# RepairAgent

A code-repair agent that fixes bugs in small Python repositories through a fixed tool set, plus a
reproducible harness that scores it against **hidden** tests. It uses no agent framework: the
decision loop, tool registry, policy, sandbox runner and verifier are written from scratch and talk
to any OpenAI-compatible chat endpoint (Groq, Ollama, OpenAI).

The point of the project is the evaluation discipline. An agent that makes the visible tests pass
has not necessarily fixed the bug, so success here means passing a separate hidden suite without
touching the tests.

## Status

| Item | State |
|---|---|
| Agent loop, tools, policy, sandbox, verifier | implemented and tested |
| 13-task benchmark with validated fixtures | implemented |
| Harness self-check (no model needed) | passes: oracle 13/13, null agent 0/13, test tampering blocked 13/13 |
| Test suite | 219 tests passing on Linux with Python 3.11, 3.12 and 3.13, 96% line coverage on 3.13 |
| **Live evaluation against a real model** | **not run yet, no API key was available when this was built** |
| Windows execution | code paths exist but were **not executed**, CI is configured but had not been run |

No accuracy number for any model is claimed. Run `eval` yourself and publish the report it writes.

## Quick start (VS Code, Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m repairagent selfcheck
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope Process Bypass` first.
On Linux or macOS use `python3 -m venv .venv && source .venv/bin/activate`.

Open the folder in VS Code and accept the extension recommendations. The `.vscode` folder provides
a test runner setup, a formatter, and launch configurations for the self-check, a single task, and
a full evaluation.

To run against a model:

```powershell
copy .env.example .env
notepad .env
python -m repairagent run paginate-off-by-one
python -m repairagent eval --repeats 3
```

The default provider is Groq. Model ids change, so set `LLM_MODEL` after checking
<https://console.groq.com/docs/models> and confirming the model supports tool calling. A local
Ollama model also works (`LLM_PROVIDER=ollama`) but small models call tools unreliably.

## Commands

| Command | Purpose |
|---|---|
| `tasks` | List benchmark tasks |
| `selfcheck` | Validate every fixture and the harness itself, no model needed |
| `run TASK` | Run the agent on one task and print the outcome |
| `eval [--task ID]... [--repeats N]` | Run the benchmark, write JSON and Markdown reports to `reports/` |
| `compare BASE.json CAND.json [--max-drop 0.05]` | Regression gate between two reports |
| `trace RUN_ID` | Print the recorded steps of a run |

## How it works

```
bug report -> loop -> model -> tool call -> policy -> tool -> observation -> loop ...
                                                              |
                          final workspace -> verifier (visible + hidden tests, tamper check)
```

- **Loop** (`agent/loop.py`): inspects budgets, asks the model for the next action, executes up to
  four tool calls, feeds failures back as text, detects repeated actions, and stops for one of
  eight reasons.
- **Tools**: `list_files`, `read_file`, `search`, `replace_in_file`, `write_file`, `run_tests`,
  `finish`. Specs are generated from pydantic models.
- **Policy** (`policy.py`): tests and configuration are read-only, only `.py` files can be written,
  names that would shadow `pytest` or the standard library are rejected, paths cannot leave the
  workspace. It is enforced outside the model, so a prompt-injected model still cannot cheat.
- **Sandbox** (`sandbox/`): tests run in a subprocess with a scrubbed environment, a timeout with
  process-tree kill, capped output, and CPU, memory and file-size limits on POSIX.
- **Verifier** (`verify.py`): works on a clone of the final state, restores the original tests,
  removes files that shadow reserved modules, then runs visible and hidden tests.
- **Store** (`store.py`): every run and step goes to SQLite for inspection.

See `docs/ARCHITECTURE.md` for detail.

## Benchmark

13 original tasks, each a small module with a realistic bug, visible tests that fail, a stricter
hidden suite, and a reference fix.

| Difficulty | Tasks |
|---|---|
| easy | paginate-off-by-one, slugify-separators, moving-average-window, split-bill-remainder, business-days-bounds |
| medium | merge-intervals, lru-cache-recency, deep-merge-mutation, top-words-ordering, retry-attempts, cart-discount-pricing (multi-file) |
| hard | atomic-transfer, csv-line-quotes |

Categories include off-by-one, state, parsing, error handling and boundaries, and one Arabic text
case. Fixture validation requires each buggy repository to fail by assertion (not by import error)
and each reference fix to pass everything.

## Design decisions

- **Hidden tests over visible tests.** Visible tests are a sample; a hardcoded answer passes them
  and fails the hidden suite. `overfit` is reported as its own metric.
- **Policy outside the model.** The test suite includes a prompt-injection case where the scripted
  model obeys a malicious comment and is still blocked.
- **Exact-match edits.** More reliable for models than unified diffs, at the cost of an occasional
  retry.
- **Single agent.** There is no evidence yet that a planner and critic would pay for themselves.
  The harness exists to answer that with data.
- **No framework.** A direct HTTP client keeps the behaviour inspectable and fully testable with a
  mocked transport.

## Limitations

- Not a security boundary: generated code runs as your user with network access. Use a container
  or VM for untrusted code. See `docs/THREAT_MODEL.md`.
- Hidden tests are present in the verification clone, so deliberately malicious code could read
  them. The design stops accidental and naive cheating, not exfiltration.
- Small, synthetic, single-bug tasks. Results do not predict performance on real repositories.
- 13 tasks give wide confidence intervals. See `docs/EVALUATION.md`.
- Groq's `tool_use_failed` handling was verified against a mocked response only.

## Tests

```powershell
python -m pytest
python -m ruff check src tests
```

The suite uses a scripted model, so it needs no network or key. It includes adversarial tests for
tampering, an injected `conftest.py`, a module shadowing `pytest`, prompt injection, path traversal,
and runaway processes.

## License

MIT. Benchmark tasks are original work.
