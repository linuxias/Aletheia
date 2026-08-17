"""Headless TUI tests: Textual run_test() + FakeStreamClient, no network, no tty."""
import asyncio
import time
from typing import List

from textual.widgets import Input, Markdown, Static

from config import Config
from core.agent import Agent

from fake_client import FakeStreamClient
from ui.tui.app import AletheiaApp
from ui.tui.splash import WORDMARK, SplashView
from ui.tui.status import StatusBar
from ui.tui.transcript import TranscriptView


def make_app(**client_kwargs) -> AletheiaApp:
    client = FakeStreamClient(**client_kwargs)
    agent = Agent(system_prompt="test prompt", label="main", client=client)
    return AletheiaApp(agent=agent)


async def wait_idle(pilot, app: AletheiaApp, timeout: float = 10.0) -> None:
    """Poll pilot.pause() until the current turn finishes (bounded, never hangs)."""
    deadline = time.monotonic() + timeout
    while app.presenter.busy:
        assert time.monotonic() < deadline, "timed out waiting for the turn to finish"
        await pilot.pause()
        await asyncio.sleep(0.01)


async def submit(app: AletheiaApp, pilot, text: str) -> None:
    app.query_one(Input).value = text
    await pilot.press("enter")
    await pilot.pause()


def transcript_texts(app: AletheiaApp) -> List[str]:
    return [str(w.content) for w in app.query_one(TranscriptView).query(Static)]


def transcript_rendered(app: AletheiaApp) -> List[str]:
    """Plain rendered text of the transcript Statics (markup tags resolved)."""
    return [w.visual.plain for w in app.query_one(TranscriptView).query(Static)]


def markdown_sources(app: AletheiaApp) -> List[str]:
    return [w.source for w in app.query_one(TranscriptView).query(Markdown)]


# ---- wordmark (design section 7) ----


def test_wordmark_six_rows_of_60_columns():
    assert len(WORDMARK) == 6
    assert all(len(row) == 60 for row in WORDMARK)
    flat = "".join(WORDMARK)
    assert "▄" not in flat  # corrupted E glyph
    assert "██████╔╝" not in flat  # corrupted L stem


# ---- scenario 1: splash ----


async def test_splash_shows_session_facts_and_ready_status():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(SplashView)  # mounted
        info = str(app.query_one("#info", Static).content)
        assert Config.MODEL in info
        assert Config.PROTOCOL in info
        assert app.session_id in info
        assert app.query_one(StatusBar).state == "ready"
        assert "ready" in str(app.query_one(StatusBar).content)
        assert Config.MODEL in str(app.query_one(StatusBar).content)


# ---- scenario 2: happy path ----


async def test_submit_streams_markdown_and_appends_history():
    app = make_app(chunks=["Hello", " world"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)

        sources = markdown_sources(app)
        assert len(sources) == 1
        assert sources[0] == "Hello world"
        assert app.query_one(StatusBar).state == "ready"
        assert not app.query_one(Input).disabled
        roles = [m["role"] for m in app._agent.messages]
        assert roles == ["user", "assistant"]
        assert app._agent.messages[1]["content"] == "Hello world"


# ---- scenario 3: interrupt ----


async def test_ctrl_c_interrupts_generation_and_keeps_history_intact():
    app = make_app(chunks=["chunk"] * 200, delay=0.05)
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "question")
        await pilot.pause()
        assert app.presenter.busy

        # Let at least one delta render before interrupting so the partial
        # text is guaranteed to exist.
        deadline = time.monotonic() + 10.0
        while not any(markdown_sources(app)):
            assert time.monotonic() < deadline, "no delta streamed before interrupt"
            await pilot.pause()
            await asyncio.sleep(0.01)

        await pilot.press("ctrl+c")
        await wait_idle(pilot, app)

        assert not app.presenter.busy
        assert "[interrupted]" in "".join(transcript_rendered(app))  # note is visible
        sources = markdown_sources(app)
        assert sources and sources[0]  # partial streamed text stays rendered
        assert "chunk" in sources[0]
        assert app.query_one(StatusBar).state == "interrupted"
        assert not app.query_one(Input).disabled
        roles = [m["role"] for m in app._agent.messages]
        assert roles == ["user"]  # no assistant message after an interrupt


# ---- scenario 4: empty response ----


async def test_empty_response_notes_and_skips_history():
    app = make_app(chunks=[])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)

        assert "(empty response)" in "".join(transcript_texts(app))
        roles = [m["role"] for m in app._agent.messages]
        assert roles == ["user"]
        assert app.query_one(StatusBar).state == "ready"


# ---- scenario 5: error ----


async def test_error_shows_note_and_next_submit_still_works():
    app = make_app(error=RuntimeError("boom"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)

        assert "[error] RuntimeError: boom" in "".join(transcript_texts(app))
        assert app.query_one(StatusBar).state == "error: RuntimeError"
        roles = [m["role"] for m in app._agent.messages]
        assert roles == ["user"]

        # App is still alive: recover the fake client and submit again.
        app._agent.client._error = None
        app._agent.client._chunks = ["recovered"]
        await submit(app, pilot, "again")
        await wait_idle(pilot, app)
        assert app.query_one(StatusBar).state == "ready"
        assert markdown_sources(app)[-1] == "recovered"


# ---- markup safety (user text / exception text are never parsed as markup) ----


async def test_user_text_with_markup_is_escaped():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "x [/] y")
        await wait_idle(pilot, app)

        # The app survived the turn and the echo shows the full string.
        assert app.query_one(StatusBar).state == "ready"
        rendered = "".join(transcript_rendered(app))
        assert "x [/] y" in rendered


async def test_error_note_with_markup_is_escaped():
    app = make_app(error=RuntimeError("boom [/] x"))
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)

        assert "[error] RuntimeError: boom [/] x" in "".join(transcript_rendered(app))
        assert app.query_one(StatusBar).state == "error: RuntimeError"
        assert not app.query_one(Input).disabled  # app stayed alive


# ---- scenario 6: /clear ----


async def test_clear_wipes_conversation_and_remounts_same_session():
    app = make_app(chunks=["Hello", " world"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)
        assert len(markdown_sources(app)) == 1

        await submit(app, pilot, "/clear")
        await pilot.pause()

        assert app._agent.messages == []
        assert markdown_sources(app) == []
        splash = app.query_one(SplashView)
        assert splash.session_id == app.session_id  # session id survives /clear
        assert app.query_one(StatusBar).state == "ready"


# ---- scenario 7: /exit ----


async def test_exit_command_quits_the_app():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "/exit")
        await pilot.pause()
        # Live assertion: /exit must have stopped the app before the context ends.
        assert not app.is_running


# ---- scenario 8: ctrl+c idle / ctrl+d ----


async def test_ctrl_c_when_idle_exits():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert not app.is_running


async def test_ctrl_d_exits_only_on_empty_input():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        input_widget = app.query_one(Input)
        input_widget.value = "partial text"
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.is_running  # does not exit while editing
        assert input_widget.value == "partial text"  # and does not corrupt editing

        input_widget.value = ""
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert not app.is_running
