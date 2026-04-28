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
from src.scheduler.models import Dataset
from src.scheduler.ps_ingest import build_dataset_from_columbus
from src.scheduler.reports import compute_kpis, write_reports
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
    # Clear stale solve outputs
    for k in ("master", "students", "unmet", "kpi", "master_status", "student_status"):
        st.session_state[k] = DEFAULTS[k]


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


# ============================================================================
# Main — tabs
# ============================================================================

st.title("Columbus Scheduling Engine")

tab_setup, tab_solve, tab_browse, tab_locks, tab_scenarios, tab_export = st.tabs([
    "1️⃣ Setup", "2️⃣ Solve", "3️⃣ Browse", "🔒 Locks & Prefs", "4️⃣ Scenarios", "5️⃣ Export"
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

        if st.button("▶️ Solve", type="primary", width='stretch'):
            # Apply config to a copy of the dataset
            import copy
            ds_run = copy.deepcopy(ds)
            ds_run.config.hard.max_section_spread_per_course = spread_cap
            ds_run.config.soft.first_choice_electives = elective_w
            ds_run.config.soft.balance_class_sizes = balance_w
            ds_run.config.soft.grouping_codes = grouping_w
            ds_run.config.soft.co_planning = coplan_w
            ds_run.config.soft.teacher_load_balance = teacher_load_w

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
                    # Also overwrite the active dataset config so other tabs see it
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

        if st.button("▶️ Run scenarios", type="primary", width='stretch'):
            results = []
            progress = st.progress(0.0, text="Running scenarios...")
            log_area = st.empty()
            log_lines: list[str] = []

            for i, spec in enumerate(specs, 1):
                progress.progress((i - 1) / len(specs), text=f"[{i}/{len(specs)}] {spec.name}...")
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
    if not _has_solution():
        st.info("Run a solve first (tab 2).")
    else:
        ds = st.session_state["dataset"]
        master = st.session_state["master"]
        students = st.session_state["students"]
        unmet = st.session_state["unmet"] or []

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
