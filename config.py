"""
Aletheia 전역 설정.
환경변수로 오버라이드 가능하도록 구성한다.
"""
import os


class Config:
    # 메인 에이전트 기본 모델
    MODEL = os.environ.get("ALETHEIA_MODEL", "claude-sonnet-5")

    # 응답 최대 토큰 수
    MAX_TOKENS = int(os.environ.get("ALETHEIA_MAX_TOKENS", "4096"))

    API_KEY = os.environ.get("ANTHROPIC_API_KEY")
