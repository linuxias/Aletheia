"""Headless TUI tests: Textual run_test() + FakeStreamClient, no network, no tty."""
import asyncio
import time
from typing import List

from rich.cells import cell_len

from textual.widgets import Input, Markdown, Static

from config import Config
from core.agent import Agent

from fake_client import FakeStreamClient
from ui.tui.app import AletheiaApp
from ui.tui.commands import COMMANDS
from ui.tui.palette import CommandPalette
from ui.tui.splash import WORDMARK, SplashView, short_cwd
from ui.tui.status import HintBar, StatusBar
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
        assert Config.PROTOCOL in info
        assert app.session_id in info
        # The model is not repeated in the splash: it lives in the composer's
        # border subtitle, which stays visible after the splash scrolls away.
        assert Config.MODEL not in info
        assert Config.MODEL in app.query_one("#composer").border_subtitle
        assert app.query_one(StatusBar).state == "ready"
        assert "ready" in str(app.query_one(StatusBar).content)


async def frames_over(pilot, widget, seconds: float) -> set:
    """Distinct rendered strings a widget shows over a window."""
    seen = set()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        seen.add(str(widget.content))
        await pilot.pause()
        await asyncio.sleep(0.02)
    return seen


async def test_status_bar_animates_only_while_busy():
    """The spinner is the liveness signal, so it must move during a turn — and
    must not burn a repaint per 100 ms once the turn is over."""
    app = make_app(chunks=["ok"], delay=5.0)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        status = app.query_one(StatusBar)
        assert short_cwd() in str(status.content)
        assert len(await frames_over(pilot, status, 0.4)) == 1  # idle: static

        await submit(app, pilot, "hi")
        await pilot.pause()
        assert status.state == "thinking"
        assert app.query_one(HintBar).mode == "busy"
        assert len(await frames_over(pilot, status, 0.5)) > 1  # busy: animates

        app._agent.client._delay = 0.01
        await wait_idle(pilot, app)
        assert app.query_one(HintBar).mode == "idle"
        assert len(await frames_over(pilot, status, 0.4)) == 1  # idle again


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


async def test_transcript_spans_the_full_width():
    """A margin on any 1fr sibling shrinks them all, which once left a dead
    2-column gutter down the right of the transcript."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.query_one(TranscriptView).region.width == 100
        assert app.query_one("#composer").region.width == 100


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


# ---- slash-command registry ----


async def test_unknown_command_is_reported_and_never_reaches_the_llm():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "/nope")
        await pilot.pause()

        assert "unknown command /nope" in "".join(transcript_rendered(app))
        assert app._agent.messages == []  # not sent as a prompt
        assert not app.presenter.busy


async def test_quit_alias_dispatches_like_exit():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "/quit")
        await pilot.pause()
        assert not app.is_running


# ---- wide characters (CJK) ----


def _row_text(app, y: int) -> str:
    return app.screen._compositor.render_strips()[y].text


async def test_typing_hangul_past_the_field_never_splits_a_glyph():
    """Input scrolls to reveal a ONE-cell region at the cursor, which is half of
    a double-width character: the offset landed mid-glyph, the leftmost
    character was cut in half and rendered as a blank, and the line sat a column
    off. PromptInput snaps the offset to a character boundary."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(50, 24)) as pilot:
        await pilot.pause()
        field = app.query_one(Input)
        offsets = []
        for character in "한글로 아주 긴 질문을 입력해보는 중입니다 계속 더":
            await pilot.press(character)
            await pilot.pause()
            offsets.append(field.scroll_x)

        assert max(offsets) > 0, "the field never overflowed; widen the sample"
        # Every offset must start a character. For this sample that means the
        # cumulative cell width of some prefix of the value.
        boundaries = set()
        width = 0
        for character in field.value:
            boundaries.add(width)
            width += 2 if ord(character) > 0x2E7F and character != " " else 1
        boundaries.add(width)
        assert {o for o in offsets} <= boundaries, f"mid-glyph offsets: {sorted(set(offsets))}"


async def test_prompt_input_boundaries_match_textual_cell_positions():
    """The boundary walk reimplements tab expansion, so pin it against the
    arithmetic Textual itself uses (Input._position_to_cell)."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(50, 24)) as pilot:
        await pilot.pause()
        field = app.query_one(Input)
        for value in ("한글", "a\tb", "가\t나", "ab\tc가", "mixed 한글 text"):
            field.value = value
            await pilot.pause()
            expected = {field._position_to_cell(i) for i in range(len(value) + 1)}
            for cell in range(0, max(expected) + 1):
                snapped = field._char_boundary_at_or_after(cell)
                assert snapped in expected, f"{value!r}: {cell} -> {snapped}"
                assert snapped >= cell, f"{value!r}: {cell} snapped back to {snapped}"


async def test_status_bar_right_aligns_a_cjk_cwd():
    """len() counts characters, not cells: a Korean path measured half its true
    width, so the whole right-hand block overflowed off the widget."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        status = app.query_one(StatusBar)
        status._cwd = "~/문서/한글프로젝트"
        status._branch = "주요"
        status._refresh_line()
        await pilot.pause()

        row = _row_text(app, status.region.y)
        assert "한글프로젝트" in row, "the CJK cwd was pushed off the widget"
        assert "주요" in row
        assert cell_len(row) == 80  # still exactly one screen wide


async def test_nfd_hangul_is_normalised_to_nfc():
    """NFD Hangul is normalised to NFC on insert."""
    from ui.tui.prompt import PromptInput

    app = make_app(chunks=["ok"])
    async with app.run_test(size=(50, 24)) as pilot:
        await pilot.pause()
        field = app.query_one(PromptInput)

        nfd_an = "\u110b\u1161\u11ab"
        field.insert_text_at_cursor(nfd_an)
        await pilot.pause()
        assert field.value == "안"
        assert field.cursor_position == 1

        nfd_it = "\u110b\u1175\u11bb"  # 쌍시옷 받침
        field.clear()
        await pilot.pause()
        field.insert_text_at_cursor(nfd_it)
        await pilot.pause()
        assert field.value == "있"
        assert field.cursor_position == 1


async def test_nfd_hangul_paste_is_normalised():
    """NFD Hangul paste events are normalised to NFC."""
    from textual import events
    from ui.tui.prompt import PromptInput

    app = make_app(chunks=["ok"])
    async with app.run_test(size=(50, 24)) as pilot:
        await pilot.pause()
        field = app.query_one(PromptInput)

        nfd_text = "\u110b\u1161\u11ab\u1102\u1167\u11bc"  # 안녕 in NFD
        field._on_paste(events.Paste(nfd_text))
        await pilot.pause()
        assert field.value == "안녕"
        assert len(field.value) == 2


# ---- colour system ----


def _fg(app, glyph: str):
    """Composited foreground of the first segment whose text is `glyph`."""
    for strip in app.screen._compositor.render_strips():
        for segment in strip:
            if segment.text.strip() == glyph and segment.style and segment.style.color:
                return segment.style.color.triplet
    return None


async def test_no_markup_token_renders_as_pure_white():
    """Textual's default text tiers are `auto NN%`, and `auto` does not resolve
    inside Rich markup: the alpha is dropped and `[$text-disabled]` renders
    #ffffff — making the dimmest tokens the brightest pixels on screen. The
    theme pins literal hex to prevent that."""
    app = make_app(chunks=["answer text"])
    async with app.run_test(size=(110, 30)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)
        await pilot.pause()

        whites = [
            segment.text.strip()
            for strip in app.screen._compositor.render_strips()
            for segment in strip
            if segment.text.strip()
            and segment.style
            and segment.style.color
            and segment.style.color.triplet == (255, 255, 255)
        ]
        assert whites == [], f"pure-white spans reappeared: {whites}"


async def test_status_dot_encodes_the_outcome():
    """A failed turn reported in the success colour is a semantic bug."""
    app = make_app(error=RuntimeError("boom"))
    async with app.run_test(size=(90, 24)) as pilot:
        await pilot.pause()
        ready = _fg(app, "●")
        assert ready is not None

        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)
        await pilot.pause()
        failed = _fg(app, "●")
        assert failed is not None and failed != ready


def test_accent_is_never_used_for_chrome():
    """$accent is a muted violet that exists only to keep Token.Keyword distinct
    from Token.Name in code fences; chrome uses the $aletheia-green ramp."""
    import re
    from pathlib import Path

    ui = Path(__file__).resolve().parent.parent / "ui"
    offenders = []
    for path in ui.rglob("*.tcss"):
        # Strip /* ... */ so the header comment explaining the rule is not itself
        # a violation, then keep only rules that are not markdown-scoped.
        css = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for block in css.split("}"):
            if "$accent" in block and "Markdown" not in block:
                offenders.append(f"{path.name}: {block.strip()[:60]}")
    for path in ui.rglob("*.py"):
        if path.name == "theme.py":
            continue
        # In Python the only way $accent reaches the screen is Rich markup.
        if "[$accent" in path.read_text(encoding="utf-8"):
            offenders.append(f"{path.name}: [$accent] markup")
    assert offenders == [], f"$accent leaked into chrome: {offenders}"


# ---- splash lifetime ----


async def test_scrollbar_costs_one_column_not_two():
    """Textual's default vertical scrollbar is 2 cells. At this size the bar is a
    position indicator, not a grab handle, so the second column goes to text."""
    app = make_app(chunks=["answer line\n\n"] * 20)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        transcript = app.query_one(TranscriptView)
        assert not transcript.show_vertical_scrollbar  # splash alone still fits
        without = transcript.scrollable_content_region.width

        await submit(app, pilot, "long question")
        await wait_idle(pilot, app)
        await pilot.pause()

        assert transcript.show_vertical_scrollbar
        assert without - transcript.scrollable_content_region.width == 1


async def test_splash_scrolls_away_instead_of_being_collapsed():
    """The wordmark is the transcript's first child and must accumulate upward
    like any other history, not vanish when the first answer lands."""
    app = make_app(chunks=["answer line\n\n"] * 30)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        splash = app.query_one(SplashView)
        full_height = splash.region.height
        transcript = app.query_one(TranscriptView)

        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)
        await wait_pinned(pilot, transcript)

        # Still full size and still present — just scrolled off the top.
        assert splash.region.height == full_height
        assert app.query_one("#splash-row").display
        assert transcript.scroll_y > 0
        assert splash in transcript.children
        assert splash.region.y < transcript.region.y  # above the viewport


async def test_splash_is_reachable_again_by_scrolling_back():
    app = make_app(chunks=["answer line\n\n"] * 30)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)
        transcript = app.query_one(TranscriptView)
        await wait_pinned(pilot, transcript)

        transcript.scroll_to(y=0, animate=False)
        await pilot.pause()
        splash = app.query_one(SplashView)
        assert splash.region.y >= transcript.region.y  # back in view


# ---- command palette ----


async def test_palette_opens_on_slash_and_filters():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        palette = app.query_one(CommandPalette)
        assert not palette.visible_now

        app.query_one(Input).value = "/"
        await pilot.pause()
        assert palette.visible_now
        assert palette.option_count == len(COMMANDS)

        app.query_one(Input).value = "/cl"
        await pilot.pause()
        assert [o.id for o in palette.options] == ["/clear"]

        app.query_one(Input).value = "what is aletheia"
        await pilot.pause()
        assert not palette.visible_now  # prose never pops a palette


async def test_palette_navigation_and_tab_completion():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        palette = app.query_one(CommandPalette)
        field = app.query_one(Input)

        field.value = "/"
        await pilot.pause()
        assert palette.highlighted == 0
        await pilot.press("down")
        assert palette.highlighted == 1
        await pilot.press("up")
        assert palette.highlighted == 0
        await pilot.press("up")
        assert palette.highlighted == 0  # clamped, does not fall through to history

        await pilot.press("tab")
        assert field.value.strip() == COMMANDS[0].name
        assert not palette.visible_now


async def test_palette_enter_runs_the_highlighted_command():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.query_one(Input).value = "/cl"  # prefix only — never a valid command
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        assert app._history == ["/clear"]  # resolved through the palette
        assert app._agent.messages == []
        assert not app.query_one(CommandPalette).visible_now


async def test_escape_dismisses_the_palette_without_clearing_the_line():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        field = app.query_one(Input)
        field.value = "/he"
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one(CommandPalette).visible_now
        assert field.value == "/he"  # the line survives the dismissal


async def test_palette_never_opens_during_a_turn():
    """Opening it mid-stream would resize the transcript under the anchor
    logic; the Input is disabled during a turn, and this is the belt to that
    brace."""
    app = make_app(chunks=["chunk"] * 200, delay=0.05)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "question")
        await pilot.pause()
        assert app.presenter.busy

        app.query_one(Input).value = "/"
        await pilot.pause()
        assert not app.query_one(CommandPalette).visible_now

        app._agent.client._delay = 0.01
        await wait_idle(pilot, app)


async def test_palette_resize_does_not_move_the_composer():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        composer_y = app.query_one("#composer").region.y
        status_y = app.query_one(StatusBar).region.y
        transcript_h = app.query_one(TranscriptView).region.height

        app.query_one(Input).value = "/"
        await pilot.pause()

        assert app.query_one("#composer").region.y == composer_y
        assert app.query_one(StatusBar).region.y == status_y
        # The rows come out of the transcript, not from pushing the chrome down.
        assert app.query_one(TranscriptView).region.height < transcript_h


# ---- turn rendering ----


async def test_user_turn_is_structurally_distinct_from_the_composer():
    app = make_app(chunks=["answer"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "my question")
        await wait_idle(pilot, app)

        echo = app.query_one(TranscriptView).query(".user-turn")
        assert len(echo) == 1
        # The "❯" belongs to the composer alone; reusing it here made user
        # turns indistinguishable from the prompt when scrolling back.
        assert "❯" not in echo[0].visual.plain
        assert echo[0].visual.plain == "my question"


async def test_completed_turn_reports_elapsed_and_size():
    app = make_app(chunks=["Hello", " world"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "hi")
        await wait_idle(pilot, app)

        rendered = "".join(transcript_rendered(app))
        assert "⏱" in rendered
        assert "11 chars" in rendered  # "Hello world"
        assert "token" not in rendered  # stream() yields no usage; never fake it


async def test_help_output_is_scrolled_into_view_on_a_short_terminal():
    """On a terminal too short for the splash, /help used to land below the
    fold and look like it did nothing."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(80, 20)) as pilot:
        await pilot.pause()
        transcript = app.query_one(TranscriptView)
        assert transcript.max_scroll_y > 0  # the splash alone already overflows

        await submit(app, pilot, "/help")
        await wait_pinned(pilot, transcript)


async def test_wordmark_is_dropped_rather_than_clipped_when_too_narrow():
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        assert not app.query_one("#wordmark", Static).display
        assert Config.PROTOCOL in str(app.query_one("#info", Static).content)


def test_hints_fit_80_columns():
    """A hint that wraps to two rows pushes the composer down a row — the
    exact class of layout jump commit d7a1f2f fixed."""
    for mode, text in HintBar.HINTS.items():
        assert len(text) <= 70, f"{mode} hint is {len(text)} columns"


async def test_hint_bar_reports_the_interrupt_state():
    app = make_app(chunks=["chunk"] * 200, delay=0.05)
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "question")
        await pilot.pause()
        assert app.query_one(HintBar).mode == "busy"

        await pilot.press("ctrl+c")
        await wait_idle(pilot, app)
        assert app.query_one(HintBar).mode == "interrupted"

        await submit(app, pilot, "/clear")
        await pilot.pause()
        assert app.query_one(HintBar).mode == "idle"


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


async def test_idle_ctrl_c_needs_confirmation_before_quitting():
    """A single ctrl+c used to end the session outright, so pressing it a beat
    after the last token landed silently discarded the conversation."""
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running  # first press only arms the confirmation
        assert app.query_one(HintBar).mode == "confirm_quit"

        await pilot.press("ctrl+c")
        await pilot.pause()
        assert not app.is_running


async def test_quit_confirmation_expires_and_escape_cancels_it():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()

        # escape is the explicit "no": it disarms and never exits.
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running
        assert app.query_one(HintBar).mode == "idle"

        # A ctrl+c long after the window is a fresh first press, not a second.
        await pilot.press("ctrl+c")
        app._last_ctrl_c -= 10.0  # simulate the window elapsing
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running


async def test_escape_interrupts_a_running_turn():
    app = make_app(chunks=["chunk"] * 200, delay=0.05)
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "question")
        await pilot.pause()
        assert app.presenter.busy

        await pilot.press("escape")
        await wait_idle(pilot, app)
        assert app.is_running  # escape can never end the session
        assert app.query_one(StatusBar).state == "interrupted"
        assert [m["role"] for m in app._agent.messages] == ["user"]


async def test_escape_clears_the_input_when_idle():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(Input).value = "half-typed thought"
        await pilot.press("escape")
        await pilot.pause()
        assert app.query_one(Input).value == ""
        assert app.is_running


# ---- prompt history ----


async def test_up_recalls_prompts_and_down_restores_the_draft():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        for text in ("first question", "second question"):
            await submit(app, pilot, text)
            await wait_idle(pilot, app)

        field = app.query_one(Input)
        field.value = "a draft I have not sent"

        await pilot.press("up")
        assert field.value == "second question"
        assert field.cursor_position == len("second question")
        await pilot.press("up")
        assert field.value == "first question"
        await pilot.press("up")
        assert field.value == "first question"  # oldest entry is the floor

        await pilot.press("down")
        assert field.value == "second question"
        await pilot.press("down")
        assert field.value == "a draft I have not sent"  # the draft survived ↑


async def test_history_walks_past_command_entries():
    """A recalled "/help" used to reopen the palette, and an open palette
    consumes up/down — so history froze on the first command it hit."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        for text in ("oldest question", "/help", "newest question"):
            await submit(app, pilot, text)
            await wait_idle(pilot, app)

        field = app.query_one(Input)
        palette = app.query_one(CommandPalette)
        recalled = []
        for _ in range(3):
            await pilot.press("up")
            await pilot.pause()
            recalled.append(field.value)
            assert not palette.visible_now, "history recall must not wake the palette"

        assert recalled == ["newest question", "/help", "oldest question"]

        # ...and back down again, still passing through the command.
        for expected in ("/help", "newest question", ""):
            await pilot.press("down")
            await pilot.pause()
            assert field.value == expected


async def test_palette_still_opens_after_a_history_recall():
    """Suppression is scoped to the recalled text, not latched: the next real
    keystroke must behave normally."""
    app = make_app(chunks=["ok"])
    async with app.run_test(size=(90, 26)) as pilot:
        await pilot.pause()
        await submit(app, pilot, "/help")
        await pilot.pause()

        await pilot.press("up")
        await pilot.pause()
        field = app.query_one(Input)
        assert field.value == "/help"
        assert not app.query_one(CommandPalette).visible_now

        field.value = ""       # clear, then type a slash for real
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        assert app.query_one(CommandPalette).visible_now


async def test_history_skips_consecutive_duplicates_and_includes_commands():
    app = make_app(chunks=["ok"])
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "same")
        await wait_idle(pilot, app)
        await submit(app, pilot, "same")
        await wait_idle(pilot, app)
        await submit(app, pilot, "/help")
        await pilot.pause()

        assert app._history == ["same", "/help"]


async def test_interrupted_prompt_is_recoverable_from_history():
    """The point of history: interrupt, recall, tweak, resend — without
    retyping a prompt the UI already threw away."""
    app = make_app(chunks=["chunk"] * 200, delay=0.05)
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "the long question")
        await pilot.pause()
        await pilot.press("escape")
        await wait_idle(pilot, app)

        assert app.query_one(Input).value == ""  # submit cleared it
        await pilot.press("up")
        assert app.query_one(Input).value == "the long question"


async def test_history_is_inert_while_a_turn_runs():
    app = make_app(chunks=["chunk"] * 200, delay=0.01)
    async with app.run_test() as pilot:
        await pilot.pause()
        await submit(app, pilot, "first")
        await wait_idle(pilot, app)
        app._agent.client._delay = 0.05  # slow the second turn down instead
        await submit(app, pilot, "second")
        await pilot.pause()

        await pilot.press("up")
        assert app.query_one(Input).value == ""  # no recall into a disabled field
        app._agent.client._delay = 0.01
        await wait_idle(pilot, app)


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
