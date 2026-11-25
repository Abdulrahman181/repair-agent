import json
from pathlib import Path
from typing import Annotated

import typer

from repairagent.agent.loop import RepairAgent
from repairagent.config import Budget, ConfigError, LLMSettings, load_env_file
from repairagent.eval.harness import TaskResult, run_eval
from repairagent.eval.metrics import compare_reports
from repairagent.eval.report import write_report
from repairagent.eval.selfcheck import run_selfcheck
from repairagent.llm.openai_compat import OpenAICompatClient
from repairagent.store import RunStore
from repairagent.tasks import Task, TaskError, default_tasks_dir, discover_tasks

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Sandboxed code-repair agent.")

TasksDirOption = Annotated[
    Path | None, typer.Option("--tasks-dir", help="Directory containing benchmark tasks.")
]
ProviderOption = Annotated[str | None, typer.Option("--provider", help="groq, ollama or openai.")]
ModelOption = Annotated[str | None, typer.Option("--model", help="Model id for the provider.")]
DbOption = Annotated[Path, typer.Option("--db", help="SQLite file for run traces.")]
StepsOption = Annotated[int, typer.Option("--max-steps", help="Maximum LLM turns per task.")]


def _fail(message: str, code: int = 2) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def _load_tasks(tasks_dir: Path | None, only: list[str] | None = None) -> list[Task]:
    try:
        return discover_tasks(tasks_dir or default_tasks_dir(), only)
    except TaskError as exc:
        _fail(str(exc))
    return []


def _settings(provider: str | None, model: str | None) -> LLMSettings:
    load_env_file(".env")
    try:
        return LLMSettings.from_env(provider=provider, model=model)
    except ConfigError as exc:
        _fail(str(exc))
    raise typer.Exit(2)


@app.command("tasks")
def list_tasks(tasks_dir: TasksDirOption = None) -> None:
    for task in _load_tasks(tasks_dir):
        typer.echo(f"{task.id:<22} {task.difficulty:<7} {task.category:<16} {task.title}")


@app.command()
def selfcheck(tasks_dir: TasksDirOption = None) -> None:
    tasks = _load_tasks(tasks_dir)
    typer.echo(f"Validating {len(tasks)} tasks and the harness (no LLM involved)...")
    report = run_selfcheck(tasks)
    for task_id, problems in report.fixture_problems.items():
        for problem in problems:
            typer.echo(f"FIXTURE PROBLEM {task_id}: {problem}", err=True)
    if report.fixture_problems:
        raise typer.Exit(1)
    typer.echo(f"oracle agent resolved : {report.oracle_resolved}/{report.n_tasks} (expected all)")
    typer.echo(f"null agent resolved   : {report.null_resolved}/{report.n_tasks} (expected 0)")
    typer.echo(
        f"test-tampering blocked: {report.cheater_blocked}/{report.n_tasks} (expected all), "
        f"tampering that reached verification: {report.cheater_tampered} (expected 0)"
    )
    typer.echo("SELFCHECK PASSED" if report.ok else "SELFCHECK FAILED")
    raise typer.Exit(0 if report.ok else 1)


def _factory(settings: LLMSettings, budget: Budget, store: RunStore):
    meta = {"provider": settings.provider, "model": settings.model}

    def make(_task: Task, _repeat: int) -> RepairAgent:
        return RepairAgent(
            OpenAICompatClient(settings), budget=budget, store=store, run_meta=dict(meta)
        )

    return make


@app.command()
def run(
    task_id: Annotated[str, typer.Argument(help="Task id, see the 'tasks' command.")],
    provider: ProviderOption = None,
    model: ModelOption = None,
    max_steps: StepsOption = 20,
    db: DbOption = Path("runs/repairagent.db"),
    tasks_dir: TasksDirOption = None,
) -> None:
    settings = _settings(provider, model)
    task = _load_tasks(tasks_dir, [task_id])[0]
    store = RunStore(db)
    agent = _factory(settings, Budget(max_steps=max_steps), store)(task, 0)
    outcome = agent.run(task)
    verdict = outcome.verdict
    typer.echo(f"run id       : {outcome.run_id}")
    typer.echo(f"stop reason  : {outcome.stop_reason}")
    typer.echo(f"resolved     : {verdict.resolved}")
    typer.echo(f"visible/hidden: {verdict.visible_pass}/{verdict.hidden_pass}")
    typer.echo(f"files changed: {', '.join(outcome.files_changed) or '-'}")
    typer.echo(f"tokens       : {outcome.prompt_tokens + outcome.completion_tokens}")
    typer.echo(f"summary      : {outcome.summary or '-'}")
    store.close()


@app.command("eval")
def eval_cmd(
    task: Annotated[
        list[str] | None, typer.Option("--task", help="Task id, repeatable. Default: all.")
    ] = None,
    repeats: Annotated[int, typer.Option("--repeats", min=1)] = 1,
    out: Annotated[Path, typer.Option("--out", help="Report output directory.")] = Path("reports"),
    provider: ProviderOption = None,
    model: ModelOption = None,
    max_steps: StepsOption = 20,
    db: DbOption = Path("runs/repairagent.db"),
    tasks_dir: TasksDirOption = None,
) -> None:
    settings = _settings(provider, model)
    tasks = _load_tasks(tasks_dir, task)
    store = RunStore(db)

    def show(record: TaskResult) -> None:
        mark = "PASS" if record.resolved else "FAIL"
        typer.echo(
            f"[{mark}] {record.task_id} repeat={record.repeat} stop={record.stop_reason} "
            f"steps={record.steps}"
        )

    report = run_eval(
        tasks,
        _factory(settings, Budget(max_steps=max_steps), store),
        repeats=repeats,
        on_result=show,
        meta={"provider": settings.provider, "model": settings.model, "max_steps": max_steps},
    )
    store.close()
    json_path, md_path = write_report(report, out)
    agg = report["aggregate"]
    typer.echo(
        f"resolved {agg['resolved']}/{agg['n_runs']} ({agg['resolve_rate'] * 100:.1f}%), "
        f"overfit={agg['overfit_count']}, tampered={agg['tamper_count']}"
    )
    typer.echo(f"report: {md_path}")
    typer.echo(f"data  : {json_path}")


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(help="Baseline report JSON.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate report JSON.")],
    max_drop: Annotated[float, typer.Option("--max-drop", min=0.0, max=1.0)] = 0.05,
) -> None:
    try:
        base = json.loads(baseline.read_text(encoding="utf-8"))
        cand = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(f"could not read reports: {exc}")
    result = compare_reports(base, cand, max_drop)
    typer.echo(
        f"baseline {result['baseline_rate'] * 100:.1f}% -> candidate "
        f"{result['candidate_rate'] * 100:.1f}% (delta {result['delta'] * 100:+.1f} points, "
        f"allowed drop {max_drop * 100:.1f})"
    )
    typer.echo(f"regressions : {', '.join(result['regressions']) or '-'}")
    typer.echo(f"improvements: {', '.join(result['improvements']) or '-'}")
    typer.echo("GATE PASSED" if result["passed"] else "GATE FAILED")
    raise typer.Exit(0 if result["passed"] else 1)


@app.command()
def trace(
    run_id: Annotated[int, typer.Argument(help="Run id printed by 'run' or stored in reports.")],
    db: DbOption = Path("runs/repairagent.db"),
) -> None:
    if not db.is_file():
        _fail(f"database not found: {db}")
    store = RunStore(db)
    record = store.get_run(run_id)
    if record is None:
        _fail(f"run {run_id} not found")
    assert record is not None
    typer.echo(
        f"run {record['id']} task={record['task_id']} model={record['model']} "
        f"stop={record['stop_reason']} resolved={record['resolved']}"
    )
    for step in store.steps_for(run_id):
        label = step["tool"] or step["kind"]
        flag = " VIOLATION" if step["policy_violation"] else ""
        preview = (step["result_preview"] or "").replace("\n", " ")[:100]
        typer.echo(f"{step['idx']:>3} {label:<16}{flag} {preview}")
    store.close()


if __name__ == "__main__":
    app()
