from __future__ import annotations

import fnmatch
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

RESERVED_MODULES = frozenset(set(sys.stdlib_module_names) | {"pytest", "_pytest", "pluggy", "py"})

DEFAULT_PROTECTED = (
    "tests/*",
    "test/*",
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "pyproject.toml",
    "sitecustomize.py",
    "usercustomize.py",
)


class PolicyViolation(Exception):
    pass


@dataclass(frozen=True)
class Policy:
    protected_patterns: tuple[str, ...] = DEFAULT_PROTECTED
    writable_suffixes: tuple[str, ...] = (".py",)
    max_file_bytes: int = 200_000
    max_edits: int = 30

    def is_protected(self, rel: str) -> bool:
        lowered = rel.lower()
        name = PurePosixPath(lowered).name
        return any(
            fnmatch.fnmatchcase(lowered, pattern) or fnmatch.fnmatchcase(name, pattern)
            for pattern in self.protected_patterns
        )

    def shadowed_module(self, rel: str) -> str | None:
        top = PurePosixPath(rel.lower()).parts[0]
        stem = top[:-3] if top.endswith(".py") else top
        return stem if stem in RESERVED_MODULES else None

    def check_path(self, rel: str) -> None:
        if self.is_protected(rel):
            raise PolicyViolation(f"'{rel}' is protected and read-only")
        if PurePosixPath(rel.lower()).suffix not in self.writable_suffixes:
            allowed = ", ".join(self.writable_suffixes)
            raise PolicyViolation(f"only {allowed} files may be written, got '{rel}'")
        shadowed = self.shadowed_module(rel)
        if shadowed:
            raise PolicyViolation(f"'{rel}' would shadow the reserved module '{shadowed}'")

    def check_budget(self, new_size: int, edits_so_far: int) -> None:
        if new_size > self.max_file_bytes:
            raise PolicyViolation(f"file would exceed {self.max_file_bytes} bytes")
        if edits_so_far >= self.max_edits:
            raise PolicyViolation(f"edit budget of {self.max_edits} exhausted")

    def check_write(self, rel: str, new_size: int, edits_so_far: int) -> None:
        self.check_path(rel)
        self.check_budget(new_size, edits_so_far)
