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


async def wait_pinned(pilot, transcript: TranscriptView, timeout: float = 5.0) -> None:
    """Poll until the transcript sits within 2 lines of the bottom."""
    deadline = time.monotonic() + timeout
    while transcript.scroll_y < transcript.max_scroll_y - 2:
        assert time.monotonic() < deadline, "view did not follow the stream to the bottom"
        await pilot.pause()
        await asyncio.sleep(0.01)


# ---- scroll follow (UX audit P0-1) ----


async def test_long_streamed_answer_stays_pinned_to_bottom():
    chunks = [f"line {i} of a long answer\n\n" for i in range(40)]
    chunks += ["```python\n", "x = 1\ny = 2\n", "```\n", "final line\n"]  # fence repaginates on close
    app = make_app(chunks=chunks)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "write a long answer with code")
        await wait_idle(pilot, app)

        transcript = app.query_one(TranscriptView)
        assert transcript.max_scroll_y > 0
        await wait_pinned(pilot, transcript)


async def test_long_user_echo_brings_view_to_bottom():
    app = make_app(chunks=["ok"], delay=5.0)  # no delta until the echo assertion is done
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "很长的用户输入问题" * 40)  # wraps across ~11 rows
        transcript = app.query_one(TranscriptView)
        deadline = time.monotonic() + 2.0
        while transcript.scroll_y < transcript.max_scroll_y - 2:
            assert time.monotonic() < deadline, "user echo did not bring the view to the bottom"
            await pilot.pause()
            await asyncio.sleep(0.01)
        # Finish the turn quickly so the app exits cleanly.
        app._agent.client._delay = 0.01
        await wait_idle(pilot, app)


async def test_scrolled_up_view_is_never_yanked_back():
    app = make_app(chunks=["stream chunk\n\n"] * 60, delay=0.05)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "long stream")
        transcript = app.query_one(TranscriptView)

        deadline = time.monotonic() + 10.0
        while transcript.max_scroll_y < 10:
            assert time.monotonic() < deadline, "stream did not grow the transcript"
            await pilot.pause()
            await asyncio.sleep(0.01)

        # Scroll up, then re-anchor once so a follow already in flight (captured
        # before the user scrolled) is drained; the assertion covers flushes
        # that arrive AFTER the user scrolled.
        for _ in range(2):
            transcript.scroll_to(y=0, animate=False)
            await pilot.pause()

        watch_until = time.monotonic() + 0.6  # several more flush cycles
        while time.monotonic() < watch_until:
            await pilot.pause()
            await asyncio.sleep(0.05)
            assert transcript.scroll_y == 0, "a flush yanked the scrolled-up view"
        await wait_idle(pilot, app)
        assert transcript.scroll_y == 0  # stays where the user left it


async def test_scroll_inside_flush_window_is_not_yanked():
    """A scroll gesture arriving between a flush and its deferred follow wins."""
    app = make_app(chunks=["stream chunk\n\n"] * 60, delay=0.05)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "long stream")
        transcript = app.query_one(TranscriptView)

        deadline = time.monotonic() + 10.0
        while transcript.max_scroll_y < 10:
            assert time.monotonic() < deadline, "stream did not grow the transcript"
            await pilot.pause()
            await asyncio.sleep(0.01)

        # Force a flush (which schedules a deferred follow), then perform the
        # user's scroll on the immediate synchronous path while that follow is
        # still pending. The follow must honour the gesture, not re-anchor.
        app.presenter._flush(force=True)
        transcript.scroll_to(y=0, animate=False, immediate=True)

        watch_until = time.monotonic() + 1.2  # spans the full follow retry deadline
        while time.monotonic() < watch_until:
            await pilot.pause()
            await asyncio.sleep(0.05)
            assert transcript.scroll_y == 0, "deferred follow yanked the user's scroll"
        await wait_idle(pilot, app)
        assert transcript.scroll_y == 0  # stays where the user left it


async def test_submit_does_not_move_view_when_content_fits():
    app = make_app(chunks=["ok"], delay=5.0)  # no token until the assertions are done
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        splash = app.query_one(SplashView)
        splash_y = splash.region.y
        transcript = app.query_one(TranscriptView)

        await submit(app, pilot, "Hello")

        deadline = time.monotonic() + 2.0
        while True:
            await pilot.pause()
            await asyncio.sleep(0.02)
            echo = [s for s in transcript.query(Static) if "Hello" in str(s.content)]
            if echo and echo[0].region.height:
                break
            assert time.monotonic() < deadline, "echo never laid out"

        assert transcript.scroll_y == 0  # nothing moves while content fits
        assert markdown_sources(app) == []  # lazy assistant slot: no Markdown pre-token
        assert splash.region.y == splash_y  # splash stays top-aligned
        assert echo[0].region.y == splash.region.y + splash.region.height + 1  # directly below

        app._agent.client._delay = 0.01
        await wait_idle(pilot, app)


async def test_clear_leaves_view_top_aligned():
    app = make_app(chunks=["answer line\n\n"] * 40)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "long question")
        await wait_idle(pilot, app)
        transcript = app.query_one(TranscriptView)
        assert transcript.scroll_y > 0  # the long answer overflowed and was followed

        await submit(app, pilot, "/clear")
        await pilot.pause()
        assert transcript.scroll_y == 0  # fresh conversation is top-aligned


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


# ---- splash responsive layout (UX audit P0-2) ----


async def test_splash_fits_and_is_readable_at_80_columns():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        splash = app.query_one(SplashView)
        info = app.query_one("#info", Static)
        transcript = app.query_one(TranscriptView)
        assert info.region.width >= 30  # no per-character truncation of values
        assert info.region.height <= 12  # rows readable, not one-character-per-row
        # Splash (bottom border included) sits fully inside the transcript viewport.
        assert splash.region.y + splash.region.height <= (
            transcript.region.y + transcript.region.height
        )


async def test_splash_side_by_side_at_100_columns():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        wordmark = app.query_one("#wordmark", Static)
        info = app.query_one("#info", Static)
        assert info.region.width >= 30
        assert info.region.y == wordmark.region.y  # side by side, not stacked
        assert "…" in str(info.content)  # shortened cwd form in the splash


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
