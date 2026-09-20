from core.tools.todo import TodoState, TodoWrite


def _tool():
    state = TodoState()
    return TodoWrite(state), state


def test_write_and_render_checklist():
    tool, state = _tool()
    out = tool.run(
        todos=[
            {
                "subject": "formulate hypotheses",
                "description": "turn the topic into 3 testable claims",
                "status": "completed",
            },
            {
                "subject": "run baseline experiment",
                "description": "train 3 epochs on the toy set",
                "status": "in_progress",
                "activeForm": "running baseline experiment",
            },
            {"subject": "ablate the adapter", "status": "pending"},
        ]
    )
    assert out.splitlines() == [
        "[x] formulate hypotheses — turn the topic into 3 testable claims",
        "[~] running baseline experiment (run baseline experiment) — train 3 epochs on the toy set",
        "[ ] ablate the adapter",
    ]
    assert len(state.todos) == 3


def test_each_call_replaces_the_whole_list():
    tool, state = _tool()
    tool.run(todos=[{"subject": "a", "status": "pending"}])
    tool.run(todos=[{"subject": "b", "status": "completed"}])
    assert [t["subject"] for t in state.todos] == ["b"]
    assert tool.run(todos=[]) == "(no todos)"
    assert state.todos == []


def test_invalid_status_is_an_error_result():
    tool, state = _tool()
    out = tool.run(todos=[{"subject": "a", "status": "doing"}])
    assert out.startswith("Error: todo #1 has invalid status 'doing'")
    assert "pending, in_progress, completed" in out
    assert state.todos == []  # a rejected update changes nothing


def test_missing_subject_is_an_error_result():
    tool, _ = _tool()
    assert tool.run(todos=[{"subject": "", "status": "pending"}]).startswith(
        "Error: todo #1 needs a non-empty 'subject'"
    )


def test_non_list_todos_is_an_error_result():
    tool, _ = _tool()
    assert tool.run(todos={"subject": "a"}) == "Error: todos must be an array"


def test_active_form_ignored_outside_in_progress():
    tool, _ = _tool()
    out = tool.run(todos=[{"subject": "a", "status": "completed", "activeForm": "doing a"}])
    assert out == "[x] a"
