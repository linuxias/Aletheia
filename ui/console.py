"""
터미널 UI 레이어. rich를 사용해 실시간 텍스트 스트리밍 대화 인터페이스를
제공한다. Agent 클래스는 이 인터페이스에만 의존하므로 UI를 통째로 바꾸고
싶으면 (예: 웹소켓 기반 GUI) 이 파일과 같은 메서드 시그니처를 가진 클래스로
교체하면 된다.
"""
from rich.console import Console as RichConsole
from rich.panel import Panel

_MAIN_COLOR = "bright_green"


class ConsoleUI:
    def __init__(self):
        self.console = RichConsole()
        self._open_label = None

    # ---------- 시작 화면 ----------
    def banner(self, model: str):
        self.console.print(
            Panel.fit(
                f"[bold]모델[/bold]: {model}\n"
                f"[dim]명령어: /help /clear /exit[/dim]",
                title="Aletheia",
                border_style=_MAIN_COLOR,
            )
        )

    def help(self):
        self.console.print(
            "[bold]/help[/bold]   이 도움말\n"
            "[bold]/clear[/bold]  대화 히스토리 초기화\n"
            "[bold]/exit[/bold]   종료 (Ctrl+D 도 가능)"
        )

    # ---------- 사용자 입력 ----------
    def user_input(self) -> str:
        return self.console.input("[bold cyan]you>[/bold cyan] ")

    # ---------- 응답 스트리밍 ----------
    def start_turn(self, label: str):
        self.console.print(f"\n[bold {_MAIN_COLOR}]aletheia>[/bold {_MAIN_COLOR}] ", end="")
        self._open_label = label

    def text_delta(self, label: str, text: str):
        self.console.print(text, end="", style=_MAIN_COLOR, highlight=False)

    def end_turn(self, label: str):
        if self._open_label == label:
            self.console.print()
            self._open_label = None

    def interrupted(self, label: str):
        self.console.print("\n[yellow][사용자에 의해 중단되었습니다][/yellow]")
        self._open_label = None

    # ---------- 기타 ----------
    def info(self, message: str):
        self.console.print(f"[dim]{message}[/dim]")

    def error(self, message: str):
        self.console.print(f"[bold red]{message}[/bold red]")
