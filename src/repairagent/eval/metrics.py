from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _group_rates(results: list[dict[str, Any]], key: str) -> dict[str, dict[str, float]]:
    groups: dict[str, list[bool]] = defaultdict(list)
    for item in results:
        groups[str(item[key])].append(bool(item["resolved"]))
    return {
        name: {"n": len(flags), "resolve_rate": sum(flags) / len(flags)}
        for name, flags in sorted(groups.items())
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results)
    resolved = sum(1 for item in results if item["resolved"])
    low, high = wilson_interval(resolved, n)
    overfit = sum(1 for item in results if item["visible_pass"] and not item["hidden_pass"])
    return {
        "n_runs": n,
        "n_tasks": len({item["task_id"] for item in results}),
        "resolved": resolved,
        "resolve_rate": resolved / n if n else 0.0,
        "ci95": [low, high],
        "visible_pass_rate": (sum(1 for item in results if item["visible_pass"]) / n) if n else 0.0,
        "overfit_count": overfit,
        "tamper_count": sum(1 for item in results if item["tampered"]),
        "policy_violations_total": sum(int(item["policy_violations"]) for item in results),
        "mean_steps": _mean([float(item["steps"]) for item in results]),
        "mean_total_tokens": _mean(
            [float(item["prompt_tokens"] + item["completion_tokens"]) for item in results]
        ),
        "mean_wall_s": _mean([float(item["wall_s"]) for item in results]),
        "stop_reasons": dict(Counter(item["stop_reason"] for item in results)),
        "by_category": _group_rates(results, "category"),
        "by_difficulty": _group_rates(results, "difficulty"),
    }


def _per_task_rates(report: dict[str, Any]) -> dict[str, float]:
    groups: dict[str, list[bool]] = defaultdict(list)
    for item in report["results"]:
        groups[item["task_id"]].append(bool(item["resolved"]))
    return {task: sum(flags) / len(flags) for task, flags in groups.items()}


def compare_reports(
    baseline: dict[str, Any], candidate: dict[str, Any], max_drop: float
) -> dict[str, Any]:
    base_rate = baseline["aggregate"]["resolve_rate"]
    cand_rate = candidate["aggregate"]["resolve_rate"]
    base_tasks = _per_task_rates(baseline)
    cand_tasks = _per_task_rates(candidate)
    common = sorted(set(base_tasks) & set(cand_tasks))
    regressions = [task for task in common if cand_tasks[task] < base_tasks[task]]
    improvements = [task for task in common if cand_tasks[task] > base_tasks[task]]
    delta = cand_rate - base_rate
    return {
        "baseline_rate": base_rate,
        "candidate_rate": cand_rate,
        "delta": delta,
        "max_drop": max_drop,
        "passed": delta >= -max_drop,
        "regressions": regressions,
        "improvements": improvements,
        "tasks_compared": len(common),
        "only_in_baseline": sorted(set(base_tasks) - set(cand_tasks)),
        "only_in_candidate": sorted(set(cand_tasks) - set(base_tasks)),
    }
