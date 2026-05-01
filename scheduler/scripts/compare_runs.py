"""Genera un reporte markdown comparando N runs persistidos en SQLite.

Pensado para que el coordinador / IT exporte un diff de iteraciones sin
abrir la app. Útil para documentar decisiones académicas sobre qué config
ganó.

Uso:
    .venv/bin/python scripts/compare_runs.py \\
        --db data/columbus.sqlite \\
        --runs 1 3 5 \\
        --out RUN_COMPARISON.md

Si --runs no se especifica, compara las últimas 5 corridas.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_SCHEDULER_ROOT = Path(__file__).resolve().parent.parent
if str(_SCHEDULER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCHEDULER_ROOT))

from src.scheduler.persistence import open_db, RunRepo, InputBundleRepo, RuleConfigRepo
from src.scheduler.rules import RULE_REGISTRY


def collect(db, run_ids: list[int]) -> dict[int, dict[str, Any]]:
    runs = RunRepo(db)
    bundles = InputBundleRepo(db)
    rules = RuleConfigRepo(db)
    out: dict[int, dict[str, Any]] = {}
    for rid in run_ids:
        meta = runs.get(rid)
        bmeta, _ = bundles.get(meta.bundle_id)
        rmeta, _, _, _ = rules.get(meta.rule_config_id)
        kpis = {(m, s, k): v for (m, s, k, v) in runs.get_kpis(rid)}
        compliance = {row[0]: row for row in runs.get_compliance(rid)}
        out[rid] = {
            "meta": meta,
            "bundle": bmeta,
            "rule_config": rmeta,
            "kpis": kpis,
            "compliance": compliance,
        }
    return out


def make_report(data: dict[int, dict[str, Any]], out_path: Path) -> None:
    if not data:
        out_path.write_text("# (no runs to compare)\n")
        return

    run_ids = sorted(data.keys())
    lines: list[str] = []
    lines.append(f"# Comparación de {len(run_ids)} corridas")
    lines.append("")
    lines.append(f"**Runs:** {', '.join(f'#{r}' for r in run_ids)}")
    lines.append("")

    # Metadata table
    lines.append("## Metadata")
    lines.append("")
    cols = ["Campo"] + [f"#{r}" for r in run_ids]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    fields = [
        ("Label", lambda d: d["meta"].label),
        ("Status", lambda d: d["meta"].status),
        ("Created", lambda d: d["meta"].created_at[:19]),
        ("Bundle", lambda d: f"#{d['bundle'].id} ({d['bundle'].label[:30]})"),
        ("RuleConfig", lambda d: f"#{d['rule_config'].id} ({d['rule_config'].label[:30]})"),
        ("Master(s)", lambda d: f"{d['meta'].master_seconds:.1f}" if d['meta'].master_seconds else "-"),
        ("Student(s)", lambda d: f"{d['meta'].student_seconds:.1f}" if d['meta'].student_seconds else "-"),
        ("Objective", lambda d: f"{d['meta'].objective:.0f}" if d['meta'].objective is not None else "-"),
    ]
    for name, accessor in fields:
        row = [name] + [str(accessor(data[r])) for r in run_ids]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # KPI matrix (global scope only)
    lines.append("## KPIs globales")
    lines.append("")
    all_metrics: set[str] = set()
    for d in data.values():
        for (m, s, k), v in d["kpis"].items():
            if s == "global":
                key = m if k == "all" else f"{m}.{k}"
                all_metrics.add(key)

    cols = ["Métrica"] + [f"#{r}" for r in run_ids] + ["Δ vs primera"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    first_id = run_ids[0]
    for metric in sorted(all_metrics):
        row = [metric]
        values_for_diff: list[float] = []
        for r in run_ids:
            value = None
            for (m, s, k), v in data[r]["kpis"].items():
                if s != "global":
                    continue
                key = m if k == "all" else f"{m}.{k}"
                if key == metric:
                    value = v
                    break
            if value is None:
                row.append("-")
                values_for_diff.append(float("nan"))
            else:
                row.append(f"{value:.2f}" if value != int(value) else f"{int(value)}")
                values_for_diff.append(value)
        # Delta vs first
        if len(values_for_diff) >= 2:
            first_v = values_for_diff[0]
            last_v = values_for_diff[-1]
            if first_v == first_v and last_v == last_v:  # NaN check
                delta = last_v - first_v
                arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "·")
                row.append(f"{arrow} {delta:+.1f}")
            else:
                row.append("-")
        else:
            row.append("-")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Compliance matrix
    lines.append("## Cumplimiento por regla (% satisfecho)")
    lines.append("")
    all_rules: set[str] = set()
    for d in data.values():
        all_rules.update(d["compliance"].keys())
    cols = ["Regla"] + [f"#{r}" for r in run_ids]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "---|" * len(cols))
    for rule_id in sorted(all_rules):
        rule = RULE_REGISTRY.get(rule_id)
        label = rule.label if rule else rule_id
        row = [f"{label} ({rule.kind})" if rule else f"{rule_id}"]
        for r in run_ids:
            row_data = data[r]["compliance"].get(rule_id)
            if row_data is None:
                row.append("-")
            else:
                _rid, sat, vio, pct, _ = row_data
                marker = "✅" if pct == 100 else ("⚠️" if pct >= 80 else "❌")
                row.append(f"{pct:.1f}% {marker}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Recommendation
    lines.append("## Mejor corrida según métricas v2 §10")
    lines.append("")

    def kpi_value(d: dict, metric: str) -> float | None:
        for (m, s, k), v in d["kpis"].items():
            if s == "global" and k == "all" and m == metric:
                return v
        return None

    def passes_v2(d: dict) -> tuple[bool, list[str]]:
        problems = []
        for metric, threshold, op in [
            ("fully_scheduled_pct", 98.0, ">="),
            ("required_fulfillment_pct", 98.0, ">="),
            ("first_choice_elective_pct", 80.0, ">="),
            ("section_balance_max_dev", 3, "<="),
        ]:
            v = kpi_value(d, metric)
            if v is None:
                problems.append(f"{metric} no medido")
                continue
            ok = (v >= threshold) if op == ">=" else (v <= threshold)
            if not ok:
                problems.append(f"{metric}={v:.1f} ({op}{threshold})")
        return len(problems) == 0, problems

    winners = []
    for r in run_ids:
        passes, problems = passes_v2(data[r])
        if passes:
            winners.append(r)
        else:
            lines.append(f"- **#{r}** ({data[r]['meta'].label}): NO cumple — {', '.join(problems)}")
    if winners:
        lines.append("")
        lines.append(
            f"✅ **Cumplen los 4 targets v2 §10:** {', '.join(f'#{r}' for r in winners)}"
        )
        # Pick the best by first-choice
        best = max(
            winners,
            key=lambda r: kpi_value(data[r], "first_choice_elective_pct") or 0
        )
        elec_v = kpi_value(data[best], 'first_choice_elective_pct') or 0
        lines.append(
            f"🏆 **Mejor por electivas rank-1:** #{best} ({data[best]['meta'].label}) — "
            f"{elec_v:.1f}%"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ Report → {out_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--runs", nargs="+", type=int, default=None,
                   help="Run IDs a comparar. Sin esto: últimas 5.")
    p.add_argument("--out", default="RUN_COMPARISON.md")
    args = p.parse_args()

    db = open_db(args.db)
    runs_repo = RunRepo(db)
    if args.runs:
        run_ids = args.runs
    else:
        run_ids = [r.id for r in runs_repo.list_all(limit=5)]
        run_ids.reverse()  # cronological

    data = collect(db, run_ids)
    make_report(data, Path(args.out))


if __name__ == "__main__":
    main()
