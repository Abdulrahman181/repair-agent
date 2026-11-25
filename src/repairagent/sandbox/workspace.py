from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path, PurePath

IGNORED_DIRS = frozenset({"__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".venv"})


class PathEscape(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path, owns_root: bool = False) -> None:
        self.root = Path(root).resolve()
        self._owns_root = owns_root

    @classmethod
    def from_template(cls, template: Path) -> Workspace:
        root = Path(tempfile.mkdtemp(prefix="repairagent_"))
        shutil.copytree(
            template,
            root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*IGNORED_DIRS),
        )
        return cls(root, owns_root=True)

    def clone(self) -> Workspace:
        return Workspace.from_template(self.root)

    def resolve(self, rel: str) -> Path:
        if not isinstance(rel, str) or not rel.strip() or "\x00" in rel:
            raise PathEscape("invalid path")
        pure = PurePath(rel)
        if pure.is_absolute() or pure.drive or pure.root:
            raise PathEscape(f"absolute paths are not allowed: '{rel}'")
        candidate = (self.root / rel).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PathEscape(f"path escapes the repository: '{rel}'")
        return candidate

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def iter_files(self, base: Path | None = None) -> Iterator[str]:
        start = base or self.root
        if start.is_file():
            yield self.rel(start)
            return
        for current, dirs, files in os.walk(start):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
            for name in sorted(files):
                yield self.rel(Path(current) / name)

    def hash_files(self, predicate: Callable[[str], bool]) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for rel in self.iter_files():
            if predicate(rel):
                hashes[rel] = hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
        return hashes

    def cleanup(self) -> None:
        if self._owns_root:
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> Workspace:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.cleanup()
