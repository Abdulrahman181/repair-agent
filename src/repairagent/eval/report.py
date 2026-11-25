from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    agg = report["aggregate"]
    low, high = agg["ci95"]
    lines = [
        "# RepairAgent evaluation report",
        "",
        f"- Provider: {meta.get('provider', 'n/a')}",
        f"- Model: {meta.get('model', 'n/a')}",
        f"- Started: {meta['started_at']}",
        f"- Python: {meta['python']} on {meta['platform']}",
        f"- Tasks: {agg['n_tasks']}, repeats per task: {meta['repeats']}, runs: {agg['n_runs']}",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Resolved (hidden tests pass, no tampering) | {agg['resolved']}/{agg['n_runs']}"
        f" ({_pct(agg['resolve_rate'])}) |",
        f"| Wilson 95% interval (runs treated as independent) | {_pct(low)} to {_pct(high)} |",
        f"| Visible tests pass | {_pct(agg['visible_pass_rate'])} |",
        f"| Overfit (visible pass, hidden fail) | {agg['overfit_count']} |",
        f"| Tamper attempts that reached verification | {agg['tamper_count']} |",
        f"| Policy violations (total) | {agg['policy_violations_total']} |",
        f"| Mean LLM turns | {agg['mean_steps']:.1f} |",
        f"| Mean tokens per run | {agg['mean_total_tokens']:.0f} |",
        f"| Mean wall time per run | {agg['mean_wall_s']:.1f}s |",
        "",
        "## Stop reasons",
        "",
        "| Reason | Runs |",
        "|---|---|",
    ]
    for reason, count in sorted(agg["stop_reasons"].items()):
        lines.append(f"| {reason} | {count} |")
    lines += ["", "## By difficulty", "", "| Difficulty | Runs | Resolve rate |", "|---|---|---|"]
    for name, stats in agg["by_difficulty"].items():
        lines.append(f"| {name} | {int(stats['n'])} | {_pct(stats['resolve_rate'])} |")
    lines += ["", "## By category", "", "| Category | Runs | Resolve rate |", "|---|---|---|"]
    for name, stats in agg["by_category"].items():
        lines.append(f"| {name} | {int(stats['n'])} | {_pct(stats['resolve_rate'])} |")
    lines += [
        "",
        "## Per run",
        "",
        "| Task | Repeat | Resolved | Visible | Hidden | Stop | Turns | Tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in report["results"]:
        tokens = item["prompt_tokens"] + item["completion_tokens"]
        lines.append(
            f"| {item['task_id']} | {item['repeat']} | {item['resolved']} | {item['visible_pass']}"
            f" | {item['hidden_pass']} | {item['stop_reason']} | {item['steps']} | {tokens} |"
        )
    lines.append("")
    return "\n".join(lines)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "run"


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = report["meta"]
    stamp = re.sub(r"[^0-9]", "", meta["started_at"])[:14]
    provider = _slug(str(meta.get("provider", "na")))
    model = _slug(str(meta.get("model", "na")))
    stem = f"eval_{provider}_{model}_{stamp}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
