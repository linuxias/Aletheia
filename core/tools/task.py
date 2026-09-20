"""Task tool: spawn a subagent with a fresh context to run one delegated job."""
from typing import TYPE_CHECKING, Callable

from core.tools.base import Tool, clip

if TYPE_CHECKING:
    from core.agent import Agent


class TaskTool(Tool):
    name = "Task"
    description = (
        "Launch a subagent that works on one task in its own fresh context and "
        "returns its final report as this tool's result. The subagent cannot see "
        "this conversation and cannot spawn further subagents, so the prompt must "
        "carry ALL the context and instructions needed: goal, relevant file paths, "
        "constraints, and the expected report format. Use it to parallelise "
        "independent work — issue several Task calls in one response and they run "
        "concurrently."
    )
    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short task summary (3-5 words) shown in the UI",
            },
            "prompt": {
                "type": "string",
                "description": "Complete, self-contained instructions for the subagent",
            },
        },
        "required": ["description", "prompt"],
    }
    # Sibling Task calls in one batch are dispatched to a thread pool.
    parallel_safe = True

    def __init__(self, agent_factory: Callable[[str], "Agent"]):
        super().__init__()
        self._factory = agent_factory

    def run(self, description: str, prompt: str) -> str:
        agent = self._factory(description)
        report = agent.run(prompt)
        return clip(report) if report else "(subagent returned no report)"


SUBAGENT_SYSTEM_PROMPT = """You are a subagent of the Aletheia platform, spawned to complete one
specific task.

- Work autonomously with the available tools (Read, Write, Edit, Glob,
  Grep, Bash, TodoWrite). Do not ask questions — make reasonable
  assumptions and note them in your report.
- You cannot see the spawning conversation and cannot spawn further
  subagents.
- When the task is done (or truly blocked), reply with your final report
  as plain text: the outcome, what you did, and the key findings. That
  report is the only thing returned to the spawning agent.
"""


def create_task_tool(parent: "Agent") -> TaskTool:
    """Build the Task tool bound to a parent agent.

    Subagents share the parent's LLM client, observer (scoped through
    SubagentObserver), approver, and tool instances, but get a fresh
    history and a registry without Task — delegation is one level deep.
    parent.ui / parent.approver are read lazily (at spawn time), so the
    tool can be registered before a frontend attaches them.
    """
    from core.agent import Agent
    from core.observer import SubagentObserver

    sub_tools = parent.tools.without("Task") if parent.tools is not None else None

    def factory(description: str) -> Agent:
        return Agent(
            system_prompt=SUBAGENT_SYSTEM_PROMPT,
            label=f"sub:{description[:16]}",
            model=parent.model,
            max_tokens=parent.max_tokens,
            client=parent.client,
            ui=SubagentObserver(parent.ui),
            tools=sub_tools,
            approver=parent.approver,
        )

    return TaskTool(factory)
