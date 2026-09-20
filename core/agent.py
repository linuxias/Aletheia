"""
Core Agent Loop (streaming + terminal UI integration).

- Streams responses in real time through the protocol-agnostic LLMClient interface.
- Runs a bounded tool loop: stream, execute requested tools, feed results
  back, stream again, until the model answers without tool calls.
- Executes each response's tool calls as a batch: parallel-safe tools (e.g.
  Task) are dispatched to a thread pool so sibling calls run concurrently,
  everything else runs sequentially in call order.
- Handles Ctrl+C so the history structure stays protocol-valid (every
  tool_use is answered by a tool_result) and the conversation can continue
  after an interruption.
"""
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple

from config import Config
from core.llm import LLMClient, create_client
from core.llm.events import TextDelta, ToolCall
from core.observer import AgentObserver, NullObserver
from core.tools.base import Tool
from core.tools.registry import ToolRegistry

# Upper bound on threads used for the parallel-safe calls of one batch.
_MAX_PARALLEL_TOOLS = 8


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
        """Execute one response's calls as a batch; returns (results, interrupted).

        Parallel-safe tools (e.g. Task) are submitted to a thread pool so
        sibling calls run concurrently; the others run sequentially in call
        order on this thread. Results are assembled in call order either
        way. Exactly one result is produced per tool_use in every path —
        approval denial, argument parse failure, tool crash, and user
        interruption included — so the history stays protocol-valid for
        the next round.
        """
        results: List[Optional[dict]] = [None] * len(tool_calls)
        futures: Dict[int, Future] = {}
        executor: Optional[ThreadPoolExecutor] = None
        try:
            for i, (call, (args, parse_error)) in enumerate(zip(tool_calls, parsed)):
                self.ui.tool_call(self.label, call.name, _arg_summary(args))
                tool = self.tools.get(call.name) if self.tools else None
                if parse_error is None and tool is not None and tool.parallel_safe:
                    if executor is None:
                        executor = ThreadPoolExecutor(
                            max_workers=min(_MAX_PARALLEL_TOOLS, len(tool_calls)),
                            thread_name_prefix="aletheia-tool",
                        )
                    futures[i] = executor.submit(self._run_one, call, args, parse_error)
                else:
                    results[i] = self._run_one(call, args, parse_error)
            for i in sorted(futures):
                results[i] = futures[i].result()
        except KeyboardInterrupt:
            self.ui.interrupted(self.label)
            # Running pool threads cannot be killed; their eventual output
            # is dropped. Anthropic requires a tool_result for every
            # tool_use before the next assistant turn, so every call that
            # never produced a result gets a synthetic one.
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            for i, call in enumerate(tool_calls):
                if results[i] is None:
                    results[i] = _synthetic_result(call, "[Interrupted by user before execution]")
            return results, True
        except Exception as e:
            # A harness bug (tool bugs are caught per call in _run_one)
            # must not corrupt the history either: report it against the
            # first call without a result, mark the rest not executed.
            if executor is not None:
                executor.shutdown(wait=False, cancel_futures=True)
            pending = [i for i, r in enumerate(results) if r is None]
            for j, i in enumerate(pending):
                content = (
                    f"Error: {type(e).__name__}: {e}"
                    if j == 0
                    else "[Not executed: earlier tool failed]"
                )
                results[i] = _synthetic_result(tool_calls[i], content)
        finally:
            if executor is not None:
                executor.shutdown(wait=False)
        return results, False

    def _run_one(
        self, call: ToolCall, args: dict, parse_error: Optional[str]
    ) -> dict:
        """Resolve one tool call to its result message; never raises for
        tool-level failures (errors become the tool result so the model
        can adjust and retry)."""
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
            try:
                output, is_error = self.tools.execute(call.name, args)
            except Exception as e:
                output, is_error = f"Error: {type(e).__name__}: {e}", True
        self.ui.tool_result(self.label, call.name, output, is_error)
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": output,
            "is_error": is_error,
        }


def _arg_summary(args: dict) -> str:
    summary = " ".join(f"{k}={str(v)[:40]}" for k, v in list(args.items())[:3])
    return summary.replace("\n", " ")[:100]


def _synthetic_result(call: ToolCall, content: str) -> dict:
    """A stand-in tool_result for a call that never produced output."""
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "content": content,
        "is_error": True,
    }
