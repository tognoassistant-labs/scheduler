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
from collections import defaultdict
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
                subtitle: str = "") -> str:
    """Render an HTML page with a 5x5 grid of (Day, Block) cells."""
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
            if (day, blk) == ("E", 3):
                content = '<div class="adv">Advisory</div>'
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
            cells.append(f'<td>{content or "&nbsp;"}</td>')
        cells.append('</tr>')
    cells.append('</tbody></table>')

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #222; }}
h1 {{ margin-bottom: 4px; }}
.subtitle {{ color: #666; margin-bottom: 16px; }}
table.grid {{ border-collapse: collapse; width: 100%; max-width: 1400px; }}
table.grid th, table.grid td {{ border: 1px solid #ccc; padding: 6px; vertical-align: top; min-width: 130px; height: 90px; }}
table.grid th {{ background: #f7f7f7; font-weight: 600; }}
.ent {{ padding: 4px 6px; border-radius: 3px; margin-bottom: 3px; font-size: 12px; }}
.ent .cn {{ font-weight: 600; }}
.ent .meta {{ color: #555; font-size: 11px; }}
.adv {{ background: #e0e0e0; padding: 6px; border-radius: 3px; font-style: italic; text-align: center; }}
.back {{ display: inline-block; margin-bottom: 16px; color: #2563eb; text-decoration: none; }}
.back:hover {{ text-decoration: underline; }}
</style></head>
<body>
<a class="back" href="index.html">← Volver al índice</a>
<h1>{escape(title)}</h1>
<div class="subtitle">{escape(subtitle)}</div>
{"".join(cells)}
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

    # Load schedule
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

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
    for sid, schedule_rows in by_student.items():
        meta = student_meta[sid]
        # Build (day, block) → entries
        grid: dict[tuple[str, int], list[dict]] = defaultdict(list)
        course_ids_seen: set[str] = set()
        for r in schedule_rows:
            for slot in parse_slots(r["Slots"]):
                grid[slot].append({
                    "course_id": r["CourseID"],
                    "course_name": r["CourseName"],
                    "section_id": r["SectionID"],
                    "teacher_or_student": r["TeacherName"],
                    "room": r["RoomName"],
                })
            course_ids_seen.add(r["CourseID"])
        n_courses = len([cid for cid in course_ids_seen if cid != "ADVHS01"])
        title = f'{meta["name"]} ({sid})'
        subtitle = f'Grado {meta["grade"]} · {n_courses} cursos asignados'
        html = render_grid(title, grid, subtitle)
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
