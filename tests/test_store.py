from __future__ import annotations

from pathlib import Path

import pytest

from repairagent.store import RunStore


def test_run_lifecycle():
    store = RunStore()
    run_id = store.create_run("task-a", {"provider": "groq", "model": "m1"})
    store.add_step(run_id, "llm", result="thinking", prompt_tokens=5, completion_tokens=2)
    store.add_step(
        run_id, "tool", tool="read_file", args={"path": "a.py"}, result="ok", ok=True, latency_s=0.1
    )
    store.add_step(run_id, "tool", tool="write_file", result="no", ok=False, policy_violation=True)
    store.finish_run(
        run_id,
        stop_reason="finished",
        resolved=True,
        visible_pass=True,
        hidden_pass=True,
        tampered=False,
        steps=3,
        prompt_tokens=5,
        completion_tokens=2,
        policy_violations=1,
        wall_s=1.5,
        summary="fixed",
    )
    run = store.get_run(run_id)
    assert run is not None
    assert (run["task_id"], run["provider"], run["model"]) == ("task-a", "groq", "m1")
    assert run["resolved"] == 1 and run["tampered"] == 0
    assert run["ended_at"] is not None
    steps = store.steps_for(run_id)
    assert [s["idx"] for s in steps] == [0, 1, 2]
    assert [s["kind"] for s in steps] == ["llm", "tool", "tool"]
    assert steps[1]["args_json"] == '{"path": "a.py"}'
    assert steps[2]["policy_violation"] == 1
    assert steps[1]["ok"] == 1 and steps[2]["ok"] == 0 and steps[0]["ok"] is None


def test_step_indices_are_per_run():
    store = RunStore()
    first = store.create_run("a")
    second = store.create_run("b")
    store.add_step(first, "llm")
    store.add_step(second, "llm")
    store.add_step(first, "llm")
    assert [s["idx"] for s in store.steps_for(first)] == [0, 1]
    assert [s["idx"] for s in store.steps_for(second)] == [0]


def test_long_values_are_clipped():
    store = RunStore()
    run_id = store.create_run("a")
    store.add_step(run_id, "tool", tool="t", args={"content": "x" * 10_000}, result="y" * 10_000)
    step = store.steps_for(run_id)[0]
    assert len(step["args_json"]) < 2100
    assert len(step["result_preview"]) < 600
    assert step["result_preview"].endswith("[clipped]")


def test_unknown_finish_field_rejected():
    store = RunStore()
    run_id = store.create_run("a")
    with pytest.raises(ValueError, match="unknown"):
        store.finish_run(run_id, nonsense=1)


def test_get_missing_run_and_list_order():
    store = RunStore()
    assert store.get_run(99) is None
    ids = [store.create_run(f"t{i}") for i in range(3)]
    listed = store.list_runs(limit=2)
    assert [r["id"] for r in listed] == [ids[2], ids[1]]


def test_persists_to_file(tmp_path: Path):
    path = tmp_path / "nested" / "runs.db"
    store = RunStore(path)
    run_id = store.create_run("persisted")
    store.close()
    reopened = RunStore(path)
    assert reopened.get_run(run_id)["task_id"] == "persisted"
    reopened.close()
