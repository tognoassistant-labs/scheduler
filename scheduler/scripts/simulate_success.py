"""Sweep de configuraciones contra los datos reales del Colegio.

Corre N escenarios con parámetros distintos sobre el mismo bundle. Cada
corrida queda persistida en SQLite (tabla `run`) y produce KPIs + compliance.
Al final reporta:
  - KPIs por escenario lado a lado
  - % de escenarios que cumplen cada target v2 §10
  - Probabilidad global de éxito (todos los targets a la vez)
  - Mejor configuración recomendada

Uso:
    .venv/bin/python scripts/simulate_success.py \\
        --xlsx data/cleanup/master_data_hs_CLEANED.xlsx \\
        --db data/sim.sqlite \\
        --report data/SIMULATION_REPORT.md
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow running from anywhere — make the scheduler root importable.
_SCHEDULER_ROOT = Path(__file__).resolve().parent.parent
if str(_SCHEDULER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCHEDULER_ROOT))

from src.scheduler.persistence import open_db
from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx
from src.scheduler.runner import solve_and_persist


@dataclass
class ScenarioSpec:
    label: str
    description: str
    overrides: dict[str, Any]      # path → value, e.g. "hard.max_section_spread_per_course": 3
    master_time: float = 60.0
    student_time: float = 120.0
    mode: str = "single"


def apply_overrides(ds, overrides: dict[str, Any]):
    """Apply 'hard.<field>' / 'soft.<field>' overrides to a Dataset copy."""
    hard_updates: dict[str, Any] = {}
    soft_updates: dict[str, Any] = {}
    for path, value in overrides.items():
        section, field_name = path.split(".", 1)
        if section == "hard":
            hard_updates[field_name] = value
        elif section == "soft":
            soft_updates[field_name] = value
    new_hard = ds.config.hard.model_copy(update=hard_updates) if hard_updates else ds.config.hard
    new_soft = ds.config.soft.model_copy(update=soft_updates) if soft_updates else ds.config.soft
    new_cfg = ds.config.model_copy(update={"hard": new_hard, "soft": new_soft})
    return ds.model_copy(update={"config": new_cfg})


SCENARIOS: list[ScenarioSpec] = [
    ScenarioSpec(
        label="baseline",
        description="Defaults — coplanning OFF, balance K=4, electivas peso 20",
        overrides={"hard.enforce_coplanning_groups": False},
    ),
    ScenarioSpec(
        label="coplanning_hard",
        description="Coplanning ON — costo conocido ~50 unmet",
        overrides={"hard.enforce_coplanning_groups": True},
    ),
    ScenarioSpec(
        label="balance_strict",
        description="Balance K=3 — meta v2 §10 más estricta",
        overrides={
            "hard.enforce_coplanning_groups": False,
            "hard.max_section_spread_per_course": 3,
        },
    ),
    ScenarioSpec(
        label="balance_loose",
        description="Balance K=6 — más holgura para electivas",
        overrides={
            "hard.enforce_coplanning_groups": False,
            "hard.max_section_spread_per_course": 6,
        },
    ),
    ScenarioSpec(
        label="elective_boost",
        description="Peso electivas rank-1 = 50 (default 20)",
        overrides={
            "hard.enforce_coplanning_groups": False,
            "soft.first_choice_electives": 50,
        },
    ),
    ScenarioSpec(
        label="elective_max",
        description="Peso electivas = 80 + balance soft bajo",
        overrides={
            "hard.enforce_coplanning_groups": False,
            "soft.first_choice_electives": 80,
            "soft.balance_class_sizes": 2,
        },
    ),
    ScenarioSpec(
        label="long_budget",
        description="Defaults pero con student_time=600s para máxima convergencia",
        overrides={"hard.enforce_coplanning_groups": False},
        master_time=120.0,
        student_time=600.0,
    ),
    ScenarioSpec(
        label="elective_boost_long",
        description="elective_boost con student_time=600s — combinación recomendada",
        overrides={
            "hard.enforce_coplanning_groups": False,
            "soft.first_choice_electives": 50,
        },
        master_time=120.0,
        student_time=600.0,
    ),
    ScenarioSpec(
        label="lexmin",
        description="Modo lexmin — electivas tienen prioridad estricta sobre groupings",
        overrides={"hard.enforce_coplanning_groups": False},
        mode="lexmin",
        student_time=180.0,
    ),
]

# v2 §10 targets — definen "éxito" para el sweep
TARGETS = {
    "fully_scheduled": ("fully_scheduled_pct", 98.0, ">="),
    "required":        ("required_fulfillment_pct", 98.0, ">="),
    "first_choice":    ("first_choice_elective_pct", 80.0, ">="),
    "balance":         ("section_balance_max_dev", 3, "<="),
}


def run_simulation(xlsx_path: Path, db_path: Path, report_path: Path) -> None:
    print(f"Loading {xlsx_path}...")
    ds = build_dataset_from_official_xlsx(xlsx_path)
    print(f"  {len(ds.students)} students · {len(ds.sections)} sections · {len(ds.courses)} courses")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # fresh DB for the sweep
    import os as _os
    _os.environ["COLUMBUS_DB"] = str(db_path)
    db = open_db(str(db_path))

    print(f"\n=== Simulation: {len(SCENARIOS)} scenarios ===")
    results: list[dict[str, Any]] = []

    for i, spec in enumerate(SCENARIOS, 1):
        print(f"\n[{i}/{len(SCENARIOS)}] {spec.label}: {spec.description}")
        ds_run = apply_overrides(ds, spec.overrides)
        t0 = time.time()
        outcome = solve_and_persist(
            ds_run,
            db=db,
            bundle_label="sweep-real",
            bundle_source_kind="xlsx",
            rule_config_label=spec.label,
            run_label=spec.label,
            master_time=spec.master_time,
            student_time=spec.student_time,
            mode=spec.mode,
        )
        elapsed = time.time() - t0

        if outcome.kpi:
            k = outcome.kpi
            row = {
                "label": spec.label,
                "description": spec.description,
                "elapsed_s": round(elapsed, 1),
                "master_status": outcome.master_status,
                "student_status": outcome.student_status,
                "fully_scheduled_pct": round(k.fully_scheduled_pct, 1),
                "required_fulfillment_pct": round(k.required_fulfillment_pct, 1),
                "first_choice_elective_pct": round(k.first_choice_elective_pct, 1),
                "section_balance_max_dev": k.section_balance_max_dev,
                "unmet_requests": k.unmet_requests,
                "infeasible": False,
            }
        else:
            row = {
                "label": spec.label,
                "description": spec.description,
                "elapsed_s": round(elapsed, 1),
                "master_status": outcome.master_status,
                "student_status": outcome.student_status,
                "fully_scheduled_pct": None,
                "required_fulfillment_pct": None,
                "first_choice_elective_pct": None,
                "section_balance_max_dev": None,
                "unmet_requests": None,
                "infeasible": True,
            }
        results.append(row)
        print(f"   → {row['master_status']}/{row['student_status']} · "
              f"required={row['required_fulfillment_pct']} · "
              f"electivas={row['first_choice_elective_pct']} · "
              f"balance={row['section_balance_max_dev']} · "
              f"{elapsed:.0f}s")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    successful = [r for r in results if not r["infeasible"]]
    n_total = len(results)
    n_feasible = len(successful)

    target_hits: dict[str, int] = {k: 0 for k in TARGETS}
    full_success_count = 0
    for r in successful:
        all_met = True
        for tname, (metric, threshold, op) in TARGETS.items():
            v = r[metric]
            ok = (v >= threshold) if op == ">=" else (v <= threshold)
            if ok:
                target_hits[tname] += 1
            else:
                all_met = False
        if all_met:
            full_success_count += 1

    lines: list[str] = []
    lines.append("# Simulación de probabilidad de éxito")
    lines.append("")
    lines.append(f"**Dataset:** `{xlsx_path.name}` ({len(ds.students)} estudiantes · "
                 f"{len(ds.sections)} secciones · {len(ds.courses)} cursos)")
    lines.append(f"**Escenarios corridos:** {n_total} (feasibles: {n_feasible})")
    lines.append(f"**Probabilidad de éxito completo (todos los targets):** "
                 f"**{100.0 * full_success_count / max(1, n_total):.1f}%** "
                 f"({full_success_count}/{n_total})")
    lines.append("")

    # Per-target hit rate
    lines.append("## Hit rate por target v2 §10")
    lines.append("")
    lines.append("| Target | Meta | % de escenarios que la cumplen |")
    lines.append("|---|---|---|")
    for tname, (metric, threshold, op) in TARGETS.items():
        pct = 100.0 * target_hits[tname] / max(1, n_total)
        meta_str = f"{op} {threshold}" + ("%" if "pct" in metric else "")
        lines.append(f"| {tname} | {meta_str} | **{pct:.1f}%** ({target_hits[tname]}/{n_total}) |")
    lines.append("")

    # Per-scenario detail
    lines.append("## Resultados por escenario")
    lines.append("")
    lines.append(
        "| Escenario | Status | Required % | Electivas rank-1 % | Balance dev | Tiempo |"
    )
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        if r["infeasible"]:
            lines.append(
                f"| **{r['label']}** | {r['master_status']}/{r['student_status']} ❌ "
                f"| — | — | — | {r['elapsed_s']}s |"
            )
        else:
            req = "✅" if r["required_fulfillment_pct"] >= 98 else "❌"
            elec = "✅" if r["first_choice_elective_pct"] >= 80 else "❌"
            bal = "✅" if r["section_balance_max_dev"] <= 3 else "❌"
            lines.append(
                f"| **{r['label']}** | {r['master_status']}/{r['student_status']} "
                f"| {r['required_fulfillment_pct']:.1f}% {req} "
                f"| {r['first_choice_elective_pct']:.1f}% {elec} "
                f"| {r['section_balance_max_dev']} {bal} "
                f"| {r['elapsed_s']:.0f}s |"
            )
    lines.append("")

    # Best scenario
    lines.append("## Mejor escenario por métrica")
    lines.append("")
    if successful:
        best_required = max(successful, key=lambda r: r["required_fulfillment_pct"])
        best_electives = max(successful, key=lambda r: r["first_choice_elective_pct"])
        best_balance = min(successful, key=lambda r: r["section_balance_max_dev"])
        lines.append(f"- **Mejor required fulfillment:** `{best_required['label']}` "
                     f"({best_required['required_fulfillment_pct']:.1f}%)")
        lines.append(f"- **Mejor electivas rank-1:** `{best_electives['label']}` "
                     f"({best_electives['first_choice_elective_pct']:.1f}%)")
        lines.append(f"- **Mejor balance:** `{best_balance['label']}` "
                     f"(dev={best_balance['section_balance_max_dev']})")

    # Recommendation
    lines.append("")
    lines.append("## Recomendación")
    lines.append("")
    if full_success_count == n_total:
        lines.append("✅ **Todos los escenarios cumplen los 4 targets simultáneamente.** "
                     "El motor es robusto a las variaciones probadas — cualquier configuración "
                     "razonable produce un horario que pasa la meta v2 §10.")
    elif full_success_count > 0:
        lines.append(f"⚠️ **{full_success_count}/{n_total} escenarios logran los 4 targets.** "
                     "Hay configuraciones que cumplen, pero el motor es sensible a parámetros. "
                     "Usar las del set ✅ y evitar las que rompen alguna meta.")
    else:
        lines.append("❌ **Ningún escenario logra los 4 targets simultáneamente.** "
                     "Los datos del Colegio o las metas v2 §10 requieren más sintonía: "
                     "subir capacidad de cursos saturados, agregar secciones, o renegociar "
                     "alguna meta (típicamente first-choice ≥80% es la más difícil con datos "
                     "ajustados).")
    lines.append("")
    lines.append(f"_Generado por `scripts/simulate_success.py` · runs persistidas en `{db_path}` · "
                 "ver tab `Corridas` en la app para drill-down._")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ Report → {report_path}")
    print(f"✓ DB     → {db_path}")
    print(f"\nProbabilidad de éxito global: {100.0 * full_success_count / max(1, n_total):.1f}% "
          f"({full_success_count}/{n_total})")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", required=True)
    p.add_argument("--db", default="data/sim.sqlite")
    p.add_argument("--report", default="data/SIMULATION_REPORT.md")
    args = p.parse_args()
    run_simulation(Path(args.xlsx), Path(args.db), Path(args.report))


if __name__ == "__main__":
    main()
