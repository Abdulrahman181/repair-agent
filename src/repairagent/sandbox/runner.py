from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = os.name == "nt"
WINDOWS_ENV_KEYS = ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "PATHEXT", "COMSPEC")


@dataclass(frozen=True)
class SandboxConfig:
    timeout_s: float = 20.0
    max_output_bytes: int = 24_000
    memory_mb: int = 2048
    max_file_mb: int = 50


@dataclass(frozen=True)
class RunResult:
    exit_code: int | None
    output: str
    timed_out: bool
    duration_s: float
    truncated: bool


@dataclass(frozen=True)
class PytestSummary:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    exit_code: int | None = None
    timed_out: bool = False

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.passed > 0 and not self.timed_out


def scrubbed_env() -> dict[str, str]:
    env = {
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if IS_WINDOWS:
        for key in WINDOWS_ENV_KEYS:
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def _posix_limits(config: SandboxConfig) -> Callable[[], None]:
    def apply() -> None:
        import resource

        limits = (
            (resource.RLIMIT_CPU, int(config.timeout_s) + 5),
            (resource.RLIMIT_AS, config.memory_mb * 1024 * 1024),
            (resource.RLIMIT_FSIZE, config.max_file_mb * 1024 * 1024),
            (resource.RLIMIT_CORE, 0),
        )
        for which, value in limits:
            try:
                resource.setrlimit(which, (value, value))
            except (ValueError, OSError):
                continue

    return apply


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _read_capped(sink: tempfile._TemporaryFileWrapper | object, max_bytes: int) -> tuple[str, bool]:
    sink.flush()
    size = sink.seek(0, os.SEEK_END)
    if size <= max_bytes:
        sink.seek(0)
        return sink.read().decode("utf-8", errors="replace"), False
    head = max_bytes // 2
    tail = max_bytes - head
    sink.seek(0)
    first = sink.read(head)
    sink.seek(size - tail)
    last = sink.read(tail)
    marker = f"\n...[{size - max_bytes} bytes truncated]...\n".encode()
    return (first + marker + last).decode("utf-8", errors="replace"), True


def run_command(
    argv: Sequence[str],
    cwd: Path,
    config: SandboxConfig | None = None,
) -> RunResult:
    cfg = config or SandboxConfig()
    started = time.perf_counter()
    popen_kwargs: dict[str, object] = {}
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
        popen_kwargs["preexec_fn"] = _posix_limits(cfg)

    with tempfile.TemporaryFile() as sink:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=scrubbed_env(),
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            **popen_kwargs,
        )
        timed_out = False
        try:
            proc.wait(timeout=cfg.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            proc.wait()
        finally:
            if not IS_WINDOWS:
                _kill_tree(proc)
        output, truncated = _read_capped(sink, cfg.max_output_bytes)

    return RunResult(
        exit_code=None if timed_out else proc.returncode,
        output=output,
        timed_out=timed_out,
        duration_s=time.perf_counter() - started,
        truncated=truncated,
    )


def parse_pytest_summary(output: str, exit_code: int | None, timed_out: bool) -> PytestSummary:
    lines = output.strip().splitlines()
    tail = lines[-1] if lines else ""

    def count(pattern: str) -> int:
        match = re.search(pattern, tail)
        return int(match.group(1)) if match else 0

    return PytestSummary(
        passed=count(r"(\d+) passed"),
        failed=count(r"(\d+) failed"),
        errors=count(r"(\d+) errors?\b"),
        exit_code=exit_code,
        timed_out=timed_out,
    )


def run_pytest(
    cwd: Path,
    targets: Sequence[str] = (),
    config: SandboxConfig | None = None,
) -> tuple[RunResult, PytestSummary]:
    argv = [
        sys.executable,
        "-s",
        "-m",
        "pytest",
        "-q",
        "--no-header",
        "--tb=short",
        "--color=no",
        "--maxfail=5",
        "-p",
        "no:cacheprovider",
        *targets,
    ]
    result = run_command(argv, cwd, config)
    summary = parse_pytest_summary(result.output, result.exit_code, result.timed_out)
    return result, summary
