"""
Aletheia 엔트리포인트 - Claude Code / Hermes 스타일 터미널 인터페이스.

실행: uv run aletheia (또는 python3 aletheia.py)
필요 환경변수: ANTHROPIC_API_KEY

인터랙션 특징:
- 응답이 실시간으로 스트리밍 출력된다.
- 응답 생성 중 Ctrl+C로 중단할 수 있고, 이어서 대화를 계속할 수 있다.
- /help /clear /exit 슬래시 명령어를 지원한다.
"""
import sys

from config import Config
from core.agent import Agent
from ui.console import ConsoleUI

MAIN_SYSTEM_PROMPT = """당신은 Aletheia 플랫폼의 메인 에이전트입니다.

- 사용자의 질문에 정확하고 성실하게 답변하세요.
- 대화 히스토리를 참고해 맥락을 유지하세요.
"""


def main() -> None:
    if not Config.API_KEY:
        print("환경변수 ANTHROPIC_API_KEY 가 설정되어 있지 않습니다.")
        print("예: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    ui = ConsoleUI()
    agent = Agent(
        system_prompt=MAIN_SYSTEM_PROMPT,
        label="main",
        ui=ui,
    )

    ui.banner(Config.MODEL)

    while True:
        try:
            user_input = ui.user_input().strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            ui.info("\n(입력을 취소했습니다. 종료하려면 /exit)")
            continue

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            break
        if user_input == "/help":
            ui.help()
            continue
        if user_input == "/clear":
            agent.messages = []
            ui.info("대화 히스토리를 초기화했습니다.")
            continue

        try:
            agent.run(user_input)  # 결과는 스트리밍 중 이미 출력되었으므로 반환값은 사용하지 않음
        except KeyboardInterrupt:
            ui.info("\n(중단됨)")
        except Exception as e:
            ui.error(f"[오류] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
