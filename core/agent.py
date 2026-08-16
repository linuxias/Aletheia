"""
Core Agent Loop (스트리밍 + 터미널 UI 연동판).

- Anthropic SDK의 스트리밍 API로 텍스트를 실시간 출력한다.
- 응답 생성 중 Ctrl+C로 중단해도 히스토리 구조가 깨지지 않도록 처리해서,
  중단 이후에도 대화를 이어갈 수 있게 한다.
"""
from typing import List, Optional

import anthropic

from config import Config


class Agent:
    def __init__(
        self,
        system_prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        label: str = "agent",
        ui=None,
    ):
        self.client = anthropic.Anthropic(api_key=Config.API_KEY)
        self.system_prompt = system_prompt
        self.model = model or Config.MODEL
        self.max_tokens = max_tokens or Config.MAX_TOKENS
        self.label = label
        self.ui = ui or _NullUI()
        self.messages: List[dict] = []

    def run(self, user_input: str) -> str:
        """사용자 입력을 받아 응답 텍스트를 스트리밍으로 출력하고 반환한다."""
        self.messages.append({"role": "user", "content": user_input})

        final_message = self._stream_one_response()
        if final_message is None:
            # 텍스트 생성이 중단됨 (아직 assistant 메시지를 히스토리에
            # 추가하지 않았으므로 대화 구조는 깨지지 않는다)
            return "[응답 생성이 중단되었습니다]"

        self.messages.append({"role": "assistant", "content": final_message.content})
        return self._extract_text(final_message.content)

    def _stream_one_response(self):
        self.ui.start_turn(self.label)
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.system_prompt,
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        self.ui.text_delta(self.label, event.delta.text)
                final_message = stream.get_final_message()
            self.ui.end_turn(self.label)
            return final_message
        except KeyboardInterrupt:
            self.ui.interrupted(self.label)
            return None

    @staticmethod
    def _extract_text(content_blocks) -> str:
        return "\n".join(b.text for b in content_blocks if b.type == "text").strip()


class _NullUI:
    """ui를 주입하지 않고 Agent를 프로그램적으로 쓸 때(테스트 등)의 무동작 UI."""

    def start_turn(self, label):
        pass

    def text_delta(self, label, text):
        pass

    def end_turn(self, label):
        pass

    def interrupted(self, label):
        pass
