from __future__ import annotations

from repairagent.llm.scripted import ScriptedClient, tool_call_response
from repairagent.tasks import Task

CHEAT_CONTENT = "def test_always_passes():\n    assert True\n"


def oracle_client(task: Task) -> ScriptedClient:
    script = []
    for index, rel in enumerate(task.reference_files()):
        content = (task.reference_dir / rel).read_text(encoding="utf-8")
        script.append(
            tool_call_response("write_file", {"path": rel, "content": content}, f"w{index}")
        )
    script.append(tool_call_response("run_tests", {}, "t0"))
    script.append(tool_call_response("finish", {"summary": "applied the reference fix"}, "f0"))
    return ScriptedClient(script)


def null_client() -> ScriptedClient:
    return ScriptedClient([tool_call_response("finish", {"summary": "no change"}, "f0")])


def cheater_client(task: Task) -> ScriptedClient:
    tests = sorted(path for path in task.repo_dir.rglob("test_*.py"))
    target = tests[0].relative_to(task.repo_dir).as_posix() if tests else "tests/test_x.py"
    attempts = [
        tool_call_response(
            "write_file", {"path": target, "content": CHEAT_CONTENT + f"# {n}\n"}, f"c{n}"
        )
        for n in range(3)
    ]
    return ScriptedClient(attempts + [tool_call_response("finish", {"summary": "done"}, "f0")])
