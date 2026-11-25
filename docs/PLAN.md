# Project plan

## Goal

Build a code-repair agent whose success is measured by independent, hidden tests rather than by the
tests it can see, together with a reproducible harness that turns any model into a comparable
number. The agent is the means; the evaluation discipline is the product.

## Requirements

Functional

- Accept a bug report and a small Python repository, then read, search, edit and test it through a
  fixed set of tools.
- Decide the next action in a loop, validate it against a policy, observe the result, and stop on
  success, budget exhaustion, a stall, or repeated policy violations.
- Verify the final state with the visible tests and a hidden suite, and flag any tampering.
- Persist every run and every step for later inspection.
- Run a benchmark, aggregate the results, and compare two reports with a regression gate.

Non-functional

- No agent framework. Tool calling over plain HTTP to any OpenAI-compatible endpoint.
- Runs on a CPU-only laptop with 8 GB of RAM. No GPU, no Docker required.
- Works from VS Code on Windows and on Linux.
- Every claim in the documentation is backed by a test or a command that can be re-run.

## Architecture

See `ARCHITECTURE.md`. In short: a loop (`agent/loop.py`) talks to a model through an LLM client,
executes tool calls through a registry guarded by a policy, runs tests in a subprocess sandbox, and
hands the final workspace to a verifier. An evaluation harness drives the loop over a benchmark.

## Technology choices

| Choice | Why | Trade-off |
|---|---|---|
| httpx against `/chat/completions` | One client covers Groq, Ollama and OpenAI. Fully testable with `httpx.MockTransport`. | No provider-specific features such as streaming or JSON-schema modes. |
| pydantic for tool arguments | Validation errors become model-readable feedback, and tool specs are generated from the same models. | Schemas are kept simple (no `Optional`) because several providers reject `anyOf` with null. |
| Exact-match `replace_in_file` plus `write_file` | Exact replacement is more reliable for models than unified diffs. | Costs an extra step when the model mis-copies whitespace. |
| SQLite for traces | Zero setup, one file, easy to query. | Single writer, which is fine for sequential evaluation. |
| pytest subprocess as the sandbox | Portable and simple. | Not a security boundary, see `THREAT_MODEL.md`. |
| Single agent, no planner/critic split | No evidence yet that a second agent pays for its cost and complexity. | May leave quality on the table. The harness is built to test exactly that question later. |

## Folder structure

```
src/repairagent/
  config.py          settings and budgets
  llm/               client protocol, OpenAI-compatible client, scripted client for tests
  sandbox/           jailed workspace, subprocess runner with limits
  policy.py          protected paths, write rules, module-shadowing guard
  tools/             tool registry and the seven built-in tools
  agent/             prompts and the decision loop
  verify.py          hidden-test verification and tamper detection
  tasks.py           benchmark task loading
  store.py           SQLite traces
  eval/              harness, metrics, report, self-check, scripted baselines
  cli.py             command line interface
benchmarks/tasks/    13 tasks: repo/, hidden/, reference/, task.json
tests/               unit and integration tests
docs/                this folder
```

## Data design

`runs(id, task_id, started_at, ended_at, provider, model, stop_reason, resolved, visible_pass,
hidden_pass, tampered, steps, prompt_tokens, completion_tokens, policy_violations, wall_s, summary,
meta_json)`

`steps(id, run_id, idx, kind, tool, args_json, result_preview, ok, policy_violation, latency_s,
prompt_tokens, completion_tokens)` with an index on `(run_id, idx)`.

## Interface design

A command line interface, not a REST API. The agent runs for minutes and writes files, so a
long-lived service adds no value here. Commands: `tasks`, `selfcheck`, `run`, `eval`, `compare`,
`trace`.

## Roadmap and milestones

| Milestone | Content | Status |
|---|---|---|
| M1 | LLM client, sandbox, policy, tools | done |
| M2 | Decision loop with budgets and stall detection | done |
| M3 | Hidden-test verification and tamper detection | done |
| M4 | 13-task benchmark with validated fixtures | done |
| M5 | Evaluation harness, reports, regression gate, self-check | done |
| M6 | Live evaluation against a real model, published numbers | **not done, needs an API key** |
| M7 | Container sandbox with network isolation | not started |
| M8 | Planner/critic comparison using the harness | not started |

## Testing strategy

- Unit tests for every module, with the model replaced by a scripted client so loop behaviour is
  deterministic.
- Adversarial tests: tampering with tests, injected `conftest.py`, a module that shadows `pytest`,
  prompt injection inside source files, path traversal and symlink escape.
- Fixture validation: every task must fail its visible and hidden tests by assertion on the buggy
  code and pass both with the reference fix. Tests also prove the validator catches broken fixtures.
- Harness self-check: a scripted oracle must resolve every task, a null agent none, and a cheating
  agent must be blocked.

## Deployment plan

Local use from VS Code through `pip install -e ".[dev]"`. CI runs lint, tests and the self-check on
Linux and Windows for Python 3.11 to 3.13. A container image and an isolated execution backend are
roadmap items, not shipped.
