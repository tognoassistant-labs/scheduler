#!/usr/bin/env python3
"""Generate static HTML "poster" views from a built bundle.

Reads the bundle's friendly schedule CSV and produces:
  - One page per student (5x5 grid showing their week)
  - One page per teacher (5x5 grid showing their teaching load)
  - An index page linking to all of the above
  - A KPI summary page with v2 §10 metrics

Output goes into <bundle>/visor_html/. Open visor_html/index.html in any
browser. No server, no Streamlit, no install — just static files.

Usage:
    python scheduler/scripts/generate_demo_posters.py \
        scheduler/data/_client_bundle_v4/HS_2026-2027_real
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from html import escape
from pathlib import Path


DAYS = ["A", "B", "C", "D", "E"]
BLOCKS = [1, 2, 3, 4, 5]


def slot_color(course_id: str) -> str:
    """Stable pastel color per course (hash-based)."""
    h = sum(ord(c) for c in course_id)
    palette = [
        "#FCE5CD", "#D9EAD3", "#CFE2F3", "#EAD1DC", "#FFF2CC",
        "#D0E0E3", "#F4CCCC", "#D9D2E9", "#FFE599", "#B6D7A8",
    ]
    return palette[h % len(palette)]


def render_grid(title: str, schedule: dict[tuple[str, int], list[dict]],
                subtitle: str = "", diagnosis_html: str = "",
                free_slots: set[tuple[str, int]] | None = None) -> str:
    """Render an HTML page with a 5x5 grid of (Day, Block) cells.

    `free_slots`: when provided, mark (day, block) cells with a green border
    if they belong to free_slots (= where the student has time available).
    `diagnosis_html`: optional HTML rendered below the grid.
    """
    cells = []
    cells.append(f'<table class="grid"><thead><tr><th></th>')
    for day in DAYS:
        cells.append(f'<th>Día {day}</th>')
    cells.append('</tr></thead><tbody>')
    for blk in BLOCKS:
        cells.append(f'<tr><th>Bloque {blk}</th>')
        for day in DAYS:
            entries = schedule.get((day, blk), [])
            content = ""
            css_class = "free" if free_slots and (day, blk) in free_slots and not entries else ""
            if (day, blk) == ("E", 3):
                content = '<div class="adv">Advisory</div>'
                css_class = ""
            for e in entries:
                bg = slot_color(e["course_id"])
                content += (
                    f'<div class="ent" style="background:{bg}">'
                    f'<div class="cn">{escape(e["course_name"])}</div>'
                    f'<div class="meta">{escape(e["section_id"])} · '
                    f'{escape(e.get("teacher_or_student", ""))}</div>'
                    f'<div class="meta">Aula {escape(str(e.get("room", "")))}</div>'
                    f'</div>'
                )
            if css_class:
                content = (content or "") + '<div class="freebadge">libre</div>'
            cells.append(f'<td class="{css_class}">{content or "&nbsp;"}</td>')
        cells.append('</tr>')
    cells.append('</tbody></table>')

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #222; max-width: 1400px; }}
h1 {{ margin-bottom: 4px; }}
.subtitle {{ color: #666; margin-bottom: 16px; }}
table.grid {{ border-collapse: collapse; width: 100%; max-width: 1400px; margin-bottom: 32px; }}
table.grid th, table.grid td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; min-width: 130px; height: 90px; position: relative; }}
table.grid th {{ background: #f7f7f7; font-weight: 600; }}
table.grid td.free {{ background: #f0fdf4; border: 2px dashed #22c55e; }}
.freebadge {{ position: absolute; bottom: 4px; right: 4px; font-size: 10px; color: #16a34a; font-style: italic; }}
.ent {{ padding: 4px 6px; border-radius: 3px; margin-bottom: 3px; font-size: 12px; }}
.ent .cn {{ font-weight: 600; }}
.ent .meta {{ color: #555; font-size: 11px; }}
.adv {{ background: #e0e0e0; padding: 6px; border-radius: 3px; font-style: italic; text-align: center; }}
.back {{ display: inline-block; margin-bottom: 16px; color: #2563eb; text-decoration: none; }}
.back:hover {{ text-decoration: underline; }}

/* Diagnosis cards */
.diag-section {{ margin-top: 24px; }}
.diag-section h2 {{ font-size: 18px; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 2px solid #fbbf24; }}
.diag-card {{ border: 1px solid #fbbf24; background: #fffbeb; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px; }}
.diag-card .header {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
.diag-card .header .icon {{ font-size: 18px; }}
.diag-card .header .name {{ font-weight: 600; font-size: 15px; color: #92400e; }}
.diag-card .header .id {{ color: #999; font-size: 12px; }}
.diag-card .row {{ margin: 8px 0; }}
.diag-card .label {{ font-weight: 600; color: #555; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }}
.diag-card .value {{ font-size: 13px; color: #222; line-height: 1.4; }}
.diag-card .proposal {{ background: #f0fdf4; border-left: 3px solid #22c55e; padding: 8px 12px; margin-top: 8px; border-radius: 4px; }}
.diag-card .proposal .label {{ color: #16a34a; }}
.legend {{ font-size: 12px; color: #666; margin-bottom: 16px; }}
.legend .swatch {{ display: inline-block; width: 12px; height: 12px; border: 2px dashed #22c55e; background: #f0fdf4; margin-right: 4px; vertical-align: middle; }}
</style></head>
<body>
<a class="back" href="index.html">← Volver al índice</a>
<h1>{escape(title)}</h1>
<div class="subtitle">{escape(subtitle)}</div>
{"<div class='legend'><span class='swatch'></span> celdas en verde = el estudiante tiene este slot libre (candidato para nuevas secciones).</div>" if free_slots else ""}
{"".join(cells)}
{diagnosis_html}
</body></html>
"""


def parse_slots(slots_str: str) -> list[tuple[str, int]]:
    """Parse 'A2;D3;B5' → [('A',2), ('D',3), ('B',5)]. Skip ADVISORY."""
    if not slots_str or slots_str == "E3":
        return [("E", 3)]
    out = []
    for piece in slots_str.split(";"):
        piece = piece.strip()
        if len(piece) >= 2 and piece[0] in DAYS:
            try:
                out.append((piece[0], int(piece[1:])))
            except ValueError:
                pass
    return out


def diagnose_student_unmet(
    student_id: str,
    student_grade: int,
    missing_courses: list[str],
    student_busy_slots: set[tuple[str, int]],
    course_meta: dict[str, dict],
    sections_of_course: dict[str, list[dict]],
    teacher_load: dict[str, int],
    teacher_name: dict[str, str],
    student_separations: dict[str, set[str]],
    students_in_section: dict[str, set[str]],
    student_restricted_teachers: dict[str, set[str]],
) -> str:
    """Build the HTML cards explaining each missing course + a proposal."""
    if not missing_courses:
        return ""

    ALL_SLOTS = [(d, b) for d in DAYS for b in BLOCKS if (d, b) != ("E", 3)]
    free_slots = [s for s in ALL_SLOTS if s not in student_busy_slots]
    free_slots_str = ", ".join(f"{d}{b}" for d, b in free_slots)

    cards = ['<div class="diag-section">']
    cards.append(f'<h2>⚠️ {len(missing_courses)} curso(s) pendiente(s) — diagnóstico y propuesta</h2>')
    cards.append(f'<div class="legend">Slots libres del estudiante: <strong>{free_slots_str or "(ninguno)"}</strong></div>')

    for cid in missing_courses:
        meta = course_meta.get(cid, {})
        course_name = meta.get("name", cid)
        course_dept = meta.get("department", "?")
        secs = sections_of_course.get(cid, [])

        # Diagnose why each existing section didn't fit
        section_status = []
        all_have_conflict = True
        any_full = False
        any_separation_block = False
        any_restricted_teacher = False
        for s in secs:
            sid = s["section_id"]
            slots = s["slots"]
            t_id = s["teacher_id"]
            t_nm = teacher_name.get(t_id, t_id)
            enrolled = s["enrolled"]
            cap = s["max_size"]
            slot_str = ", ".join(f"{d}{b}" for d, b in sorted(slots))
            issues = []
            conflicts_with_busy = [s_ for s_ in slots if s_ in student_busy_slots]
            if conflicts_with_busy:
                issues.append(f"choca en {', '.join(f'{d}{b}' for d, b in sorted(conflicts_with_busy))}")
            else:
                all_have_conflict = False
            if enrolled >= cap:
                issues.append(f"sección llena ({enrolled}/{cap})")
                any_full = True
            # Check separation peers in this section
            peers = students_in_section.get(sid, set())
            separated_peers = peers & student_separations.get(student_id, set())
            if separated_peers:
                issues.append(f"contiene a {len(separated_peers)} estudiante(s) separado(s) por consejo")
                any_separation_block = True
            if t_id in student_restricted_teachers.get(student_id, set()):
                issues.append(f"profesor en lista de restringidos")
                any_restricted_teacher = True
            status_text = "✓ disponible" if not issues else " · ".join(issues)
            section_status.append(
                f'<li><code>{escape(sid)}</code> — {escape(t_nm)} — slots <code>{escape(slot_str)}</code> — {enrolled}/{cap} — <em>{escape(status_text)}</em></li>'
            )

        # Determine root cause
        if not secs:
            cause = "el curso no tiene secciones generadas en este bundle (ej. profesor sin asignar)"
        elif any_full and all_have_conflict:
            cause = "todas las secciones existentes están llenas Y sus horarios chocan con otros required del estudiante"
        elif all_have_conflict:
            cause = "los horarios de todas las secciones existentes chocan con otros cursos required del estudiante (grid-bound)"
        elif any_full:
            cause = "las secciones donde cabría temporalmente están llenas (capacity-bound)"
        elif any_separation_block:
            cause = "todas las secciones donde cabría tienen un estudiante con quien el consejo pidió mantener separado"
        elif any_restricted_teacher:
            cause = "el profesor de las secciones disponibles está en la lista de profesores que el estudiante debe evitar"
        else:
            cause = "razón mixta o sutil — revisar caso por caso"

        # Proposal: find candidate slot triplets
        # Heuristic: pick 3 free slots from same scheme would be ideal, but
        # without the bell rotation we use the simple "top 3 free slots".
        candidate_slots = free_slots[:3]
        candidate_slots_str = ", ".join(f"{d}{b}" for d, b in candidate_slots)

        # Find a teacher with capacity (load < 6 considered "available")
        existing_teachers_of_course = [s["teacher_id"] for s in secs]
        teacher_with_capacity = None
        for tid in existing_teachers_of_course:
            if teacher_load.get(tid, 0) < 6:
                teacher_with_capacity = (tid, teacher_load.get(tid, 0))
                break
        if teacher_with_capacity:
            t_id, t_n = teacher_with_capacity
            teacher_proposal = f"profesor existente con carga moderada: <strong>{escape(teacher_name.get(t_id, t_id))}</strong> ({t_n} secciones hoy → puede tomar 1 más)"
        elif existing_teachers_of_course:
            min_t = min(existing_teachers_of_course, key=lambda t: teacher_load.get(t, 0))
            teacher_proposal = f"todos los profesores actuales del curso están a carga alta ({teacher_load.get(min_t, 0)}+ secciones); requiere contratar profesor nuevo o re-asignar"
        else:
            teacher_proposal = "no hay profesor asignado al curso — requiere contratación"

        # Render the card
        cards.append('<div class="diag-card">')
        cards.append('<div class="header">')
        cards.append(f'<span class="icon">❌</span><span class="name">{escape(course_name)}</span><span class="id">({escape(cid)} · {escape(course_dept)})</span>')
        cards.append('</div>')

        cards.append('<div class="row"><div class="label">Estado actual de las secciones</div>')
        if secs:
            cards.append(f'<ul style="margin: 4px 0 0 18px; padding: 0;">{"".join(section_status)}</ul>')
        else:
            cards.append('<div class="value">No hay secciones en el bundle.</div>')
        cards.append('</div>')

        cards.append(f'<div class="row"><div class="label">Por qué no entró este estudiante</div><div class="value">{escape(cause)}.</div></div>')

        cards.append('<div class="proposal">')
        cards.append(f'<div class="label">Propuesta para incluirlo</div>')
        if candidate_slots:
            cards.append(
                f'<div class="value">Abrir 1 sección adicional de <strong>{escape(course_name)}</strong> en slots '
                f'<code>{escape(candidate_slots_str)}</code> (donde este estudiante tiene tiempo libre). '
                f'Asignación de docente sugerida: {teacher_proposal}.</div>'
            )
        else:
            cards.append(
                f'<div class="value">El estudiante NO tiene 3 slots libres en su semana actual. '
                f'Para incluir este curso habría que mover otro de sus required a otro horario primero, '
                f'o aceptar la falta como inevitable (caso pigeonhole real).</div>'
            )
        cards.append('</div>')

        cards.append('</div>')  # diag-card

    cards.append('</div>')  # diag-section
    return "\n".join(cards)


def build_index(out_dir: Path, students: list[dict], teachers: list[dict],
                kpi_summary: str) -> None:
    rows_stu = "\n".join(
        f'<li><a href="student_{s["id"]}.html">{escape(s["id"])} · '
        f'{escape(s["name"])} · G{s["grade"]} · '
        f'{s["n_assigned"]}/{s["n_requested"]} cursos</a></li>'
        for s in sorted(students, key=lambda x: (int(x["grade"]), x["id"]))
    )
    rows_tch = "\n".join(
        f'<li><a href="teacher_{escape(t["id"])}.html">{escape(t["id"])} · '
        f'{escape(t["name"])} · {t["n_sections"]} sec</a></li>'
        for t in sorted(teachers, key=lambda x: x["name"])
    )
    page = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Visor — Bundle Columbus HS 2026-2027</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #222; max-width: 1100px; }}
h1 {{ margin-bottom: 4px; }}
h2 {{ margin-top: 32px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
.kpi {{ background: #f9f9f9; padding: 16px; border-radius: 6px; margin-bottom: 24px; }}
.kpi pre {{ margin: 0; font-size: 13px; }}
ul.cols {{ column-count: 3; column-gap: 24px; padding-left: 18px; }}
ul.cols li {{ margin-bottom: 4px; }}
a {{ color: #2563eb; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style></head>
<body>
<h1>📚 Bundle Columbus HS 2026-2027</h1>
<p>Visor estático del horario generado. Click en cualquier estudiante o profesor para ver su semana.</p>

<div class="kpi">
<h2 style="margin-top:0;border:none;">KPIs del bundle actual</h2>
<pre>{escape(kpi_summary)}</pre>
</div>

<h2>Estudiantes ({len(students)})</h2>
<ul class="cols">{rows_stu}</ul>

<h2>Profesores ({len(teachers)})</h2>
<ul class="cols">{rows_tch}</ul>
</body></html>
"""
    (out_dir / "index.html").write_text(page)


def main(bundle: Path) -> None:
    csv_path = bundle / "horario_estudiantes" / "student_schedules_friendly.csv"
    if not csv_path.exists():
        print(f"❌ Not found: {csv_path}")
        sys.exit(1)

    out_dir = bundle / "visor_html"
    out_dir.mkdir(exist_ok=True)

    # Load main schedule
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    # Load additional data for diagnostic
    def _load(path):
        with (bundle / path).open() as f:
            return list(csv.DictReader(f))

    courses_csv = _load("input_data/courses.csv")
    teachers_csv = _load("input_data/teachers.csv")
    sections_csv = _load("input_data/sections.csv")
    behavior_csv = _load("input_data/behavior.csv")
    enrollment_csv = _load("horario_estudiantes/sections_with_enrollment.csv")
    schedules_csv = _load("horario_estudiantes/student_schedules.csv")

    # Master schedule for slot mapping
    master_csv_path = bundle / "powerschool_upload" / "ps_master_schedule.csv"
    master_csv = []
    if master_csv_path.exists():
        with master_csv_path.open() as f:
            master_csv = list(csv.DictReader(f))

    # Build helper structures
    course_meta = {c["course_id"]: {"name": c.get("name", ""), "department": c.get("department", "")}
                   for c in courses_csv}
    teacher_name_map = {t["teacher_id"]: t.get("name", t["teacher_id"]) for t in teachers_csv}

    # Per-section: enrolled, max_size, slots, teacher
    enrolled_by_sec = {s["section_id"]: int(s["enrolled"]) for s in enrollment_csv}
    max_size_by_sec = {s["section_id"]: int(s["max_size"]) for s in enrollment_csv}
    teacher_by_sec = {s["section_id"]: s["teacher_id"] for s in sections_csv}
    slots_by_sec: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for r in master_csv:
        slots_by_sec[r["Section_ID_Internal"]].add((r["Day"], int(r["Block"])))

    # Sections per course (for the diagnostic pass)
    sections_of_course: dict[str, list[dict]] = defaultdict(list)
    for s in sections_csv:
        sid = s["section_id"]
        sections_of_course[s["course_id"]].append({
            "section_id": sid,
            "teacher_id": s["teacher_id"],
            "slots": slots_by_sec.get(sid, set()),
            "enrolled": enrolled_by_sec.get(sid, 0),
            "max_size": max_size_by_sec.get(sid, int(s.get("max_size", 25) or 25)),
        })

    # Teacher load (count of sections per teacher)
    teacher_load = Counter(s["teacher_id"] for s in sections_csv)

    # Behavior matrix → separations per student
    student_separations: dict[str, set[str]] = defaultdict(set)
    for r in behavior_csv:
        if r["kind"] == "separation":
            student_separations[r["student_a"]].add(r["student_b"])
            student_separations[r["student_b"]].add(r["student_a"])

    # Restricted teachers per student (placeholder — would need to load from students.csv)
    student_restricted_teachers: dict[str, set[str]] = defaultdict(set)
    students_csv = _load("input_data/students.csv")
    for s in students_csv:
        rt = (s.get("restricted_teacher_ids") or "").split("|")
        student_restricted_teachers[s["student_id"]] = {t for t in rt if t}

    # Students in each section (for separation checks)
    students_in_section: dict[str, set[str]] = defaultdict(set)
    for r in schedules_csv:
        for sid in (r["section_ids"] or "").split("|"):
            if sid:
                students_in_section[sid].add(r["student_id"])

    # Missing courses per student (excludes Advisory)
    missing_by_student: dict[str, list[str]] = defaultdict(list)
    for r in schedules_csv:
        for cid in (r.get("missing_courses") or "").split("|"):
            if cid:
                missing_by_student[r["student_id"]].append(cid)

    # Group by student
    by_student: dict[str, list[dict]] = defaultdict(list)
    student_meta: dict[str, dict] = {}
    by_teacher: dict[str, list[dict]] = defaultdict(list)
    teacher_meta: dict[str, dict] = {}
    for r in rows:
        by_student[r["StudentID"]].append(r)
        student_meta[r["StudentID"]] = {
            "id": r["StudentID"],
            "name": r["StudentName"],
            "grade": r["Grade"],
        }
        by_teacher[r["TeacherID"]].append(r)
        teacher_meta[r["TeacherID"]] = {
            "id": r["TeacherID"],
            "name": r["TeacherName"],
        }

    # Generate per-student pages
    ALL_SLOTS = [(d, b) for d in DAYS for b in BLOCKS if (d, b) != ("E", 3)]
    for sid, schedule_rows in by_student.items():
        meta = student_meta[sid]
        # Build (day, block) → entries + busy slots
        grid: dict[tuple[str, int], list[dict]] = defaultdict(list)
        course_ids_seen: set[str] = set()
        busy_slots: set[tuple[str, int]] = set()
        for r in schedule_rows:
            for slot in parse_slots(r["Slots"]):
                grid[slot].append({
                    "course_id": r["CourseID"],
                    "course_name": r["CourseName"],
                    "section_id": r["SectionID"],
                    "teacher_or_student": r["TeacherName"],
                    "room": r["RoomName"],
                })
                if slot != ("E", 3):
                    busy_slots.add(slot)
            course_ids_seen.add(r["CourseID"])
        n_courses = len([cid for cid in course_ids_seen if cid != "ADVHS01"])

        # Diagnostic + proposal
        missing = missing_by_student.get(sid, [])
        diag_html = diagnose_student_unmet(
            student_id=sid,
            student_grade=int(meta["grade"]),
            missing_courses=missing,
            student_busy_slots=busy_slots,
            course_meta=course_meta,
            sections_of_course=sections_of_course,
            teacher_load=teacher_load,
            teacher_name=teacher_name_map,
            student_separations=student_separations,
            students_in_section=students_in_section,
            student_restricted_teachers=student_restricted_teachers,
        )

        free_slots = {s for s in ALL_SLOTS if s not in busy_slots} if missing else set()

        title = f'{meta["name"]} ({sid})'
        if missing:
            subtitle = f'Grado {meta["grade"]} · {n_courses} cursos asignados · ⚠️ {len(missing)} pendiente(s)'
        else:
            subtitle = f'Grado {meta["grade"]} · {n_courses} cursos asignados · ✅ horario completo'
        html = render_grid(title, grid, subtitle, diagnosis_html=diag_html, free_slots=free_slots)
        (out_dir / f"student_{sid}.html").write_text(html)

    # Generate per-teacher pages
    for tid, schedule_rows in by_teacher.items():
        meta = teacher_meta[tid]
        grid: dict[tuple[str, int], list[dict]] = defaultdict(list)
        sections_seen: set[str] = set()
        for r in schedule_rows:
            for slot in parse_slots(r["Slots"]):
                grid[slot].append({
                    "course_id": r["CourseID"],
                    "course_name": r["CourseName"],
                    "section_id": r["SectionID"],
                    "teacher_or_student": f"({r['StudentName']})",
                    "room": r["RoomName"],
                })
            sections_seen.add(r["SectionID"])
        title = f'Profesor: {meta["name"]} ({tid})'
        subtitle = f'{len(sections_seen)} secciones asignadas'
        html = render_grid(title, grid, subtitle)
        (out_dir / f"teacher_{tid}.html").write_text(html)

    # Index
    students_list = []
    for sid, meta in student_meta.items():
        sched = by_student[sid]
        course_ids = {r["CourseID"] for r in sched if r["CourseID"] != "ADVHS01"}
        students_list.append({**meta, "n_assigned": len(course_ids), "n_requested": len(course_ids)})
    teachers_list = []
    for tid, meta in teacher_meta.items():
        sections = {r["SectionID"] for r in by_teacher[tid]}
        teachers_list.append({**meta, "n_sections": len(sections)})

    # KPI summary from KPI report if available
    kpi_summary = "(KPI report not found in bundle)"
    kpi_path = bundle.parent / "02_KPI_REPORT.md"
    if kpi_path.exists():
        text = kpi_path.read_text()
        # Extract the table
        in_table = False
        out_lines = []
        for line in text.splitlines():
            if "| Metric" in line or "| Fully scheduled" in line:
                in_table = True
            if in_table:
                out_lines.append(line)
                if line.strip() == "" and len(out_lines) > 3:
                    break
        kpi_summary = "\n".join(out_lines).strip() or text[:1500]

    build_index(out_dir, students_list, teachers_list, kpi_summary)

    n_pages = len(by_student) + len(by_teacher) + 1
    print(f"✅ Generated {n_pages} pages in {out_dir}")
    print(f"   Open: file://{out_dir.absolute()}/index.html")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <bundle_dir>")
        sys.exit(1)
    main(Path(sys.argv[1]))
