# Architecture

## Components

```
                +-----------------+        +--------------------+
  bug report -> |   RepairAgent   | <----> |  LLMClient         |  OpenAI-compatible HTTP
                |   (loop.py)     |        |  (Groq/Ollama/...) |  or ScriptedClient in tests
                +--------+--------+        +--------------------+
                         |
              tool call  |  result
                         v
                +-----------------+     +------------------+
                |  ToolRegistry   | --> |  Policy          |  protected paths, write rules
                |  7 tools        |     +------------------+
                +--------+--------+
                         |
            +------------+-------------+
            v                          v
   +-----------------+        +-------------------+
   |  Workspace      |        |  Sandbox runner   |  subprocess, scrubbed env, limits
   |  (jailed temp   |        |  pytest           |
   |   copy of repo) |        +-------------------+
   +--------+--------+
            |  final state
            v
   +-----------------+        +-------------------+
   |  Verifier       | -----> |  RunStore (SQLite)|
   |  hidden tests   |        +-------------------+
   +-----------------+
```

The model never sees the hidden tests. The verifier works on a fresh clone of the final workspace,
restores the original protected files, removes files that shadow reserved modules, then runs the
visible tests and the hidden tests.

## Decision loop

Each iteration:

1. Check the budgets (steps, tokens, wall clock). Stop if one is exhausted.
2. Call the model with the conversation and the tool specifications.
3. Recoverable errors:
   - A malformed tool call from the provider (`tool_use_failed`) or a reply with no tool call adds
     a short corrective message. Three in a row end the run with `no_tool_calls`.
   - Any other client error ends the run with `llm_error`.
4. Execute at most four tool calls from the reply. Each goes through argument validation, the
   policy, and the handler. Failures are returned to the model as text, not raised.
5. Track repeated identical actions that happen with no edit in between. The second repeat appends
   a hint, the third stops the run with `stalled`.
6. Stop on `finish`, on three policy violations, or continue.

Stop reasons: `finished`, `max_steps`, `max_tokens`, `timeout`, `stalled`, `no_tool_calls`,
`llm_error`, `policy_violations`. Verification runs after every stop reason, so an agent that ran
out of budget but left a correct fix is still scored correctly.

## Tools

| Tool | Purpose |
|---|---|
| `list_files` | Directory listing. Protected files are marked `[read-only]`. |
| `read_file` | Numbered lines, at most 300 per call. |
| `search` | Regex search over `.py` files. |
| `replace_in_file` | Replace one exact, unique occurrence. |
| `write_file` | Create or overwrite a `.py` file. |
| `run_tests` | Run the visible tests. Limited by a run budget. |
| `finish` | End the task. The summary is optional. |

Tool specifications are generated from pydantic models, with titles stripped to save tokens.

## Verification

`resolved` is true only when all of these hold:

- the visible tests pass on the agent's source with pristine test files restored,
- the hidden tests pass,
- no protected file was changed, added or deleted, and no file shadows a reserved module.

`overfit` is reported separately: visible tests pass and hidden tests fail.

A passing run requires at least one passed test and exit code 0, so deleting all tests cannot
produce a pass (pytest exits with code 5 when nothing is collected).

## Stored data

See the schema in `PLAN.md`. Large arguments and results are clipped when stored (2000 and 500
characters). Nothing from the environment is stored.
