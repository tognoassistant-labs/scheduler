"""Streamlit UI for the Columbus scheduling engine.

Run with:
    .venv/bin/streamlit run app.py

Single-page app with tabs (Setup → Solve → Browse → Scenarios → Export).
Uses st.session_state to cache the dataset and solve outputs across reruns.
"""
from __future__ import annotations

import io
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import streamlit as st

from src.scheduler.exporter import export_powerschool
from src.scheduler.io_csv import read_dataset, write_dataset
from src.scheduler.master_solver import solve_master
from src.scheduler.models import Dataset, HardConstraints, SoftConstraintWeights
from src.scheduler.persistence import DB, InputBundleRepo, RuleConfigRepo, RunRepo, open_db
from src.scheduler.ps_ingest import build_dataset_from_columbus
from src.scheduler.reports import compute_kpis, write_reports
from src.scheduler.rules import RULE_REGISTRY, apply_overrides, extract_values, list_rules
from src.scheduler.rules.compliance import compute_compliance
from src.scheduler.runner import solve_and_persist
from src.scheduler.sample_data import make_grade_12_dataset
from src.scheduler.scenarios import PRESETS, format_comparison, run_scenarios
from src.scheduler.student_solver import solve_students
from src.scheduler.validate import validate_dataset


# ============================================================================
# Page config + session state defaults
# ============================================================================

st.set_page_config(
    page_title="Columbus Scheduling Engine",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULTS = {
    "dataset": None,         # Dataset
    "dataset_source": "",    # description string
    "master": None,          # list[MasterAssignment]
    "students": None,        # list[StudentAssignment]
    "unmet": None,           # list[(student_id, course_id)]
    "kpi": None,             # KPIReport
    "master_status": "",
    "student_status": "",
    "master_seconds": 0.0,
    "student_seconds": 0.0,
    # v4.27 persistence + rules
    "persist_enabled": False,
    "db": None,              # DB instance, lazily created
    "bundle_id": None,       # int — persisted bundle for the active dataset
    "rule_config_id": None,  # int — persisted rule config for the next solve
    "rule_overrides": {},    # dict[rule_id, bool|int] — Rules-tab edits
    "last_run_id": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================================
# Helpers
# ============================================================================

def _kpi_cards(kpi) -> None:
    """Render the v2 §10 KPI cards as a 6-up grid."""
    cols = st.columns(6)
    targets = {
        "Fully scheduled": (kpi.fully_scheduled_pct, "≥98%", kpi.fully_scheduled_pct >= 98.0, "%"),
        "Required fulfillment": (kpi.required_fulfillment_pct, "≥98%", kpi.required_fulfillment_pct >= 98.0, "%"),
        "First-choice electives": (kpi.first_choice_elective_pct, "≥80%", kpi.first_choice_elective_pct >= 80.0, "%"),
        "Section balance": (kpi.section_balance_max_dev, "≤3", kpi.section_balance_max_dev <= 3, " students"),
        "Unscheduled": (kpi.unscheduled_students, "0", kpi.unscheduled_students == 0, ""),
        "Time conflicts": (0, "0", True, ""),
    }
    for col, (label, (value, target, met, suffix)) in zip(cols, targets.items()):
        with col:
            color = "#28a745" if met else "#dc3545"
            indicator = "✅" if met else "❌"
            display_value = f"{value:.1f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"
            st.markdown(
                f"""
                <div style="border:2px solid {color};border-radius:8px;padding:12px;text-align:center;">
                    <div style="color:#888;font-size:0.85em;">{label}</div>
                    <div style="font-size:1.6em;font-weight:bold;color:{color};">{display_value}</div>
                    <div style="font-size:0.85em;">target {target} {indicator}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _readiness_card(score: int, n_errors: int, n_warnings: int) -> None:
    """Render the readiness score panel."""
    color = "#28a745" if n_errors == 0 else "#dc3545"
    st.markdown(
        f"""
        <div style="border:2px solid {color};border-radius:8px;padding:16px;">
            <div style="font-size:1.1em;color:#888;">Data readiness</div>
            <div style="font-size:2.4em;font-weight:bold;color:{color};">{score}/100</div>
            <div>Errors: {n_errors} · Warnings: {n_warnings}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _has_dataset() -> bool:
    return st.session_state["dataset"] is not None


def _has_solution() -> bool:
    return st.session_state["master"] is not None and st.session_state["students"] is not None


def _set_dataset(ds: Dataset, source: str) -> None:
    st.session_state["dataset"] = ds
    st.session_state["dataset_source"] = source
    # New dataset → invalidate any persisted bundle pointer & solve outputs
    st.session_state["bundle_id"] = None
    st.session_state["rule_overrides"] = {}
    for k in ("master", "students", "unmet", "kpi", "master_status", "student_status"):
        st.session_state[k] = DEFAULTS[k]


def _get_db() -> DB | None:
    """Lazy-init the SQLite connection when persistence is enabled."""
    if not st.session_state.get("persist_enabled"):
        return None
    if st.session_state.get("db") is None:
        st.session_state["db"] = open_db()
    return st.session_state["db"]


def _effective_rules(ds: Dataset) -> tuple[HardConstraints, SoftConstraintWeights]:
    """Apply session_state['rule_overrides'] on top of ds.config.hard/soft."""
    overrides = st.session_state.get("rule_overrides") or {}
    return apply_overrides(ds.config.hard, ds.config.soft, overrides)


# ============================================================================
# Sidebar — dataset selection + solver config
# ============================================================================

with st.sidebar:
    st.title("📚 Columbus Scheduler")
    st.caption("v2 §10-aligned scheduling engine")

    st.divider()
    st.subheader("Dataset source")

    src = st.radio(
        "Choose a source",
        ["Built-in sample (Grade 12, 130 students)", "Canonical CSV folder", "Real Columbus xlsx"],
        label_visibility="collapsed",
    )

    if src == "Built-in sample (Grade 12, 130 students)":
        seed = st.number_input("Random seed", value=42, step=1, min_value=0)
        n_students = st.number_input("Number of students", value=130, step=10, min_value=10, max_value=1000)
        if st.button("🔄 Generate sample", width='stretch'):
            with st.spinner("Generating..."):
                ds = make_grade_12_dataset(n_students=int(n_students), seed=int(seed))
                _set_dataset(ds, f"sample · seed={seed} · n={n_students}")
            st.success(f"Loaded: {len(ds.students)} students, {len(ds.sections)} sections")
            st.rerun()

    elif src == "Canonical CSV folder":
        path = st.text_input("Path to CSV folder", value="data/sample")
        if st.button("📂 Load CSVs", width='stretch'):
            try:
                ds = read_dataset(Path(path))
                _set_dataset(ds, f"csv · {path}")
                st.success(f"Loaded from {path}: {len(ds.students)} students, {len(ds.sections)} sections")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load: {e}")

    elif src == "Real Columbus xlsx":
        st.caption("Upload the Columbus operating workbooks")
        demand_file = st.file_uploader("Demand workbook (1._STUDENTS_PER_COURSE_*.xlsx)", type=["xlsx"], key="demand_xlsx")
        sched_file = st.file_uploader("Schedule workbook (HS_Schedule_*.xlsx, optional)", type=["xlsx"], key="sched_xlsx")
        grade = st.number_input("Grade", value=12, step=1, min_value=9, max_value=12)
        year = st.text_input("Year", value="2026-2027")
        if st.button("📥 Ingest", width='stretch', disabled=demand_file is None):
            with st.spinner("Reading xlsx files..."):
                # Save uploads to /tmp so openpyxl can read them
                tmp = Path("/tmp/scheduler_uploads")
                tmp.mkdir(exist_ok=True)
                demand_path = tmp / demand_file.name
                demand_path.write_bytes(demand_file.getbuffer())
                sched_path = None
                if sched_file is not None:
                    sched_path = tmp / sched_file.name
                    sched_path.write_bytes(sched_file.getbuffer())
                try:
                    ds = build_dataset_from_columbus(demand_path, sched_path, grade=int(grade), year=year)
                    _set_dataset(ds, f"columbus · {demand_file.name} · grade={grade}")
                    st.success(f"Ingested: {len(ds.students)} students, {len(ds.sections)} sections, "
                               f"{len(ds.behavior.separations)} separations, {len(ds.behavior.groupings)} groupings")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ingest failed: {e}")

    st.divider()
    if _has_dataset():
        st.markdown(f"**Loaded:** `{st.session_state['dataset_source']}`")
        ds = st.session_state["dataset"]
        st.caption(f"{len(ds.students)} students · {len(ds.sections)} sections · "
                   f"{len(ds.teachers)} teachers · {len(ds.rooms)} rooms")
    else:
        st.info("Pick a dataset source above")

    st.divider()
    st.subheader("Persistence")
    persist = st.checkbox(
        "Save runs to SQLite",
        value=st.session_state.get("persist_enabled", False),
        help="Persist bundles, rule configs, and solve outputs so any historical "
             "run can be browsed and re-exported. DB path: $COLUMBUS_DB or "
             "data/columbus.sqlite.",
    )
    st.session_state["persist_enabled"] = persist
    if persist:
        db = _get_db()
        if db is not None:
            st.caption(f"DB: `{db.path}`")


# ============================================================================
# Main — tabs
# ============================================================================

st.title("Columbus Scheduling Engine")

(
    tab_setup,
    tab_rules,
    tab_solve,
    tab_compliance,
    tab_browse,
    tab_locks,
    tab_runs,
    tab_scenarios,
    tab_export,
) = st.tabs([
    "1️⃣ Inputs",
    "📋 Rules",
    "2️⃣ Solve",
    "✅ Compliance",
    "3️⃣ Browse",
    "🔒 Locks & Prefs",
    "📜 Runs",
    "4️⃣ Scenarios",
    "5️⃣ Export",
])

# ----------------------------------------------------------------------------
# TAB 1: SETUP — dataset overview + readiness
# ----------------------------------------------------------------------------

with tab_setup:
    if not _has_dataset():
        st.info("Pick a dataset source in the sidebar to begin.")
    else:
        ds = st.session_state["dataset"]
        rep = validate_dataset(ds)

        col_left, col_right = st.columns([1, 2])
        with col_left:
            _readiness_card(rep.score, len(rep.errors), len(rep.warnings))
        with col_right:
            st.subheader("Dataset overview")
            stats_cols = st.columns(4)
            stats_cols[0].metric("Students", len(ds.students))
            stats_cols[1].metric("Sections", len(ds.sections))
            stats_cols[2].metric("Teachers", len(ds.teachers))
            stats_cols[3].metric("Rooms", len(ds.rooms))

        if rep.errors:
            st.error(f"⚠️ {len(rep.errors)} blocking error(s) — fix before solving")
            for issue in rep.errors:
                st.write(f"  - **{issue.code}** · `{issue.entity_id or '-'}` · {issue.message}")
        if rep.warnings:
            with st.expander(f"{len(rep.warnings)} warning(s)"):
                for issue in rep.warnings:
                    st.write(f"- **{issue.code}** · `{issue.entity_id or '-'}` · {issue.message}")

        # v4.27 — persist the active dataset to SQLite so it survives reruns.
        if st.session_state.get("persist_enabled"):
            db = _get_db()
            st.divider()
            cols_persist = st.columns([2, 1])
            with cols_persist[0]:
                bundle_label = st.text_input(
                    "Bundle label",
                    value=st.session_state["dataset_source"][:60] or "ad-hoc",
                    key="bundle_label_input",
                )
            with cols_persist[1]:
                st.write("")
                st.write("")
                if st.button("💾 Save bundle to DB", width='stretch'):
                    repo = InputBundleRepo(db)
                    src = st.session_state["dataset_source"]
                    kind = (
                        "xlsx" if src.startswith("columbus")
                        else "sample" if src.startswith("sample")
                        else "csv"
                    )
                    bid = repo.save(bundle_label, kind, ds)
                    st.session_state["bundle_id"] = bid
                    st.success(f"Saved as bundle #{bid}")
            if st.session_state.get("bundle_id"):
                st.caption(f"Active bundle: #{st.session_state['bundle_id']}")

        st.divider()
        st.subheader("Course breakdown")
        rows = []
        sections_by_course = Counter(s.course_id for s in ds.sections)
        rank1_demand = Counter()
        for st_ in ds.students:
            for r in st_.requested_courses:
                if r.rank == 1:
                    rank1_demand[r.course_id] += 1
        for c in sorted(ds.courses, key=lambda c: c.course_id):
            n_sect = sections_by_course.get(c.course_id, 0)
            cap = sum(s.max_size for s in ds.sections if s.course_id == c.course_id)
            demand = rank1_demand.get(c.course_id, 0)
            rows.append({
                "Course ID": c.course_id,
                "Name": c.name,
                "Department": c.department,
                "Required": "✓" if c.is_required else "",
                "Lab": "✓" if c.is_lab else "",
                "Sections": n_sect,
                "Capacity": cap,
                "Rank-1 demand": demand,
                "Slack": cap - demand,
            })
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


# ----------------------------------------------------------------------------
# TAB 1.5: RULES — registry-driven toggles + sliders
# ----------------------------------------------------------------------------

with tab_rules:
    if not _has_dataset():
        st.info("Load a dataset first.")
    else:
        ds = st.session_state["dataset"]
        st.subheader("Reglas del motor")
        st.caption(
            "Toggles y pesos generados desde el registry. Los cambios aplican al próximo solve. "
            "Sin guardar a DB, los cambios se pierden al reiniciar la app."
        )

        # Group rules by (kind, category) so the form is scannable.
        from itertools import groupby
        rules_sorted = sorted(
            list_rules(),
            key=lambda r: (r.kind, r.category, r.id),
        )

        # Pre-fill widgets with current value: override > dataset config > default.
        cfg_values = extract_values(ds.config)
        overrides = dict(st.session_state.get("rule_overrides") or {})

        new_overrides: dict[str, bool | int] = {}
        for kind, kind_group in groupby(rules_sorted, key=lambda r: r.kind):
            kind_label = "Reglas duras (hard)" if kind == "hard" else "Pesos suaves (soft)"
            with st.expander(kind_label, expanded=(kind == "hard")):
                for category, cat_group in groupby(list(kind_group), key=lambda r: r.category):
                    st.markdown(f"**{category}**")
                    for r in cat_group:
                        current = overrides.get(r.id, cfg_values[r.id])
                        widget_key = f"rule_widget_{r.id}"
                        if r.value_type == "bool":
                            value = st.checkbox(
                                r.label,
                                value=bool(current),
                                key=widget_key,
                                help=r.description,
                            )
                        else:
                            value = st.number_input(
                                r.label,
                                min_value=int(r.min_value or 0),
                                max_value=int(r.max_value or 1000),
                                value=int(current),
                                step=1,
                                key=widget_key,
                                help=r.description,
                            )
                        new_overrides[r.id] = value
                    st.write("")  # vertical breathing room

        col_apply, col_reset, col_save = st.columns(3)
        with col_apply:
            if st.button("✓ Aplicar al próximo solve", type="primary", width='stretch'):
                # Strip overrides that match the current dataset config — keeps the
                # session state minimal and obvious.
                effective = {rid: v for rid, v in new_overrides.items() if v != cfg_values[rid]}
                st.session_state["rule_overrides"] = effective
                if effective:
                    st.success(f"{len(effective)} regla(s) modificada(s) — aplicarán en el próximo solve")
                else:
                    st.info("No hay cambios respecto a la config actual del dataset")
        with col_reset:
            if st.button("↺ Reset a defaults del dataset", width='stretch'):
                st.session_state["rule_overrides"] = {}
                st.rerun()
        with col_save:
            if st.session_state.get("persist_enabled"):
                save_label = st.text_input(
                    "Nombre",
                    value="custom",
                    key="rule_config_save_label",
                    label_visibility="collapsed",
                    placeholder="Nombre para esta config",
                )
                if st.button("💾 Guardar config", width='stretch'):
                    db = _get_db()
                    repo = RuleConfigRepo(db)
                    new_hard, new_soft = apply_overrides(
                        ds.config.hard, ds.config.soft, new_overrides
                    )
                    cid = repo.save(save_label or "custom", new_hard, new_soft)
                    st.session_state["rule_config_id"] = cid
                    st.session_state["rule_overrides"] = {
                        rid: v for rid, v in new_overrides.items() if v != cfg_values[rid]
                    }
                    st.success(f"Guardada como rule_config #{cid}")
            else:
                st.caption("Activa 'Save runs to SQLite' en el sidebar para guardar configs nombradas")

        active = st.session_state.get("rule_overrides") or {}
        if active:
            st.divider()
            st.markdown(f"**Pendiente de aplicar — {len(active)} regla(s) modificada(s):**")
            diff_rows = []
            for rid, val in active.items():
                r = RULE_REGISTRY.get(rid)
                if r is None:
                    continue
                diff_rows.append({
                    "Regla": r.label,
                    "Default": cfg_values[rid],
                    "Override": val,
                })
            st.dataframe(pd.DataFrame(diff_rows), width='stretch', hide_index=True)

        # M6 — Phase 2 placeholder: custom rule editor
        st.divider()
        with st.expander("➕ Reglas personalizadas (próximamente — Fase 2)"):
            st.markdown(
                "**Estado:** la arquitectura ya soporta reglas custom serializadas en "
                "`rule_config.registry_overrides_json`. La UI de autoría y el "
                "evaluador de DSL llegan en una segunda fase."
            )
            st.code(
                """# Ejemplo de spec custom (CustomRuleSpec):
{
  "id": "user_no_friday_pe",
  "kind": "hard",
  "label": "No PE on Fridays",
  "solver_op": "forbid_slot",
  "params": {"course_id": "PE12", "day": "E"},
  "enabled": true
}""",
                language="json",
            )
            st.caption(
                "Cuando la Fase 2 esté lista, esta sección permitirá escribir, probar y "
                "guardar reglas custom directamente desde la UI."
            )


# ----------------------------------------------------------------------------
# TAB 2: SOLVE
# ----------------------------------------------------------------------------

with tab_solve:
    if not _has_dataset():
        st.info("Load a dataset first.")
    else:
        ds = st.session_state["dataset"]

        st.subheader("Solver configuration")
        cfg_cols = st.columns(3)
        with cfg_cols[0]:
            mode = st.selectbox("Mode", ["single", "lexmin"], index=0,
                                help="single: weighted-sum (fast). lexmin: 2-phase (electives → groupings) under hard balance cap.")
            master_time = st.number_input("Master time budget (s)", value=30, min_value=5, max_value=600, step=5)
            student_time = st.number_input("Student time budget (s)", value=180, min_value=10, max_value=1200, step=10)
        with cfg_cols[1]:
            spread_cap = st.slider("Hard balance cap K (max−min per course)", 2, 10, ds.config.hard.max_section_spread_per_course,
                                   help="K=5 → max-dev ≤ 3 (v2 §10 target). K=8 = loose; K=3 = tight (may make electives infeasible).")
            elective_w = st.slider("First-choice elective weight", 1, 50, ds.config.soft.first_choice_electives)
            balance_w = st.slider("Soft balance weight", 0, 30, ds.config.soft.balance_class_sizes)
        with cfg_cols[2]:
            grouping_w = st.slider("Grouping pairs weight", 0, 20, ds.config.soft.grouping_codes)
            coplan_w = st.slider("Co-planning weight (0=off)", 0, 10, ds.config.soft.co_planning,
                                 help="Co-planning concentrates same-dept sections; >0 may hurt electives.")
            teacher_load_w = st.slider("Teacher-load balance weight", 0, 20, ds.config.soft.teacher_load_balance)

        # Show rule overrides badge if any are pending.
        if st.session_state.get("rule_overrides"):
            n = len(st.session_state["rule_overrides"])
            st.info(f"📋 {n} regla(s) modificada(s) en la tab Rules — aplicarán automáticamente al solve")

        if st.button("▶️ Solve", type="primary", width='stretch'):
            # Apply quick-slider config + Rules-tab overrides to a copy of the dataset.
            import copy
            ds_run = copy.deepcopy(ds)
            new_hard, new_soft = _effective_rules(ds_run)
            ds_run.config.hard = new_hard
            ds_run.config.soft = new_soft
            # Quick sliders win over rule overrides for the parameters they expose.
            ds_run.config.hard.max_section_spread_per_course = spread_cap
            ds_run.config.soft.first_choice_electives = elective_w
            ds_run.config.soft.balance_class_sizes = balance_w
            ds_run.config.soft.grouping_codes = grouping_w
            ds_run.config.soft.co_planning = coplan_w
            ds_run.config.soft.teacher_load_balance = teacher_load_w

            db = _get_db() if st.session_state.get("persist_enabled") else None

            if db is not None:
                # Persistence path: runner handles bundle/rule_config/run lifecycle.
                with st.spinner("Solving (with persistence)..."):
                    src = st.session_state["dataset_source"]
                    bundle_label = st.session_state.get("bundle_label_input") or src[:60] or "ad-hoc"
                    kind = (
                        "xlsx" if src.startswith("columbus")
                        else "sample" if src.startswith("sample")
                        else "csv"
                    )
                    outcome = solve_and_persist(
                        ds_run,
                        db=db,
                        bundle_id=st.session_state.get("bundle_id"),
                        rule_config_id=st.session_state.get("rule_config_id"),
                        bundle_label=bundle_label,
                        bundle_source_kind=kind,
                        rule_config_label="ui-active",
                        run_label=f"ui-{int(time.time())}",
                        master_time=master_time,
                        student_time=student_time,
                        mode=mode,
                    )
                if not outcome.result.master:
                    st.error(f"Master solve failed: {outcome.master_status}")
                else:
                    st.session_state["master"] = outcome.result.master
                    st.session_state["students"] = outcome.result.students
                    st.session_state["unmet"] = outcome.result.unscheduled_requests
                    st.session_state["master_status"] = outcome.master_status
                    st.session_state["student_status"] = outcome.student_status
                    st.session_state["master_seconds"] = outcome.result.solve_seconds * 0.5  # split for display
                    st.session_state["student_seconds"] = outcome.result.solve_seconds * 0.5
                    st.session_state["kpi"] = outcome.kpi
                    st.session_state["dataset"] = ds_run
                    st.session_state["bundle_id"] = outcome.bundle_id
                    st.session_state["rule_config_id"] = outcome.rule_config_id
                    st.session_state["last_run_id"] = outcome.run_id
                    st.success(
                        f"✓ Run #{outcome.run_id} · {outcome.master_status} / {outcome.student_status} · "
                        f"{len(outcome.result.students)} students · {len(outcome.result.unscheduled_requests)} unmet"
                    )
            else:
                # Legacy path — no persistence
                with st.spinner(f"Stage 1: master schedule (budget {master_time}s)..."):
                    t0 = time.time()
                    master, _, m_status = solve_master(ds_run, time_limit_s=master_time)
                    m_elapsed = time.time() - t0
                if not master:
                    st.error(f"Master solve failed: {m_status}")
                else:
                    st.session_state["master"] = master
                    st.session_state["master_status"] = m_status
                    st.session_state["master_seconds"] = m_elapsed
                    st.success(f"✓ Stage 1: {m_status} · {len(master)} sections placed · {m_elapsed:.1f}s")

                    with st.spinner(f"Stage 2: student assignment (mode={mode}, budget {student_time}s)..."):
                        t0 = time.time()
                        students, unmet, _, s_status = solve_students(
                            ds_run, master, time_limit_s=student_time, mode=mode
                        )
                        s_elapsed = time.time() - t0
                    if not students:
                        st.error(f"Student solve failed: {s_status}")
                    else:
                        st.session_state["students"] = students
                        st.session_state["unmet"] = unmet
                        st.session_state["student_status"] = s_status
                        st.session_state["student_seconds"] = s_elapsed
                        st.session_state["kpi"] = compute_kpis(ds_run, master, students, unmet)
                        st.session_state["dataset"] = ds_run
                        st.success(f"✓ Stage 2: {s_status} · {len(students)} students placed · "
                                   f"{len(unmet)} unmet rank-1 · {s_elapsed:.1f}s")

        if _has_solution():
            st.divider()
            st.subheader("KPI vs v2 §10 targets")
            _kpi_cards(st.session_state["kpi"])

            st.caption(
                f"Master: {st.session_state['master_status']} ({st.session_state['master_seconds']:.1f}s) · "
                f"Student: {st.session_state['student_status']} ({st.session_state['student_seconds']:.1f}s)"
            )


# ----------------------------------------------------------------------------
# TAB 2.5: COMPLIANCE — per-rule satisfaction with drilldown
# ----------------------------------------------------------------------------

with tab_compliance:
    if not _has_solution():
        st.info("Corre el solver primero (tab 2) para ver cumplimiento por regla.")
    else:
        ds = st.session_state["dataset"]
        master = st.session_state["master"]
        students = st.session_state["students"]
        unmet = st.session_state["unmet"] or []

        compliances = compute_compliance(ds, master, students, unmet)
        st.subheader("Cumplimiento por regla")
        st.caption("Solo se muestran reglas con un checker disponible. Las demás aparecen como N/A.")

        rows = []
        for c in compliances:
            r = RULE_REGISTRY.get(c.rule_id)
            if r is None:
                continue
            total = c.satisfied + c.violated
            rows.append({
                "Regla": r.label,
                "Tipo": r.kind,
                "Categoría": r.category,
                "Cumplidas": c.satisfied,
                "Violadas": c.violated,
                "% Cumplimiento": round(c.pct, 2),
                "Total": total,
                "_id": c.rule_id,
            })
        df_comp = pd.DataFrame(rows).drop(columns=["_id"]) if rows else pd.DataFrame()
        if not df_comp.empty:
            st.dataframe(df_comp, width='stretch', hide_index=True)

        # N/A list — registered rules without a checker
        measured_ids = {c.rule_id for c in compliances}
        unmeasured = [r for r in RULE_REGISTRY.values() if r.id not in measured_ids]
        if unmeasured:
            with st.expander(f"Reglas sin medición disponible ({len(unmeasured)})"):
                for r in unmeasured:
                    st.write(f"- **{r.label}** — _no checker implementado_")

        st.divider()
        st.subheader("Drill-down de violaciones")
        violated = [c for c in compliances if c.violated > 0]
        if not violated:
            st.success("✅ Sin violaciones detectadas en las reglas medidas.")
        else:
            options = {f"{RULE_REGISTRY[c.rule_id].label} ({c.violated} violadas)": c for c in violated}
            picked_label = st.selectbox("Selecciona regla", list(options.keys()))
            picked = options[picked_label]
            if picked.sample_violations:
                st.markdown(f"**Muestra (hasta {len(picked.sample_violations)} primeras):**")
                st.dataframe(pd.DataFrame(picked.sample_violations), width='stretch', hide_index=True)
            else:
                st.info("Esta regla no expone muestras de violaciones.")


# ----------------------------------------------------------------------------
# TAB 3: BROWSE
# ----------------------------------------------------------------------------

with tab_browse:
    if not _has_solution():
        st.info("Run a solve first (tab 2).")
    else:
        ds = st.session_state["dataset"]
        master = st.session_state["master"]
        students = st.session_state["students"]

        sections_by_id = {s.section_id: s for s in ds.sections}
        master_by_sect = {m.section_id: m for m in master}
        teachers_by_id = {t.teacher_id: t for t in ds.teachers}
        rooms_by_id = {r.room_id: r for r in ds.rooms}
        courses_by_id = {c.course_id: c for c in ds.courses}

        enrollment = defaultdict(int)
        for sa in students:
            for sid in sa.section_ids:
                enrollment[sid] += 1

        view = st.radio(
            "View",
            ["Schedule grid", "Sections", "Students", "Teachers", "Unmet requests"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if view == "Schedule grid":
            st.subheader("Master schedule grid (Day × Block)")
            # For each (day, block), list which sections meet there
            slots: dict[tuple[str, int], list[str]] = defaultdict(list)
            for m in master:
                for (day, block) in m.slots:
                    slots[(day, block)].append(m.section_id)
            grid_data = []
            for block in (1, 2, 3, 4, 5):
                row = {"Block": block}
                for day in ("A", "B", "C", "D", "E"):
                    sect_ids = slots.get((day, block), [])
                    cell = []
                    for sid in sorted(sect_ids):
                        sect = sections_by_id.get(sid)
                        m = master_by_sect.get(sid)
                        if sect is None or m is None:
                            continue
                        n = enrollment.get(sid, 0)
                        cap = sect.max_size
                        cell.append(f"{sid} ({n}/{cap})")
                    row[f"Day {day}"] = "\n".join(cell) if cell else "—"
                grid_data.append(row)
            st.dataframe(pd.DataFrame(grid_data), width='stretch', hide_index=True, height=420)

        elif view == "Sections":
            rows = []
            for s in ds.sections:
                m = master_by_sect.get(s.section_id)
                if m is None:
                    continue
                t = teachers_by_id.get(s.teacher_id)
                r = rooms_by_id.get(m.room_id)
                c = courses_by_id.get(s.course_id)
                n = enrollment.get(s.section_id, 0)
                util = 100.0 * n / max(1, s.max_size)
                rows.append({
                    "Section": s.section_id,
                    "Course": s.course_id,
                    "Course Name": c.name if c else "",
                    "Teacher": t.name if t else s.teacher_id,
                    "Scheme": str(m.scheme),
                    "Slots": ", ".join(f"{d}{b}" for d, b in m.slots),
                    "Room": r.name if r else m.room_id,
                    "Enrolled": n,
                    "Cap": s.max_size,
                    "Util %": round(util, 1),
                })
            df = pd.DataFrame(rows)
            course_filter = st.multiselect("Filter by course", sorted(df["Course"].unique()))
            if course_filter:
                df = df[df["Course"].isin(course_filter)]
            st.dataframe(df, width='stretch', hide_index=True, height=520)

        elif view == "Students":
            rows = []
            student_assigns = {sa.student_id: sa for sa in students}
            for stu in ds.students:
                sa = student_assigns.get(stu.student_id)
                if sa is None:
                    continue
                cids = [sections_by_id[sid].course_id for sid in sa.section_ids if sid in sections_by_id]
                rows.append({
                    "Student ID": stu.student_id,
                    "Name": stu.name,
                    "Grade": stu.grade,
                    "# courses": len(sa.section_ids),
                    "Sections": ", ".join(sa.section_ids),
                    "Courses": ", ".join(cids),
                })
            df = pd.DataFrame(rows)
            search = st.text_input("Search students (name or ID)", "")
            if search:
                mask = df["Name"].str.contains(search, case=False, na=False) | df["Student ID"].astype(str).str.contains(search, case=False, na=False)
                df = df[mask]
            st.dataframe(df, width='stretch', hide_index=True, height=520)

        elif view == "Teachers":
            rows = []
            sect_per_teacher = defaultdict(list)
            for s in ds.sections:
                sect_per_teacher[s.teacher_id].append(s.section_id)
            for t in ds.teachers:
                sids = sect_per_teacher.get(t.teacher_id, [])
                academic = [sid for sid in sids if not courses_by_id[sections_by_id[sid].course_id].is_advisory]
                advisory = [sid for sid in sids if courses_by_id[sections_by_id[sid].course_id].is_advisory]
                rows.append({
                    "Teacher": t.name,
                    "ID": t.teacher_id,
                    "Department": t.department,
                    "Academic sections": len(academic),
                    "Advisory sections": len(advisory),
                    "Max load": t.max_load,
                    "Sections": ", ".join(sids),
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, width='stretch', hide_index=True, height=520)

        elif view == "Unmet requests":
            unmet = st.session_state["unmet"] or []
            if not unmet:
                st.success("🎉 No unmet rank-1 requests.")
            else:
                rows = [
                    {"Student ID": stu_id, "Course ID": cid, "Course Name": (courses_by_id.get(cid).name if courses_by_id.get(cid) else "")}
                    for stu_id, cid in unmet
                ]
                df = pd.DataFrame(rows)
                by_course = df.groupby(["Course ID", "Course Name"]).size().reset_index(name="# unmet")
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.subheader("By course")
                    st.dataframe(by_course.sort_values("# unmet", ascending=False), width='stretch', hide_index=True)
                with col2:
                    st.subheader("All unmet")
                    st.dataframe(df, width='stretch', hide_index=True, height=420)


# ----------------------------------------------------------------------------
# TAB 3.5: LOCKS & PREFERENCES (v2 §6.2 / §13)
# ----------------------------------------------------------------------------

with tab_locks:
    if not _has_dataset():
        st.info("Load a dataset first.")
    else:
        ds = st.session_state["dataset"]
        st.caption("Edit section locks and teacher preferences. Changes persist in the loaded dataset; re-run Solve (tab 2) to apply.")

        sub_locks, sub_prefs = st.tabs(["Section locks", "Teacher preferences"])

        with sub_locks:
            st.subheader("Section locks (v2 §13)")
            st.caption("Pin a section to a specific scheme (1..8 or ADVISORY) or room. Empty = unconstrained.")
            non_adv = [s for s in ds.sections if not ds.course_by_id(s.course_id).is_advisory]
            rows = [{
                "Section ID": s.section_id,
                "Course": s.course_id,
                "Teacher": next((t.name for t in ds.teachers if t.teacher_id == s.teacher_id), s.teacher_id),
                "Locked Scheme": str(s.locked_scheme) if s.locked_scheme is not None else "",
                "Locked Room": s.locked_room_id or "",
            } for s in non_adv]
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df,
                column_config={
                    "Section ID": st.column_config.TextColumn(disabled=True),
                    "Course": st.column_config.TextColumn(disabled=True),
                    "Teacher": st.column_config.TextColumn(disabled=True),
                    "Locked Scheme": st.column_config.SelectboxColumn(
                        options=["", "1", "2", "3", "4", "5", "6", "7", "8"], required=False,
                        help="Pick scheme 1..8, or empty for no lock",
                    ),
                    "Locked Room": st.column_config.SelectboxColumn(
                        options=[""] + [r.room_id for r in ds.rooms], required=False,
                    ),
                },
                hide_index=True,
                width='stretch',
                num_rows="fixed",
                key="locks_editor",
            )

            if st.button("💾 Apply locks to dataset"):
                changes = 0
                for i, s in enumerate(non_adv):
                    new_scheme = edited.iloc[i]["Locked Scheme"]
                    new_room = edited.iloc[i]["Locked Room"]
                    if new_scheme:
                        try:
                            new_scheme_val = int(new_scheme)
                        except ValueError:
                            new_scheme_val = None
                    else:
                        new_scheme_val = None
                    new_room_val = new_room if new_room else None
                    if s.locked_scheme != new_scheme_val:
                        s.locked_scheme = new_scheme_val
                        changes += 1
                    if s.locked_room_id != new_room_val:
                        s.locked_room_id = new_room_val
                        changes += 1
                if changes:
                    st.session_state["dataset"] = ds
                    # Clear stale solve outputs since locks change the model
                    for k in ("master", "students", "unmet", "kpi", "master_status", "student_status"):
                        st.session_state[k] = DEFAULTS[k]
                    st.success(f"Updated {changes} field(s). Re-run Solve in tab 2 to apply.")
                else:
                    st.info("No changes detected.")

        with sub_prefs:
            st.subheader("Teacher preferences (v2 §6.2)")
            st.caption("Preferred/avoided courses and time blocks. Soft objectives — solver will try to honor.")
            rows = [{
                "Teacher ID": t.teacher_id,
                "Name": t.name,
                "Department": t.department,
                "# qualified": len(t.qualified_course_ids),
                "Preferred courses": "|".join(t.preferred_course_ids),
                "Avoid courses": "|".join(t.avoid_course_ids),
                "Preferred blocks": "|".join(str(b) for b in t.preferred_blocks),
                "Avoid blocks": "|".join(str(b) for b in t.avoid_blocks),
            } for t in ds.teachers]
            df = pd.DataFrame(rows)
            edited = st.data_editor(
                df,
                column_config={
                    "Teacher ID": st.column_config.TextColumn(disabled=True),
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Department": st.column_config.TextColumn(disabled=True),
                    "# qualified": st.column_config.NumberColumn(disabled=True),
                    "Preferred courses": st.column_config.TextColumn(help="Pipe-separated course IDs (e.g. ENG12|CALC)"),
                    "Avoid courses": st.column_config.TextColumn(help="Pipe-separated course IDs"),
                    "Preferred blocks": st.column_config.TextColumn(help="Pipe-separated block numbers 1..5"),
                    "Avoid blocks": st.column_config.TextColumn(help="Pipe-separated block numbers 1..5"),
                },
                hide_index=True,
                width='stretch',
                num_rows="fixed",
                key="prefs_editor",
            )

            if st.button("💾 Apply preferences to dataset"):
                def _split(v: str) -> list[str]:
                    return [x.strip() for x in v.split("|") if x.strip()]
                def _split_int(v: str) -> list[int]:
                    out = []
                    for x in v.split("|"):
                        x = x.strip()
                        if x.isdigit():
                            out.append(int(x))
                    return out
                changes = 0
                for i, t in enumerate(ds.teachers):
                    new_pref = _split(edited.iloc[i]["Preferred courses"] or "")
                    new_avoid = _split(edited.iloc[i]["Avoid courses"] or "")
                    new_pblk = _split_int(edited.iloc[i]["Preferred blocks"] or "")
                    new_ablk = _split_int(edited.iloc[i]["Avoid blocks"] or "")
                    if t.preferred_course_ids != new_pref:
                        t.preferred_course_ids = new_pref
                        changes += 1
                    if t.avoid_course_ids != new_avoid:
                        t.avoid_course_ids = new_avoid
                        changes += 1
                    if t.preferred_blocks != new_pblk:
                        t.preferred_blocks = new_pblk
                        changes += 1
                    if t.avoid_blocks != new_ablk:
                        t.avoid_blocks = new_ablk
                        changes += 1
                if changes:
                    st.session_state["dataset"] = ds
                    for k in ("master", "students", "unmet", "kpi", "master_status", "student_status"):
                        st.session_state[k] = DEFAULTS[k]
                    st.success(f"Updated {changes} field(s). Re-run Solve in tab 2 to apply.")
                else:
                    st.info("No changes detected.")


# ----------------------------------------------------------------------------
# TAB 3.6: RUNS — historical run browser (M3 basic; full diff in M4)
# ----------------------------------------------------------------------------

with tab_runs:
    if not st.session_state.get("persist_enabled"):
        st.info("Activa 'Save runs to SQLite' en el sidebar para ver el histórico de corridas.")
    else:
        db = _get_db()
        run_repo = RunRepo(db)
        bundle_repo = InputBundleRepo(db)
        rules_repo = RuleConfigRepo(db)

        runs = run_repo.list_all(limit=50)
        st.subheader(f"Histórico ({len(runs)} corrida(s))")

        if not runs:
            st.info("No hay corridas guardadas todavía. Corre el solver con persistencia activa para ver corridas aquí.")
        else:
            run_rows = []
            for r in runs:
                run_rows.append({
                    "ID": r.id,
                    "Label": r.label,
                    "Created": r.created_at[:19].replace("T", " "),
                    "Status": r.status,
                    "Bundle": r.bundle_id,
                    "RuleCfg": r.rule_config_id,
                    "Master (s)": f"{r.master_seconds:.1f}" if r.master_seconds else "-",
                    "Student (s)": f"{r.student_seconds:.1f}" if r.student_seconds else "-",
                    "Objective": f"{r.objective:.0f}" if r.objective else "-",
                })
            st.dataframe(pd.DataFrame(run_rows), width='stretch', hide_index=True)

            st.divider()
            st.subheader("Comparar runs")
            compare_ids = st.multiselect(
                "Selecciona 2+ runs para diff",
                options=[r.id for r in runs],
                format_func=lambda i: f"#{i} — {next(r.label for r in runs if r.id == i)}",
                default=[],
            )
            if len(compare_ids) >= 2:
                # KPI matrix: rows = metrics, cols = run ids
                metric_grid: dict[str, dict[int, float]] = defaultdict(dict)
                for rid in compare_ids:
                    for (metric, scope, key, value) in run_repo.get_kpis(rid):
                        if scope != "global":
                            continue
                        col_label = f"{metric}" if key == "all" else f"{metric}.{key}"
                        metric_grid[col_label][rid] = value
                kpi_diff_rows = []
                for metric in sorted(metric_grid):
                    row = {"Métrica": metric}
                    for rid in compare_ids:
                        row[f"#{rid}"] = metric_grid[metric].get(rid, "-")
                    kpi_diff_rows.append(row)
                if kpi_diff_rows:
                    st.markdown("**KPIs globales**")
                    st.dataframe(pd.DataFrame(kpi_diff_rows), width='stretch', hide_index=True)

                # Compliance matrix: rows = rules, cols = run ids (% Cumplimiento)
                comp_grid: dict[str, dict[int, float]] = defaultdict(dict)
                for rid in compare_ids:
                    for (rule_id, sat, vio, pct, _) in run_repo.get_compliance(rid):
                        comp_grid[rule_id][rid] = pct
                comp_rows = []
                for rule_id in sorted(comp_grid):
                    rule = RULE_REGISTRY.get(rule_id)
                    label = rule.label if rule else rule_id
                    row = {"Regla": label}
                    for rid in compare_ids:
                        v = comp_grid[rule_id].get(rid)
                        row[f"#{rid} %"] = round(v, 1) if v is not None else "-"
                    comp_rows.append(row)
                if comp_rows:
                    st.markdown("**% cumplimiento por regla**")
                    st.dataframe(pd.DataFrame(comp_rows), width='stretch', hide_index=True)

            st.divider()
            st.subheader("Detalle de corrida")
            selected = st.selectbox(
                "Selecciona run",
                options=[r.id for r in runs],
                format_func=lambda i: f"#{i} — {next(r.label for r in runs if r.id == i)}",
            )
            if selected:
                meta = run_repo.get(selected)
                cols = st.columns(4)
                cols[0].metric("Status", meta.status)
                cols[1].metric("Master (s)", f"{meta.master_seconds:.1f}" if meta.master_seconds else "-")
                cols[2].metric("Student (s)", f"{meta.student_seconds:.1f}" if meta.student_seconds else "-")
                cols[3].metric("Objective", f"{meta.objective:.0f}" if meta.objective else "-")

                kpis = run_repo.get_kpis(selected)
                if kpis:
                    st.markdown("**KPIs globales**")
                    kpi_rows = [
                        {"Métrica": m, "Scope": s, "Key": k, "Valor": v}
                        for (m, s, k, v) in kpis
                    ]
                    st.dataframe(pd.DataFrame(kpi_rows), width='stretch', hide_index=True)

                comp_rows_one = run_repo.get_compliance(selected)
                if comp_rows_one:
                    st.markdown("**Cumplimiento por regla**")
                    rows_view = []
                    for (rid, sat, vio, pct, _) in comp_rows_one:
                        rule = RULE_REGISTRY.get(rid)
                        rows_view.append({
                            "Regla": rule.label if rule else rid,
                            "Tipo": rule.kind if rule else "?",
                            "Cumplidas": sat,
                            "Violadas": vio,
                            "%": round(pct, 1),
                        })
                    st.dataframe(pd.DataFrame(rows_view), width='stretch', hide_index=True)

                if st.button("Cargar este run como dataset activo"):
                    bmeta, ds_loaded = bundle_repo.get(meta.bundle_id)
                    rmeta, hard, soft, _ = rules_repo.get(meta.rule_config_id)
                    new_cfg = ds_loaded.config.model_copy(update={"hard": hard, "soft": soft})
                    ds_loaded = ds_loaded.model_copy(update={"config": new_cfg})
                    _set_dataset(ds_loaded, f"run #{selected} (bundle #{bmeta.id})")
                    st.session_state["bundle_id"] = bmeta.id
                    st.session_state["rule_config_id"] = rmeta.id
                    st.session_state["last_run_id"] = selected
                    st.success(f"Cargado run #{selected}. Ve a la tab Solve o Browse.")
                    st.rerun()


# ----------------------------------------------------------------------------
# TAB 4: SCENARIOS
# ----------------------------------------------------------------------------

with tab_scenarios:
    if not _has_dataset():
        st.info("Load a dataset first.")
    else:
        ds = st.session_state["dataset"]

        preset = st.selectbox("Preset", list(PRESETS.keys()))
        col_l, col_r = st.columns(2)
        with col_l:
            sc_master_time = st.number_input("Master time per scenario (s)", value=20, min_value=5, max_value=300, step=5, key="sc_master")
        with col_r:
            sc_student_time = st.number_input("Student time per scenario (s)", value=60, min_value=10, max_value=600, step=10, key="sc_student")

        specs = PRESETS[preset]
        st.caption(f"Will run {len(specs)} scenario(s). Estimated total time: "
                   f"{(sc_master_time + sc_student_time) * len(specs)}s.")

        # v4.27 — option to persist each scenario as a separate run.
        persist_scenarios = False
        if st.session_state.get("persist_enabled"):
            persist_scenarios = st.checkbox(
                "Persistir cada escenario como run en SQLite",
                value=True,
                help="Cada escenario crea un run separado con su rule_config y compliance, "
                     "comparable luego en la tab Runs.",
            )

        if st.button("▶️ Run scenarios", type="primary", width='stretch'):
            results = []
            persisted_run_ids: list[int] = []
            progress = st.progress(0.0, text="Running scenarios...")
            log_area = st.empty()
            log_lines: list[str] = []

            from src.scheduler.scenarios import _apply_overrides as scenario_apply
            db = _get_db() if persist_scenarios else None

            for i, spec in enumerate(specs, 1):
                progress.progress((i - 1) / len(specs), text=f"[{i}/{len(specs)}] {spec.name}...")
                if db is not None:
                    # Persistence path: build a per-scenario dataset and route through runner
                    import copy
                    ds_run = copy.deepcopy(ds)
                    scenario_apply(ds_run, spec.overrides)
                    try:
                        outcome = solve_and_persist(
                            ds_run,
                            db=db,
                            bundle_id=st.session_state.get("bundle_id"),
                            bundle_label=f"scenarios-{preset}",
                            bundle_source_kind=(
                                "xlsx" if st.session_state["dataset_source"].startswith("columbus")
                                else "sample"
                            ),
                            rule_config_label=f"scenario:{spec.name}",
                            run_label=f"scenario:{spec.name}",
                            master_time=sc_master_time,
                            student_time=sc_student_time,
                        )
                        if outcome.run_id:
                            persisted_run_ids.append(outcome.run_id)
                        # Adapt to the same shape as run_scenario for the comparison table.
                        from src.scheduler.scenarios import ScenarioResult
                        r = ScenarioResult(
                            name=spec.name,
                            description=spec.description,
                            overrides=spec.overrides,
                            master_status=outcome.master_status,
                            student_status=outcome.student_status,
                            master_solve_seconds=outcome.result.solve_seconds * 0.5,
                            student_solve_seconds=outcome.result.solve_seconds * 0.5,
                            kpi=outcome.kpi if outcome.result.master else None,
                            n_unmet_rank1=len(outcome.result.unscheduled_requests),
                            error=None if outcome.result.master else f"infeasible: {outcome.master_status}",
                        )
                    except Exception as exc:
                        from src.scheduler.scenarios import ScenarioResult
                        r = ScenarioResult(
                            name=spec.name,
                            description=spec.description,
                            overrides=spec.overrides,
                            master_status="ERROR",
                            student_status="ERROR",
                            master_solve_seconds=0.0,
                            student_solve_seconds=0.0,
                            kpi=None,
                            n_unmet_rank1=0,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                else:
                    from src.scheduler.scenarios import run_scenario
                    r = run_scenario(ds, spec, master_time=sc_master_time, student_time=sc_student_time)
                results.append(r)
                if r.error:
                    log_lines.append(f"❌ {spec.name}: {r.error}")
                elif r.kpi:
                    log_lines.append(
                        f"✓ {spec.name}: electives {r.kpi.first_choice_elective_pct:.1f}% · "
                        f"balance {r.kpi.section_balance_max_dev} · unmet {r.n_unmet_rank1}"
                    )
                else:
                    log_lines.append(f"⚠️ {spec.name}: {r.master_status}/{r.student_status}")
                log_area.markdown("\n\n".join(log_lines))
            progress.progress(1.0, text="Done")
            if persisted_run_ids:
                st.success(f"Persistidos {len(persisted_run_ids)} run(s): {persisted_run_ids}. Ve a la tab Runs para comparar.")

            # Comparison table
            st.subheader("Comparison")
            rows = []
            for r in results:
                if r.kpi:
                    k = r.kpi
                    rows.append({
                        "Scenario": r.name,
                        "Description": r.description,
                        "Status": f"{r.master_status}/{r.student_status}",
                        "Fully Sched %": round(k.fully_scheduled_pct, 1),
                        "Required %": round(k.required_fulfillment_pct, 1),
                        "First-Choice %": round(k.first_choice_elective_pct, 1),
                        "Balance Dev": k.section_balance_max_dev,
                        "Unmet": r.n_unmet_rank1,
                        "Time (s)": round(r.master_solve_seconds + r.student_solve_seconds, 1),
                    })
                else:
                    rows.append({
                        "Scenario": r.name,
                        "Description": r.description,
                        "Status": "ERROR",
                        "First-Choice %": None,
                        "Balance Dev": None,
                        "Time (s)": round(r.master_solve_seconds + r.student_solve_seconds, 1),
                    })
            df = pd.DataFrame(rows)
            st.dataframe(df, width='stretch', hide_index=True)

            # Save markdown for download
            md = format_comparison(results)
            st.download_button(
                "📥 Download comparison.md",
                data=md,
                file_name=f"scenarios_{preset}.md",
                mime="text/markdown",
            )


# ----------------------------------------------------------------------------
# TAB 5: EXPORT
# ----------------------------------------------------------------------------

with tab_export:
    # v4.27 — optional run-picker: export from history instead of session.
    export_source = "session"
    history_run_id: int | None = None
    if st.session_state.get("persist_enabled"):
        db = _get_db()
        run_repo_e = RunRepo(db)
        bundles_e = InputBundleRepo(db)
        rules_e = RuleConfigRepo(db)
        runs_avail = run_repo_e.list_all(limit=50)
        completed_runs = [r for r in runs_avail if r.status == "completed"]
        if completed_runs:
            export_source = st.radio(
                "Fuente de export",
                options=["session", "history"],
                format_func=lambda x: "Sesión actual" if x == "session" else "Run histórico",
                horizontal=True,
            )
            if export_source == "history":
                history_run_id = st.selectbox(
                    "Selecciona run",
                    options=[r.id for r in completed_runs],
                    format_func=lambda i: f"#{i} — {next(r.label for r in completed_runs if r.id == i)}",
                )

    # Resolve (ds, master, students, unmet) based on export_source.
    if export_source == "history" and history_run_id is not None:
        try:
            from src.scheduler.persistence.serialize import (
                master_from_blob,
                students_from_blob,
                unmet_from_blob,
            )
            meta_e = run_repo_e.get(history_run_id)
            _, ds = bundles_e.get(meta_e.bundle_id)
            _, hard_e, soft_e, _ = rules_e.get(meta_e.rule_config_id)
            new_cfg_e = ds.config.model_copy(update={"hard": hard_e, "soft": soft_e})
            ds = ds.model_copy(update={"config": new_cfg_e})
            mb, sb, ub = run_repo_e.get_result_blobs(history_run_id)
            master = master_from_blob(mb)
            students = students_from_blob(sb)
            unmet = unmet_from_blob(ub)
            st.caption(f"Exportando run histórico #{history_run_id}")
        except Exception as exc:
            st.error(f"No se pudo cargar el run #{history_run_id}: {exc}")
            st.stop()
    elif not _has_solution():
        st.info("Run a solve first (tab 2) o activa persistencia y selecciona un run histórico.")
        st.stop()
    else:
        ds = st.session_state["dataset"]
        master = st.session_state["master"]
        students = st.session_state["students"]
        unmet = st.session_state["unmet"] or []

    if True:
        st.subheader("PowerSchool-compatible exports")
        st.caption("Three CSV files + a field mapping doc, ready to import into PowerSchool sandbox.")

        # Generate files into a temp dir, then offer downloads + zip
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            export_powerschool(ds, master, students, tmp)
            write_reports(ds, master, students, unmet, tmp / "reports")

            files = {
                "ps_sections.csv": tmp / "ps_sections.csv",
                "ps_enrollments.csv": tmp / "ps_enrollments.csv",
                "ps_master_schedule.csv": tmp / "ps_master_schedule.csv",
                "ps_field_mapping.md": tmp / "ps_field_mapping.md",
                "schedule_report.md": tmp / "reports" / "schedule_report.md",
                "sections_with_enrollment.csv": tmp / "reports" / "sections_with_enrollment.csv",
                "student_schedules.csv": tmp / "reports" / "student_schedules.csv",
                "teacher_loads.csv": tmp / "reports" / "teacher_loads.csv",
                "unmet_requests.csv": tmp / "reports" / "unmet_requests.csv",
            }
            for name, path in files.items():
                if not path.exists():
                    continue
                st.download_button(
                    f"📥 {name}",
                    data=path.read_bytes(),
                    file_name=name,
                    mime="text/csv" if name.endswith(".csv") else "text/markdown",
                    width='stretch',
                )

            # Bundled zip
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, path in files.items():
                    if path.exists():
                        zf.write(path, name)
            zbuf.seek(0)
            st.divider()
            st.download_button(
                "🎁 Download all as ZIP",
                data=zbuf.getvalue(),
                file_name="columbus_schedule_exports.zip",
                mime="application/zip",
                width='stretch',
                type="primary",
            )

        st.divider()
        st.subheader("Field mapping reference")
        st.caption("Adjust column names per the school's PS instance using PS Data Dictionary if needed.")
        st.markdown("""
| Engine column | PS field | Notes |
|---|---|---|
| SchoolID | School_Number | Hard-coded to school name; replace with school number |
| CourseID | Course_Number | Direct |
| SectionID | Section_Number | Engine uses dotted form (e.g. ENG12.1) |
| TeacherID | Teacher_Number | Direct |
| RoomID | Room | Direct |
| Period | Expression | Engine produces P01..P08 + ADV |
| Slots | (split into M/T/W/Th/F flags) | Engine produces "A1;D2;B4" |
| TermID | TermID | School year as a string |
| MaxEnrollment | Max_Enrollment | Direct |
""")
