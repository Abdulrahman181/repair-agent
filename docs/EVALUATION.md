# Evaluation protocol

## What is measured

| Metric | Definition |
|---|---|
| Resolved | Hidden tests pass, visible tests pass on pristine test files, and no tampering. This is the headline number. |
| Visible pass | Visible tests pass on pristine test files. |
| Overfit | Visible pass and hidden fail. Counts fixes that satisfy the sample but are wrong in general. |
| Tamper count | Runs where a protected file or a shadowing file changed. Should be 0. |
| Policy violations | Rejected tool calls. A behaviour signal, not a failure by itself. |
| Mean turns, tokens, wall time | Cost indicators per run. Tokens come from the provider's `usage` field and are zero if the provider omits it. |
| Stop reasons | Distribution over `finished`, `max_steps`, `stalled`, and so on. |

The report also breaks results down by category and difficulty and gives a Wilson 95% interval for
the resolve rate.

## How to run

```
python -m repairagent selfcheck
python -m repairagent eval --repeats 3
python -m repairagent compare reports/old.json reports/new.json --max-drop 0.05
```

`selfcheck` needs no model. `eval` needs `LLM_MODEL` and, for hosted providers, an API key.

## Reading the numbers honestly

- There are 13 tasks. A single run has a wide interval: 9 of 13 resolved is 69%, with a Wilson
  interval of about 42% to 87%. Differences of a few points between two models are noise.
- Repeats of the same task are not independent. The reported interval treats runs as independent
  and is therefore too narrow when `--repeats` is above 1. Use it as a rough guide only.
- Temperature defaults to 0, but hosted models are still not perfectly deterministic.
- The tasks are small, single-bug, Python-only exercises written for this project. They are not a
  substitute for SWE-bench style tasks on real repositories, and results do not transfer to them.
- The benchmark text is in this repository. A model may have seen similar bugs in its training
  data. Contamination cannot be ruled out.

## Regression gate

`compare` fails when the candidate's resolve rate drops by more than `--max-drop` points
(default 0.05) and lists the tasks that got worse. It does not test significance. With 13 tasks,
treat a failed gate as a prompt to look at the traces, not as proof.

## What the self-check proves

- Each fixture fails by assertion on the buggy code and passes with the reference fix, for both
  the visible and the hidden suites.
- A scripted agent that applies the reference fix through the real tools resolves every task, so
  the policy, tools, loop and verifier work together on all 13 tasks.
- A null agent resolves none, and an agent that tries to rewrite the tests is stopped.

It does **not** say anything about how well a real model performs.

## Adding a task

Create `benchmarks/tasks/<id>/` with `task.json`, `repo/` (buggy source and visible tests),
`hidden/` (a stricter suite), and `reference/` (the fixed source files). Run
`python -m repairagent selfcheck`. It rejects tasks whose tests fail by import error rather than by
assertion, whose buggy code already passes, or whose reference does not pass everything. Keep the
bug report free of the fix, and keep module names away from standard-library names.

## Results

No model results are published here. Run `eval` and paste the generated Markdown report into this
section with the date, provider and model.
