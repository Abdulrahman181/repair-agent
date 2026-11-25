from __future__ import annotations

from collections.abc import Callable

import pytest

from repairagent.llm.base import ToolCall
from repairagent.tools import ToolContext, ToolRegistry, ToolResult

Invoke = Callable[..., ToolResult]


def test_specs_are_well_formed(registry: ToolRegistry):
    specs = registry.specs()
    names = [spec["function"]["name"] for spec in specs]
    assert names == [
        "list_files",
        "read_file",
        "search",
        "replace_in_file",
        "write_file",
        "run_tests",
        "finish",
    ]
    for spec in specs:
        assert spec["type"] == "function"
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert "title" not in params
        assert all("title" not in prop for prop in params["properties"].values())
        assert spec["function"]["description"]
    replace = next(s for s in specs if s["function"]["name"] == "replace_in_file")
    assert set(replace["function"]["parameters"]["required"]) == {"path", "old", "new"}


def test_list_files_marks_read_only(invoke: Invoke):
    result = invoke("list_files")
    assert result.ok
    assert "pager.py" in result.text
    assert "tests/test_pager.py" in result.text
    line = next(line for line in result.text.splitlines() if "test_pager.py" in line)
    assert "[read-only]" in line
    source = next(line for line in result.text.splitlines() if line.startswith("pager.py"))
    assert "[read-only]" not in source


def test_list_files_hides_hidden_tests(invoke: Invoke):
    result = invoke("list_files")
    assert "hidden" not in result.text.lower()


def test_list_files_missing_directory(invoke: Invoke):
    result = invoke("list_files", path="nope")
    assert not result.ok
    assert "does not exist" in result.text


def test_read_file_numbers_lines(invoke: Invoke):
    result = invoke("read_file", path="pager.py")
    assert result.ok
    assert "   1| def paginate" in result.text
    assert "lines 1-" in result.text


def test_read_file_range(invoke: Invoke):
    result = invoke("read_file", path="pager.py", start_line=2, end_line=3)
    assert result.ok
    assert "lines 2-3" in result.text
    assert "   1|" not in result.text


def test_read_file_start_beyond_end(invoke: Invoke):
    result = invoke("read_file", path="pager.py", start_line=999)
    assert not result.ok
    assert "beyond" in result.text


def test_read_file_rejects_binary(invoke: Invoke, ctx: ToolContext):
    (ctx.workspace.root / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    result = invoke("read_file", path="blob.bin")
    assert not result.ok
    assert "UTF-8" in result.text


def test_read_file_empty(invoke: Invoke, ctx: ToolContext):
    (ctx.workspace.root / "empty.py").write_text("", encoding="utf-8")
    assert "empty file" in invoke("read_file", path="empty.py").text


@pytest.mark.parametrize("path", ["../x.py", "/etc/passwd", "tests/../../x"])
def test_read_file_path_escape_is_policy_violation(invoke: Invoke, path: str):
    result = invoke("read_file", path=path)
    assert not result.ok
    assert result.policy_violation


def test_search_finds_matches(invoke: Invoke):
    result = invoke("search", pattern=r"def \w+")
    assert "pager.py:1: def paginate" in result.text
    assert "tests/test_pager.py" in result.text


def test_search_no_match_and_bad_regex(invoke: Invoke):
    assert invoke("search", pattern="zzzzzz").text == "no matches"
    bad = invoke("search", pattern="(")
    assert not bad.ok and "regular expression" in bad.text


def test_replace_in_file_success(invoke: Invoke, ctx: ToolContext):
    result = invoke(
        "replace_in_file",
        path="pager.py",
        old="start = page * per_page",
        new="start = (page - 1) * per_page",
    )
    assert result.ok, result.text
    assert "(page - 1)" in (ctx.workspace.root / "pager.py").read_text(encoding="utf-8")
    assert ctx.state.edits == 1
    assert ctx.state.edit_version == 1
    assert ctx.state.files_changed == {"pager.py"}


def test_replace_requires_exact_unique_match(invoke: Invoke):
    missing = invoke("replace_in_file", path="pager.py", old="not present", new="x")
    assert not missing.ok and "not found" in missing.text
    ambiguous = invoke("replace_in_file", path="pager.py", old="page", new="p")
    assert not ambiguous.ok and "matches" in ambiguous.text


def test_replace_in_protected_file_is_violation(invoke: Invoke, ctx: ToolContext):
    before = (ctx.workspace.root / "tests" / "test_pager.py").read_text(encoding="utf-8")
    result = invoke("replace_in_file", path="tests/test_pager.py", old="== [0, 1, 2]", new="== []")
    assert result.policy_violation
    assert "protected" in result.text
    after = (ctx.workspace.root / "tests" / "test_pager.py").read_text(encoding="utf-8")
    assert before == after
    assert ctx.state.edits == 0


def test_replace_reports_syntax_error(invoke: Invoke):
    result = invoke("replace_in_file", path="pager.py", old="start = page", new="start = = page")
    assert result.ok
    assert "syntax error" in result.text


def test_replace_unknown_file(invoke: Invoke):
    result = invoke("replace_in_file", path="missing.py", old="a", new="b")
    assert not result.ok and "write_file" in result.text


def test_write_file_creates_module(invoke: Invoke, ctx: ToolContext):
    result = invoke("write_file", path="helpers/util.py", content="VALUE = 1\n")
    assert result.ok
    assert (ctx.workspace.root / "helpers" / "util.py").read_text(encoding="utf-8") == "VALUE = 1\n"


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_pager.py",
        "tests/test_new.py",
        "conftest.py",
        "pytest.ini",
        "notes.txt",
        "pytest.py",
        "os.py",
        "Tests/test_pager.py",
    ],
)
def test_write_file_policy_blocks(invoke: Invoke, ctx: ToolContext, path: str):
    result = invoke("write_file", path=path, content="x = 1\n")
    assert result.policy_violation, result.text
    assert ctx.state.edits == 0
    assert not (ctx.workspace.root / "conftest.py").exists()


def test_write_file_size_limit(invoke: Invoke):
    result = invoke("write_file", path="big.py", content="x = 1\n" * 100_000)
    assert result.policy_violation
    assert "exceed" in result.text


def test_edit_budget_is_enforced(invoke: Invoke, ctx: ToolContext):
    ctx.state.edits = ctx.policy.max_edits
    result = invoke("write_file", path="a.py", content="x = 1\n")
    assert result.policy_violation
    assert "edit budget" in result.text


def test_run_tests_reports_failures(invoke: Invoke, ctx: ToolContext):
    result = invoke("run_tests")
    assert result.ok
    assert "failed=" in result.text
    assert result.data["all_passed"] is False
    assert ctx.state.test_runs == 1
    assert ctx.state.last_tests is not None and ctx.state.last_tests.failed > 0


def test_run_tests_after_fix_passes(invoke: Invoke):
    invoke(
        "replace_in_file",
        path="pager.py",
        old="start = page * per_page",
        new="start = (page - 1) * per_page",
    )
    result = invoke("run_tests")
    assert result.data["all_passed"] is True
    assert "failed=0" in result.text


def test_run_tests_with_target(invoke: Invoke):
    result = invoke("run_tests", target="tests/test_pager.py")
    assert result.ok and "passed=" in result.text
    missing = invoke("run_tests", target="tests/none.py")
    assert not missing.ok


def test_run_tests_budget(invoke: Invoke, ctx: ToolContext):
    ctx.max_test_runs = 1
    assert invoke("run_tests").ok
    second = invoke("run_tests")
    assert not second.ok and "budget" in second.text


def test_finish_is_terminal(invoke: Invoke):
    result = invoke("finish", summary="done")
    assert result.terminal and result.data["summary"] == "done"


def test_invalid_arguments_are_reported(registry: ToolRegistry, ctx: ToolContext):
    call = ToolCall("1", "read_file", {"start_line": 0}, "{}")
    result = registry.execute(call, ctx)
    assert not result.ok
    assert "Invalid arguments" in result.text
    assert "path" in result.text


def test_unknown_tool(registry: ToolRegistry, ctx: ToolContext):
    result = registry.execute(ToolCall("1", "rm_rf", {}, "{}"), ctx)
    assert not result.ok and "Unknown tool" in result.text and "read_file" in result.text


def test_parse_error_is_reported(registry: ToolRegistry, ctx: ToolContext):
    call = ToolCall("1", "read_file", None, "{broken", "invalid JSON (Expecting value)")
    result = registry.execute(call, ctx)
    assert not result.ok and "Could not parse" in result.text


def test_unexpected_exception_does_not_crash(registry: ToolRegistry, ctx: ToolContext, monkeypatch):
    import repairagent.tools.builtin as builtin

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret detail that must not leak")

    monkeypatch.setattr(builtin, "run_pytest", boom)
    result = registry.execute(ToolCall("1", "run_tests", {}, "{}"), ctx)
    assert not result.ok
    assert "Internal tool error: RuntimeError" in result.text
    assert "secret detail" not in result.text
