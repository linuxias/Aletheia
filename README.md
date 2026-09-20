# Aletheia

**A self-improving agent platform for research: it experiments on a research topic,
verifies the results, and refines the work — automatically.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

## Why "Aletheia"?

*Aletheia* (ἀλήθεια) is the ancient Greek word for truth — literally, "un-concealment."
For the Greeks, truth was not merely a property of statements; it was the process of
bringing what is hidden into the open through inquiry.

That is exactly what this platform does. A research idea is not accepted because it
sounds right — it is subjected to experiment, checked against evidence, and only what
survives becomes knowledge. Aletheia automates that discipline.

## Overview

Aletheia is an agent platform built around one core capability: **the autonomous
research loop**. Given a research topic, the platform carries it through the full cycle —

1. **Hypothesize** — formalize the topic into concrete, testable hypotheses
2. **Experiment** — design and run experiments: code, data, benchmarks, analyses
3. **Verify** — adversarially check the results: reproduce, ablate, stress-test
4. **Improve** — feed what survived back in: refine the method, update what the
   system knows, and start the next round better informed than the last

— repeating until the results hold up. No step is a human handoff; the loop closes
on itself.

To run this loop in the wild, Aletheia takes the form of a **general-purpose agent**,
in the mold of Hermes or Claude: a single conversational agent that can plan, act, use
tools, remember, and coordinate other agents. Point it at a research question — survey
a literature and stress-test its claims, tune a model against its benchmark, explore a
hypothesis over a dataset — and it investigates end to end.

## Core Building Blocks

The research loop is powered by a small set of composable primitives:

### 🧠 Memory

Persistent memory that survives across sessions — and across iterations of the loop.
Working context stays separate from long-term knowledge: verified findings, failed
approaches, and facts about the project are stored, recalled when relevant, and revised
when contradicted. Each research round starts from everything the previous rounds
learned; nothing that was hard-won is silently forgotten.

### 🛠 Skills

Packaged, reusable procedures. A skill captures *how* to do something — an experimental
protocol, an evaluation recipe, a domain method — as a unit the agent loads on demand.
Skills keep the core agent small and general while letting it grow deep competence in
specific research domains, and they improve too: procedures that consistently produce
verified results get promoted; ones that don't get rewritten.

### 🔌 MCP (Model Context Protocol)

Standardized access to the tools an experiment needs. Through MCP, Aletheia connects to
code execution, search, databases, and any MCP-compatible server. Integrations live
outside the core behind an open protocol, so the platform's reach grows with the
ecosystem instead of with hardcoded code.

### 🔄 Agent Workflow

Deterministic orchestration for multi-step, multi-agent work. A research round is a
pipeline: fan out hypotheses to parallel investigators, run experiments under controlled
conditions, verify findings adversarially, synthesize, and decide what to try next.
Workflows impose structure — checkpoints, retries, isolation — where determinism helps,
so the model's judgment is spent where it matters.

## How It Fits Together

```
              ┌─────────────────────────────────────────────┐
              │              The Research Loop              │
              │                                             │
              │   ┌────────────┐   ┌─────────────┐          │
              │   │ Hypothesize│──▶│ Experiment  │          │
              │   └────────────┘   └─────────────┘          │
              │         ▲               │                   │
              │         │        ┌─────▼─────┐             │
              │    ┌────┴─────┐  │  Verify   │             │
              │    │ Improve  │◀─┤ (adversar.)│             │
              │    └──────────┘  └───────────┘             │
              │                                             │
              └───────┬───────────┬───────────┬─────────────┘
                      ▼           ▼           ▼
               ┌──────────┐ ┌──────────┐ ┌─────────────┐
               │  Memory  │ │  Skills  │ │  Workflows  │
               └────┬─────┘ └────┬─────┘ └──────┬──────┘
                    │            │              │
                    └────────────┴──────┬───────┘
                                        ▼
                            ┌───────────────────────┐
                            │    MCP Tool Layer     │
                            │  code · data · search │
                            └───────────────────────┘
```

## Built-in Terminal Tools

The first shipped capability of the agent core: Claude Code-style terminal
tools, executed in-process and available to the main agent over all three
protocols (`LLM_PROTOCOL`: `anthropic` / `openai-chat` / `openai-responses`)
through a protocol-neutral tool-call representation.

| Tool        | What it does                                                    | Approval |
| ----------- | --------------------------------------------------------------- | -------- |
| `Read`      | Numbered, line-ranged file contents                             | automatic |
| `Glob`      | Find files by pattern, newest first                             | automatic |
| `Grep`      | Regex search across files (content / matches / count modes)     | automatic |
| `Write`     | Create or overwrite files (read-before-overwrite enforced)      | per call |
| `Edit`      | Exact-match replacement with uniqueness check + diff            | per call |
| `Bash`      | Shell command with timeout, captured stdout/stderr and exit code | per call |
| `TodoWrite` | Replace the session's plan/checklist; returns the rendered list | automatic |
| `Task`      | Spawn a subagent with a fresh context; returns its final report | automatic** |

- Dangerous tools (`Write` / `Edit` / `Bash`) ask for confirmation (`y/N`)
  before each execution; denials go back to the model as tool results so it
  can adapt. ** `Task` itself needs no approval, but dangerous tools used
  *inside* a subagent still do; approvals from parallel subagents are
  serialised into one modal at a time.
- Ctrl+C interrupts streaming or a running tool while keeping the
  conversation history structurally valid. Already-running subagents
  finish their current work; calls that never produced output get
  synthetic results so the history stays protocol-valid.
- `ALETHEIA_MAX_TOOL_ROUNDS` (default 20) bounds the stream-execute loop
  per user input; agentic sessions may want a higher `ALETHEIA_MAX_TOKENS`
  than the 4096 default.

### Planning: TodoWrite

`TodoWrite` holds the session's live plan — the detailed checklist for
multi-step work such as an experiment campaign. Each call replaces the
whole list (send every todo, not just the changed ones); the rendered
checklist comes back as the tool result so the plan stays visible in the
conversation.

### Delegation: Task and parallel subagents

`Task` spawns a subagent with its own fresh context: it shares the
parent's LLM client, tools, and approval gate, but sees none of the parent
conversation and cannot spawn further subagents (delegation is one level
deep). Its final report is the tool result. When the model issues several
`Task` calls in one response they run **concurrently** — one subagent per
experiment — while file/shell tools in the same batch stay sequential.
Subagent tool activity is shown in the transcript tagged with the
subagent's label.

## Design Principles

1. **Nothing is true until it survives verification.** Claims are hypotheses by
   default; only reproduced, stress-tested results get promoted to knowledge.
2. **Improvement must be earned.** Every refinement — to a method, a skill, or a
   conclusion — cites the experiment that justified it.
3. **Small core, extensible surface.** The agent stays lean; capability comes from
   skills, tools, and workflows added without touching the core.
4. **Open protocols over private integrations.** MCP and open standards keep the
   platform portable across models and providers.
5. **Everything inspectable.** Hypotheses, experiment runs, and verification verdicts
   are first-class artifacts a human can read, audit, and override.

## Project Status

⚠️ Aletheia is in early development — the repository is young and the architecture
above describes the target design. Components are being built out incrementally;
expect the surface to change.

## CJK / Hangul Input

`PromptInput` fixes two CJK issues in Textual's stock `Input`:

1. **Scroll splits double-width glyphs** — scroll offsets are snapped to
   character boundaries so a Hangul syllable is never cut in half.
2. **NFD Hangul jams the cursor** — all inserted/pasted text is normalised
   to NFC, so a syllable like "있" (쌍시옷 받침) is always one character,
   not three decomposed jamo code points.

## Contributing

Contributions are welcome once the core structure stabilizes. In the meantime, issues
and discussions are open for ideas, use cases, and feedback.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
