"""
Aletheia entrypoint - full-screen terminal interface.

Run: uv run aletheia (or python3 aletheia.py)
Required config: LLM_KEY in .env (GLM API key)
Protocol selection: LLM_PROTOCOL in .env = anthropic | openai-chat | openai-responses
Optional override: LLM_BASE_URL in .env (defaults to the per-protocol endpoint)

Interaction features:
- Responses are streamed in real time as rendered Markdown.
- Press Ctrl+C during generation to interrupt; the conversation continues afterwards.
- Supports /help /clear /exit slash commands.
"""
import sys

from config import Config
from core.agent import Agent
from ui.tui.app import AletheiaApp

MAIN_SYSTEM_PROMPT = """You are the main agent of the Aletheia platform.

- Answer the user's questions accurately and faithfully.
- Refer to the conversation history to maintain context.
"""


def main() -> None:
    if not Config.API_KEY:
        print("LLM_KEY is not configured in the .env file.")
        print("Example: LLM_KEY=<GLM API key>")
        sys.exit(1)

    try:
        agent = Agent(
            system_prompt=MAIN_SYSTEM_PROMPT,
            label="main",
        )
    except ValueError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    AletheiaApp(agent=agent).run()


if __name__ == "__main__":
    main()
