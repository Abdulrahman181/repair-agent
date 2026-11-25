from __future__ import annotations

import re

from pydantic import BaseModel, Field

from repairagent.sandbox.runner import run_pytest
from repairagent.tools.base import Tool, ToolContext, ToolError, ToolRegistry, ToolResult

MAX_LIST_ENTRIES = 200
MAX_READ_LINES = 300
MAX_READ_BYTES = 500_000
MAX_READ_CHARS = 16_000
MAX_SEARCH_MATCHES = 40
MAX_TEST_OUTPUT_CHARS = 6_000


class ListFilesArgs(BaseModel):
    path: str = Field(".", description="Directory relative to the repository root.")


class ReadFileArgs(BaseModel):
    path: str = Field(description="File path relative to the repository root.")
    start_line: int = Field(1, ge=1, description="First line to read (1-based).")
    end_line: int = Field(
        0, ge=0, description="Last line to read. 0 reads up to 300 lines from start_line."
    )


class SearchArgs(BaseModel):
    pattern: str = Field(min_length=1, description="Python regular expression.")
    path: str = Field(".", description="Directory or file to search in.")


class ReplaceArgs(BaseModel):
    path: str = Field(description="File to edit.")
    old: str = Field(min_length=1, description="Exact text to replace. Must occur exactly once.")
    new: str = Field(description="Replacement text.")


class WriteArgs(BaseModel):
    path: str = Field(description="File to create or overwrite.")
    content: str = Field(description="Complete new file content.")


class RunTestsArgs(BaseModel):
    target: str = Field(
        "", description="Optional test file or directory. Empty runs all visible tests."
    )


class FinishArgs(BaseModel):
    summary: str = Field("", max_length=2000, description="Short description of the fix.")


def _syntax_note(rel: str, text: str) -> str:
    if not rel.endswith(".py"):
        return ""
    try:
        compile(text, rel, "exec")
    except SyntaxError as exc:
        return f" Warning: the file now has a syntax error at line {exc.lineno}: {exc.msg}."
    return ""


def list_files(ctx: ToolContext, args: ListFilesArgs) -> ToolResult:
    base = ctx.workspace.resolve(args.path)
    if not base.exists():
        raise ToolError(f"'{args.path}' does not exist.")
    entries = []
    for index, rel in enumerate(ctx.workspace.iter_files(base)):
        if index >= MAX_LIST_ENTRIES:
            entries.append(f"... more than {MAX_LIST_ENTRIES} files, narrow the path")
            break
        size = (ctx.workspace.root / rel).stat().st_size
        marker = " [read-only]" if ctx.policy.is_protected(rel) else ""
        entries.append(f"{rel} ({size} bytes){marker}")
    return ToolResult(True, "\n".join(entries) or "(no files)")


def read_file(ctx: ToolContext, args: ReadFileArgs) -> ToolResult:
    path = ctx.workspace.resolve(args.path)
    if not path.is_file():
        raise ToolError(f"'{args.path}' is not a file.")
    data = path.read_bytes()
    if len(data) > MAX_READ_BYTES:
        raise ToolError("file is too large to read.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("file is not UTF-8 text.") from exc
    rel = ctx.workspace.rel(path)
    lines = text.splitlines()
    if not lines:
        return ToolResult(True, f"{rel} (empty file)")
    start = args.start_line
    if start > len(lines):
        raise ToolError(f"start_line is beyond the end of the file ({len(lines)} lines).")
    last = args.end_line or start + MAX_READ_LINES - 1
    end = min(last, len(lines), start + MAX_READ_LINES - 1)
    body = "\n".join(f"{number:>4}| {lines[number - 1]}" for number in range(start, end + 1))
    if len(body) > MAX_READ_CHARS:
        body = body[:MAX_READ_CHARS] + "\n...[truncated]"
    return ToolResult(True, f"{rel} lines {start}-{end} of {len(lines)}\n{body}")


def search(ctx: ToolContext, args: SearchArgs) -> ToolResult:
    try:
        regex = re.compile(args.pattern)
    except re.error as exc:
        raise ToolError(f"invalid regular expression: {exc}") from exc
    base = ctx.workspace.resolve(args.path)
    if not base.exists():
        raise ToolError(f"'{args.path}' does not exist.")
    matches: list[str] = []
    for rel in ctx.workspace.iter_files(base):
        if not rel.endswith(".py"):
            continue
        text = (ctx.workspace.root / rel).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{rel}:{number}: {line.strip()[:200]}")
                if len(matches) >= MAX_SEARCH_MATCHES:
                    matches.append(f"... stopped after {MAX_SEARCH_MATCHES} matches")
                    return ToolResult(True, "\n".join(matches))
    return ToolResult(True, "\n".join(matches) or "no matches")


def replace_in_file(ctx: ToolContext, args: ReplaceArgs) -> ToolResult:
    path = ctx.workspace.resolve(args.path)
    rel = ctx.workspace.rel(path)
    ctx.policy.check_path(rel)
    if not path.is_file():
        raise ToolError(f"'{rel}' does not exist. Use write_file to create a new file.")
    text = path.read_text(encoding="utf-8")
    count = text.count(args.old)
    if count == 0:
        raise ToolError(
            "'old' was not found. It must match exactly, including whitespace. "
            "Use read_file and copy the text."
        )
    if count > 1:
        raise ToolError(
            f"'old' matches {count} places. Include more surrounding lines to make it unique."
        )
    updated = text.replace(args.old, args.new, 1)
    ctx.policy.check_budget(len(updated.encode("utf-8")), ctx.state.edits)
    path.write_text(updated, encoding="utf-8")
    ctx.state.edits += 1
    ctx.state.edit_version += 1
    ctx.state.files_changed.add(rel)
    delta = args.new.count("\n") - args.old.count("\n")
    return ToolResult(
        True,
        f"Edited {rel}: replaced 1 occurrence ({delta:+d} lines)." + _syntax_note(rel, updated),
    )


def write_file(ctx: ToolContext, args: WriteArgs) -> ToolResult:
    path = ctx.workspace.resolve(args.path)
    rel = ctx.workspace.rel(path)
    ctx.policy.check_write(rel, len(args.content.encode("utf-8")), ctx.state.edits)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"could not write '{rel}': {type(exc).__name__}") from exc
    ctx.state.edits += 1
    ctx.state.edit_version += 1
    ctx.state.files_changed.add(rel)
    return ToolResult(
        True,
        f"Wrote {rel} ({len(args.content.splitlines())} lines)." + _syntax_note(rel, args.content),
    )


def run_tests(ctx: ToolContext, args: RunTestsArgs) -> ToolResult:
    if ctx.state.test_runs >= ctx.max_test_runs:
        raise ToolError("Test run budget exhausted. Call finish with your best fix.")
    targets: tuple[str, ...] = ()
    if args.target:
        target = ctx.workspace.resolve(args.target)
        if not target.exists():
            raise ToolError(f"'{args.target}' does not exist.")
        targets = (ctx.workspace.rel(target),)
    ctx.state.test_runs += 1
    result, summary = run_pytest(ctx.workspace.root, targets, ctx.sandbox)
    ctx.state.last_tests = summary
    header = (
        f"exit_code={result.exit_code} passed={summary.passed} "
        f"failed={summary.failed} errors={summary.errors}"
    )
    if result.timed_out:
        header += " TIMED_OUT"
    output = result.output
    if len(output) > MAX_TEST_OUTPUT_CHARS:
        output = output[:MAX_TEST_OUTPUT_CHARS] + "\n...[truncated]"
    return ToolResult(True, f"{header}\n{output}", data={"all_passed": summary.ok})


def finish(ctx: ToolContext, args: FinishArgs) -> ToolResult:
    return ToolResult(True, "Finished.", terminal=True, data={"summary": args.summary})


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                "list_files",
                "List files in a directory of the repository. Read-only files are marked.",
                ListFilesArgs,
                list_files,
            ),
            Tool(
                "read_file",
                "Read a text file with line numbers.",
                ReadFileArgs,
                read_file,
            ),
            Tool(
                "search",
                "Search Python files with a regular expression.",
                SearchArgs,
                search,
            ),
            Tool(
                "replace_in_file",
                "Replace one exact occurrence of text in a source file.",
                ReplaceArgs,
                replace_in_file,
            ),
            Tool(
                "write_file",
                "Create or overwrite a source file with complete content.",
                WriteArgs,
                write_file,
            ),
            Tool(
                "run_tests",
                "Run the visible tests and return the result.",
                RunTestsArgs,
                run_tests,
            ),
            Tool(
                "finish",
                "End the task once the fix is complete.",
                FinishArgs,
                finish,
            ),
        ]
    )
