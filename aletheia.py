"""
Aletheia entrypoint - Claude Code / Hermes style terminal interface.

Run: uv run aletheia (or python3 aletheia.py)
Required config: LLM_KEY in .env (GLM API key)
Protocol selection: LLM_PROTOCOL in .env = anthropic | openai-chat | openai-responses
Optional override: LLM_BASE_URL in .env (defaults to the per-protocol endpoint)

Interaction features:
- Responses are streamed in real time.
- Press Ctrl+C during generation to interrupt; the conversation continues afterwards.
- Supports /help /clear /exit slash commands.
"""
import sys

from config import Config
from core.agent import Agent
from ui.console import ConsoleUI

MAIN_SYSTEM_PROMPT = """You are the main agent of the Aletheia platform.

- Answer the user's questions accurately and faithfully.
- Refer to the conversation history to maintain context.
"""


def main() -> None:
    if not Config.API_KEY:
        print("LLM_KEY is not configured in the .env file.")
        print("Example: LLM_KEY=<GLM API key>")
        sys.exit(1)

    ui = ConsoleUI()
    try:
        agent = Agent(
            system_prompt=MAIN_SYSTEM_PROMPT,
            label="main",
            ui=ui,
        )
    except ValueError as e:
        print(f"[Error] {e}")
        sys.exit(1)

    ui.banner(Config.MODEL)
    ui.info(f"Protocol: {Config.PROTOCOL}")

    while True:
        try:
            user_input = ui.user_input().strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            ui.info("\n(Input cancelled. Use /exit to quit.)")
            continue

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/help":
            ui.help()
            continue
        if user_input == "/clear":
            agent.clear()
            ui.info("Conversation history cleared.")
            continue

        try:
            agent.run(user_input)  # output was already streamed, so the return value is unused
        except KeyboardInterrupt:
            ui.info("\n(Interrupted)")
        except Exception as e:
            ui.error(f"[Error] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
