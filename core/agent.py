"""
Core Agent Loop (streaming + terminal UI integration).

- Streams responses in real time through the protocol-agnostic LLMClient interface.
- Runs a bounded tool loop: stream, execute requested tools, feed results
  back, stream again, until the model answers without tool calls.
- Handles Ctrl+C so the history structure stays protocol-valid (every
  tool_use is answered by a tool_result) and the conversation can continue
  after an interruption.
"""
import json
import threading
from typing import Callable, List, Optional, Tuple

from config import Config
from core.llm import LLMClient, create_client
from core.llm.events import TextDelta, ToolCall
from core.observer import AgentObserver, NullObserver
from core.tools.base import Tool
from core.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        system_prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        label: str = "agent",
        ui: Optional[AgentObserver] = None,
        client: Optional[LLMClient] = None,
        tools: Optional[ToolRegistry] = None,
        approver: Optional[Callable[[Tool, dict], bool]] = None,
    ):
        # Use the injected client, or select one via environment (LLM_PROTOCOL).
        self.client = client or create_client(Config.PROTOCOL, Config.API_KEY, Config.BASE_URL)
        self.system_prompt = system_prompt
        self.model = model or Config.MODEL
        self.max_tokens = max_tokens or Config.MAX_TOKENS
        self.label = label
        self.ui = ui or NullObserver()
        self.messages: List[dict] = []
        self.tools = tools
        # Decides whether a tool flagged requires_approval may run. None
        # means everything is allowed (tests, programmatic use).
        self.approver = approver
        self._cancel = threading.Event()

    def request_cancel(self) -> None:
        """Ask the running generation to stop at the next delta."""
        self._cancel.set()

    def clear(self):
        """Reset the conversation history."""
        self.messages = []

    def run(self, user_input: str) -> str:
        """Run the tool loop until the model answers without tool calls."""
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(Config.MAX_TOOL_ROUNDS):
            outcome = self._stream_one_response()
            if outcome is None:
                # Interrupted while streaming: nothing was appended for this
                # turn, so the history stays protocol-valid.
                return "[Response generation was interrupted]"
            text, tool_calls = outcome

            if tool_calls:
                parsed = [self._parse_args(c) for c in tool_calls]
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": ([{"type": "text", "text": text}] if text else [])
                        + [
                            {
                                "type": "tool_use",
                                "id": c.id,
                                "name": c.name,
                                "input": args,
                            }
                            for c, (args, _) in zip(tool_calls, parsed)
                        ],
                    }
                )
            elif text:
                # Empty responses (e.g. thinking consumed all max_tokens) are
                # not added to history.
                self.messages.append({"role": "assistant", "content": text})
            if not tool_calls:
                return text

            results, interrupted = self._execute_tool_calls(tool_calls, parsed)
            self.messages.extend(results)  # exactly one result per tool_use
            if interrupted:
                return "[Tool execution was interrupted]"
        self.ui.end_turn(self.label)
        return "[Tool round limit reached]"

    @staticmethod
    def _parse_args(call: ToolCall) -> Tuple[dict, Optional[str]]:
        """Parse raw JSON arguments; on failure return the error to report
        as the tool result so the model can retry with valid JSON."""
        try:
            return json.loads(call.arguments or "{}"), None
        except json.JSONDecodeError:
            return {}, (
                "Error: could not parse tool arguments as JSON: "
                f"{call.arguments[:200]!r}"
            )

    def _stream_one_response(self) -> Optional[Tuple[str, List[ToolCall]]]:
        """Stream one model response; None means interrupted by the user."""
        self._cancel.clear()
        self.ui.start_turn(self.label)
        try:
            parts: List[str] = []
            tool_calls: List[ToolCall] = []
            for event in self.client.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=self.messages,
                tools=self.tools.definitions() if self.tools else None,
            ):
                if self._cancel.is_set():
                    self.ui.interrupted(self.label)
                    return None
                if isinstance(event, TextDelta):
                    self.ui.text_delta(self.label, event.text)
                    parts.append(event.text)
                else:
                    tool_calls.append(event)
            if not tool_calls:
                # Tool rounds keep the turn open; tool_call/tool_result
                # report the activity instead of ending it.
                self.ui.end_turn(self.label)
            return "".join(parts), tool_calls
        except KeyboardInterrupt:
            self.ui.interrupted(self.label)
            return None

    def _execute_tool_calls(
        self, tool_calls: List[ToolCall], parsed: List[Tuple[dict, Optional[str]]]
    ) -> Tuple[List[dict], bool]:
        """Execute calls in order; returns (results, interrupted).

        Exactly one result is appended per tool_use in every path —
        approval denial, argument parse failure, tool crash, and user
        interruption included — so the history stays protocol-valid for
        the next round.
        """
        results: List[dict] = []
        try:
            for call, (args, parse_error) in zip(tool_calls, parsed):
                self.ui.tool_call(self.label, call.name, _arg_summary(args))
                tool = self.tools.get(call.name) if self.tools else None
                if parse_error is not None:
                    output, is_error = parse_error, True
                elif tool is None:
                    output, is_error = f"Error: unknown tool {call.name!r}", True
                elif (
                    tool.requires_approval
                    and self.approver is not None
                    and not self.approver(tool, args)
                ):
                    output, is_error = "[Denied by user]", True
                else:
                    output, is_error = self.tools.execute(call.name, args)
                self.ui.tool_result(self.label, call.name, output, is_error)
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
        except KeyboardInterrupt:
            self.ui.interrupted(self.label)
            # Anthropic requires a tool_result for every tool_use before the
            # next assistant turn: fill in synthetic results for the calls
            # that never ran (including the interrupted one).
            for call in tool_calls[len(results):]:
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": "[Interrupted by user before execution]",
                        "is_error": True,
                    }
                )
            return results, True
        except Exception as e:
            # A tool bug must not corrupt the history either: report it as
            # the result of the in-flight call, skip the rest.
            in_flight = tool_calls[len(results)]
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": in_flight.id,
                    "content": f"Error: {type(e).__name__}: {e}",
                    "is_error": True,
                }
            )
            for call in tool_calls[len(results):]:
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": "[Not executed: earlier tool failed]",
                        "is_error": True,
                    }
                )
        return results, False


def _arg_summary(args: dict) -> str:
    summary = " ".join(f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3])
    return summary.replace("\n", " ")[:100]
