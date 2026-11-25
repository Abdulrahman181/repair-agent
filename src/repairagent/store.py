from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    provider TEXT,
    model TEXT,
    stop_reason TEXT,
    resolved INTEGER,
    visible_pass INTEGER,
    hidden_pass INTEGER,
    tampered INTEGER,
    steps INTEGER,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    policy_violations INTEGER,
    wall_s REAL,
    summary TEXT,
    meta_json TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    idx INTEGER NOT NULL,
    kind TEXT NOT NULL,
    tool TEXT,
    args_json TEXT,
    result_preview TEXT,
    ok INTEGER,
    policy_violation INTEGER,
    latency_s REAL,
    prompt_tokens INTEGER,
    completion_tokens INTEGER
);
CREATE INDEX IF NOT EXISTS idx_steps_run ON steps(run_id, idx);
"""

PREVIEW_CHARS = 500
ARGS_CHARS = 2000


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "...[clipped]"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class RunStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._counters: dict[int, int] = {}

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> RunStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def create_run(self, task_id: str, meta: dict[str, Any] | None = None) -> int:
        info = meta or {}
        cursor = self._conn.execute(
            "INSERT INTO runs (task_id, started_at, provider, model, meta_json) VALUES (?,?,?,?,?)",
            (
                task_id,
                _now(),
                info.get("provider"),
                info.get("model"),
                json.dumps(info, sort_keys=True, default=str),
            ),
        )
        self._conn.commit()
        run_id = int(cursor.lastrowid or 0)
        self._counters[run_id] = 0
        return run_id

    def add_step(
        self,
        run_id: int,
        kind: str,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        result: str | None = None,
        ok: bool | None = None,
        policy_violation: bool = False,
        latency_s: float | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        idx = self._counters.get(run_id, 0)
        self._counters[run_id] = idx + 1
        args_json = (
            _clip(json.dumps(args, sort_keys=True, default=str), ARGS_CHARS) if args else None
        )
        self._conn.execute(
            "INSERT INTO steps (run_id, idx, kind, tool, args_json, result_preview, ok, "
            "policy_violation, latency_s, prompt_tokens, completion_tokens) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                idx,
                kind,
                tool,
                args_json,
                _clip(result, PREVIEW_CHARS),
                None if ok is None else int(ok),
                int(policy_violation),
                latency_s,
                prompt_tokens,
                completion_tokens,
            ),
        )
        self._conn.commit()

    def finish_run(self, run_id: int, **fields: Any) -> None:
        allowed = {
            "stop_reason",
            "resolved",
            "visible_pass",
            "hidden_pass",
            "tampered",
            "steps",
            "prompt_tokens",
            "completion_tokens",
            "policy_violations",
            "wall_s",
            "summary",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown run fields: {sorted(unknown)}")
        values = {
            key: (int(value) if isinstance(value, bool) else value) for key, value in fields.items()
        }
        assignments = ", ".join(f"{key} = ?" for key in values)
        self._conn.execute(
            f"UPDATE runs SET ended_at = ?, {assignments} WHERE id = ?",  # noqa: S608
            (_now(), *values.values(), run_id),
        )
        self._conn.commit()

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def steps_for(self, run_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY idx", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
