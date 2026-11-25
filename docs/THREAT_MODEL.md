# Threat model

## What this protects

The goal is a trustworthy evaluation number and a safe local run. The adversary is a model that is
careless, over-eager to make tests pass, or steered by text it read in a file. It is **not** a
determined attacker with a code-execution exploit.

## Controls and how each is tested

| Threat | Control | Test |
|---|---|---|
| Editing tests to make them pass | Protected path patterns, case-insensitive. Writes are rejected. | `test_tools.py::test_write_file_policy_blocks`, `test_loop.py::test_repeated_policy_violations_stop_the_run` |
| Tests changed by some other route | Hashes of protected files taken at start and compared at the end. Originals are restored before verification. | `test_verify.py::test_modified_test_file_is_flagged_and_restored` and neighbours |
| Injected `conftest.py` forcing passes | Protected, deleted from the verification clone. The test shows the attack really does pass in the agent workspace. | `test_verify.py::test_injected_conftest_is_neutralised` |
| A file named `pytest.py` or a `pluggy/` package shadowing the test runner | Writes to reserved module names are rejected. Such files are deleted from the verification clone and reported as tampering. | `test_verify.py::test_module_shadowing_pytest_is_neutralised` |
| Hardcoding the visible expectations | Hidden test suite that exercises other inputs. | `test_verify.py::test_overfitting_to_visible_tests_is_caught_by_hidden_tests` |
| Prompt injection inside a source file | The policy is enforced outside the model, so obeying the injection still fails. | `test_loop.py::test_prompt_injection_in_source_cannot_edit_tests` |
| Path traversal, absolute paths, symlink escape | Every path is resolved and checked to be inside the workspace. | `test_workspace_policy.py` |
| Infinite loops and runaway memory in generated code | Timeout with process-group kill. On POSIX also CPU, memory and file-size limits. | `test_runner.py` |
| Leaking API keys to generated code | The child process gets a minimal environment built from scratch. | `test_runner.py::test_secrets_do_not_reach_child_process` |
| Output flooding | Captured to a temp file and truncated in the middle. | `test_runner.py::test_output_is_truncated_with_marker` |
| Endless agent loops | Step, token and wall-clock budgets, stall detection, violation limit. | `test_loop.py` |
| API key in error messages or traces | Keys are only placed in the request header. Error text is limited to the status and a body excerpt. | `test_llm_client.py::test_client_errors_are_not_retried_and_do_not_leak_key` |

## Known limitations

These are real and not hidden by the tests.

1. **Not a security boundary.** Generated code runs as the current user, with network access, in a
   subprocess. Do not run the benchmark on untrusted code. A container or VM backend with no
   network is the planned fix.
2. **Hidden tests are readable at verification time.** The verifier copies the hidden tests into
   the clone while the agent's code runs. Source code written by the agent could read them. This
   defends against accidental overfitting and naive cheating, not against deliberate
   exfiltration. Running verification in an isolated process with the tests mounted read-only and
   out of reach is the planned fix.
3. **Windows limits are weaker.** Memory and CPU limits use `resource`, which does not exist on
   Windows. There, only the timeout and process-tree kill apply. The Windows code paths
   (`taskkill`, process-group flags) were **not executed** in the authoring environment, which was
   Linux. CI is configured to run on Windows but had not been run when this was written.
4. **Resource limits are best effort.** `RLIMIT_AS` can behave differently across platforms and
   limit failures are ignored rather than aborting the run.
5. **Model-side risks are out of scope.** Provider data handling and the content of prompts are
   the operator's responsibility. Do not put proprietary code into a hosted model without
   permission.
