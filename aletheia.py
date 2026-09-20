"""
Aletheia entrypoint - full-screen terminal interface.

Run: uv run aletheia (or python3 aletheia.py)
Required config: LLM_KEY in .env (GLM API key)
Protocol selection: LLM_PROTOCOL in .env = anthropic | openai-chat | openai-responses
Optional override: LLM_BASE_URL in .env (defaults to the per-protocol endpoint)

Interaction features:
- Responses are streamed in real time as rendered Markdown.
- Press Ctrl+C during generation to interrupt; the conversation continues afterwards.
- The agent uses terminal tools (Read, Write, Edit, Glob, Grep, Bash) plus
  TodoWrite for planning and Task to spawn subagents; Write/Edit/Bash ask
  for confirmation before each run.
- Several Task calls in one response run as parallel subagents.
- Supports /help /clear /exit slash commands.
"""
import os
import sys

from config import Config

# Kitty keyboard protocol interferes with IME; disabled unconditionally.
# Must be set before importing Textual (textual.constants reads it at import time).
os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")

from core.agent import Agent
from core.tools import FileState, ToolRegistry, register_builtins
from core.tools.task import create_task_tool
from ui.tui.app import AletheiaApp

MAIN_SYSTEM_PROMPT = """You are the main agent of the Aletheia platform.

- Answer the user's questions accurately and faithfully.
- Refer to the conversation history to maintain context.
- You can call tools (Read, Write, Edit, Glob, Grep, Bash) to inspect and
  change files and to run shell commands.
- Prefer Read/Glob/Grep over Bash (cat/ls/grep) for file inspection, and
  verify edits by reading the file back.
- When a tool returns an error, adjust the call and retry instead of
  asking the user.
- Plan multi-step work with TodoWrite before starting it: lay out the
  steps, keep exactly one in_progress, and mark steps completed as they
  finish.
- Delegate self-contained subtasks to Task subagents. Subagents do not
  see this conversation, so their prompt must carry every detail (goal,
  file paths, expected report format). Issue several Task calls in one
  response to run independent subtasks in parallel — for example, one
  subagent per experiment.
"""


def main() -> None:
    if not Config.API_KEY:
        print("LLM_KEY is not configured in the .env file.")
        print("Example: LLM_KEY=<GLM API key>")
        sys.exit(1)

    file_state = FileState()
    registry = ToolRegistry()
    register_builtins(registry, file_state)
    try:
        agent = Agent(
            system_prompt=MAIN_SYSTEM_PROMPT,
            label="main",
            # The TUI presenter takes over as observer and approval gate
            # when the app mounts (agent.ui / agent.approver).
            tools=registry,
        )
    except ValueError as e:
        print(f"[Error] {e}")
        sys.exit(1)
    # Task is bound to this agent: subagents share its client, tools and
    # approval gate, but cannot spawn further subagents.
    registry.register(create_task_tool(agent))

    AletheiaApp(agent=agent).run()

if __name__ == "__main__":
    main()
