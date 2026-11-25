from __future__ import annotations

import os
from pathlib import Path

import pytest

from repairagent.policy import Policy, PolicyViolation
from repairagent.sandbox.workspace import PathEscape, Workspace


@pytest.fixture
def ws(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "junk.pyc").write_bytes(b"\x00")
    return Workspace(root)


def test_resolve_inside(ws: Workspace):
    assert ws.resolve("pkg/mod.py") == ws.root / "pkg" / "mod.py"
    assert ws.resolve(".") == ws.root


@pytest.mark.parametrize("bad", ["../outside.py", "pkg/../../outside.py", "", "   ", "a\x00b"])
def test_rejects_traversal_and_invalid(ws: Workspace, bad: str):
    with pytest.raises(PathEscape):
        ws.resolve(bad)


def test_rejects_absolute_path(ws: Workspace, tmp_path: Path):
    with pytest.raises(PathEscape):
        ws.resolve(str(tmp_path / "other.py"))


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_rejects_symlink_escape(ws: Workspace, tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (ws.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscape):
        ws.resolve("link/secret.txt")


def test_iter_files_skips_ignored_directories(ws: Workspace):
    assert list(ws.iter_files()) == ["pkg/mod.py"]


def test_hash_files_uses_predicate(ws: Workspace):
    hashes = ws.hash_files(lambda rel: rel.endswith(".py"))
    assert list(hashes) == ["pkg/mod.py"]
    assert len(hashes["pkg/mod.py"]) == 64


def test_from_template_copies_and_cleans_up(ws: Workspace):
    copy = Workspace.from_template(ws.root)
    try:
        assert (copy.root / "pkg" / "mod.py").is_file()
        assert not (copy.root / "__pycache__").exists()
        assert copy.root != ws.root
    finally:
        copy.cleanup()
    assert not copy.root.exists()


def test_cleanup_does_not_delete_borrowed_root(ws: Workspace):
    ws.cleanup()
    assert ws.root.exists()


@pytest.mark.parametrize(
    "rel",
    [
        "tests/test_a.py",
        "tests/sub/helper.py",
        "test_root.py",
        "pkg/test_inner.py",
        "pkg/inner_test.py",
        "conftest.py",
        "pkg/conftest.py",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        "pyproject.toml",
        "sitecustomize.py",
        "usercustomize.py",
        "Tests/test_a.py",
        "TESTS/Helper.py",
        "CONFTEST.PY",
    ],
)
def test_protected_paths(rel: str):
    assert Policy().is_protected(rel)


@pytest.mark.parametrize("rel", ["pager.py", "pkg/mod.py", "src/helpers.py", "latest.py"])
def test_regular_source_is_not_protected(rel: str):
    assert not Policy().is_protected(rel)


def test_check_write_blocks_protected_file():
    with pytest.raises(PolicyViolation, match="protected"):
        Policy().check_write("tests/test_a.py", 10, 0)


def test_check_write_blocks_non_python_suffix():
    with pytest.raises(PolicyViolation, match="only"):
        Policy().check_write("notes.txt", 10, 0)


@pytest.mark.parametrize(
    "rel", ["pytest.py", "os.py", "json/decoder.py", "_pytest/x.py", "unittest.py"]
)
def test_check_write_blocks_module_shadowing(rel: str):
    with pytest.raises(PolicyViolation, match="shadow"):
        Policy().check_write(rel, 10, 0)


def test_check_write_enforces_size_and_edit_budget():
    policy = Policy(max_file_bytes=100, max_edits=2)
    with pytest.raises(PolicyViolation, match="exceed"):
        policy.check_write("a.py", 101, 0)
    with pytest.raises(PolicyViolation, match="edit budget"):
        policy.check_write("a.py", 10, 2)
    policy.check_write("a.py", 10, 1)


def test_nested_new_module_is_allowed():
    Policy().check_write("pkg/new_module.py", 10, 0)
