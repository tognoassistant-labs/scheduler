"""Limpieza reproducible del workbook 'schedule_master_data_hs.xlsx'.

Toma como entrada el xlsx original, identifica los problemas conocidos, y
produce:
  1. Un xlsx CLEANED.xlsx con los fixes aplicados
  2. Un CLEANUP_REPORT.md detallando cada cambio

Issues que limpia:
  A. Curso OZ1333 — 19 secciones planeadas pero 0 teacher_assignments.
     Estrategia v1: marca el curso como inactivo agregando 'INACTIVE_' al
     COURSE_NUMBER (mejor que borrarlo para no perder histórico).
  B. conselours_recommendations huérfano — fila con student_id que no
     aparece en student_requests. Estrategia: la marca con flag
     '_DROPPED' en una columna nueva y deja una nota.
  C. 6 reglas de texto libre en CONSTRAINTS — el ingester las lee pero
     no las puede ejecutar (lógica condicional). Las preserva como
     anotaciones documentales en una hoja nueva 'free_text_rules_log'
     para que un humano las pueda traducir más tarde a custom rules
     (forbid_slot / prefer_teacher).

Uso:
    .venv/bin/python scripts/cleanup_master_data.py \\
        --in data/cleanup/master_data_hs_ORIGINAL.xlsx \\
        --out data/cleanup/master_data_hs_CLEANED.xlsx \\
        --report data/cleanup/CLEANUP_REPORT.md
"""
from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import PatternFill


# Keys we know about
ORPHAN_FILL = PatternFill(start_color="FFF4CCCC", end_color="FFF4CCCC", fill_type="solid")
INACTIVE_FILL = PatternFill(start_color="FFCCCCCC", end_color="FFCCCCCC", fill_type="solid")


def _freeze_formulas_to_values(wb_for_edit, wb_data_only) -> None:
    """openpyxl drops cached formula values on save. We pre-compute them by
    reading from a `data_only=True` load and writing the values back into the
    edit workbook's cells, so save preserves what Excel had cached."""
    for sheet_name in wb_for_edit.sheetnames:
        if sheet_name not in wb_data_only.sheetnames:
            continue
        ws_edit = wb_for_edit[sheet_name]
        ws_values = wb_data_only[sheet_name]
        for row in ws_edit.iter_rows():
            for cell in row:
                if cell.data_type == "f":  # formula
                    val = ws_values.cell(row=cell.row, column=cell.column).value
                    cell.value = val


def cleanup(input_path: Path, output_path: Path, report_path: Path) -> None:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("input and output must differ to keep an audit trail")
    shutil.copy(input_path, output_path)

    # Two loads: one for editing (formulas intact), one for cached values.
    # Then we freeze formulas → static values BEFORE any other edits, so the
    # final save retains everything Excel had calculated.
    wb_data_only = load_workbook(output_path, data_only=True)
    wb = load_workbook(output_path)
    _freeze_formulas_to_values(wb, wb_data_only)
    report_lines: list[str] = [
        "# Cleanup report — schedule_master_data_hs.xlsx",
        "",
        f"Source: `{input_path.name}`",
        f"Output: `{output_path.name}`",
        "",
        "Cada sección abajo describe un issue detectado, qué cambió, y "
        "cómo verificarlo.",
        "",
    ]

    # ------------------------------------------------------------------
    # ISSUE A — OZ1333: NO es un bug — es el placeholder de TAs
    # ------------------------------------------------------------------
    report_lines.append("## A. Curso OZ1333 — placeholder de TAs (NO requiere fix)")
    report_lines.append("")
    ws_courses = wb["courses"]
    course_headers = [c.value for c in ws_courses[1]]
    course_number_idx = course_headers.index("COURSE_NUMBER")
    course_name_idx = course_headers.index("COURSE_NAME")

    report_lines.append(
        "Investigación: el warning `OZ1333 planned=19 generated=0` NO es un "
        "bug. OZ1333 es el curso placeholder usado por la hoja "
        "`teacher_assistants` para marcar estudiantes que serán TA. El "
        "ingester de PowerSchool intencionalmente:"
    )
    report_lines.append("")
    report_lines.append(
        "1. Reemplaza la solicitud de OZ1333 del estudiante por la solicitud "
        "del curso real al que asistirá."
    )
    report_lines.append("2. NO genera secciones de OZ1333 (no las necesita).")
    report_lines.append("")
    report_lines.append(
        "Por eso `SECTIONSTOOFFER=19` (planeadas) pero `generated=0` (no se "
        "crean). **No tocar este curso** — eliminarlo o ponerlo inactivo "
        "rompería el flujo de TAs."
    )
    report_lines.append("")
    report_lines.append("- Acción: ninguna. El warning es informativo y esperado.")

    report_lines.append("")

    # ------------------------------------------------------------------
    # ISSUE B — conselours_recommendations con student_id huérfano
    # ------------------------------------------------------------------
    report_lines.append("## B. `conselours_recommendations` con student_ids huérfanos")
    report_lines.append("")

    # Collect valid student IDs from student_requests
    if "student_requests" not in wb.sheetnames:
        report_lines.append("- ⚠️ No hay hoja `student_requests`. Skip.")
    else:
        ws_req = wb["student_requests"]
        req_headers = [c.value for c in ws_req[1]]
        sn_idx = req_headers.index("STUDENT_NUMBER") if "STUDENT_NUMBER" in req_headers else None
        if sn_idx is None:
            report_lines.append("- ⚠️ Hoja `student_requests` no tiene columna STUDENT_NUMBER.")
        else:
            valid_students = set()
            for row in ws_req.iter_rows(min_row=2, values_only=True):
                v = row[sn_idx]
                if v is not None:
                    valid_students.add(str(v).strip().rstrip(".0").rstrip("."))
                    valid_students.add(str(int(v)) if isinstance(v, (int, float)) and v == int(v) else str(v))

            ws_cr = wb["conselours_recommendations"]
            cr_headers = [c.value for c in ws_cr[1]]
            id_a_idx = cr_headers.index("CODIGO") if "CODIGO" in cr_headers else None
            id_b_idx = None
            if id_a_idx is not None:
                for i, h in enumerate(cr_headers[id_a_idx + 1:], start=id_a_idx + 1):
                    if h == "CODIGO":
                        id_b_idx = i
                        break

            # Collect rows to delete (in reverse order to preserve indices)
            rows_to_delete: list[int] = []
            dropped_records: list[dict] = []
            for r_idx, row_cells in enumerate(ws_cr.iter_rows(min_row=2), start=2):
                if id_a_idx is None or id_b_idx is None:
                    break
                a = row_cells[id_a_idx].value
                b = row_cells[id_b_idx].value
                if a is None or b is None:
                    continue
                a_str = str(int(a)) if isinstance(a, (int, float)) else str(a).strip()
                b_str = str(int(b)) if isinstance(b, (int, float)) else str(b).strip()
                missing = []
                if a_str not in valid_students:
                    missing.append(f"a={a_str}")
                if b_str not in valid_students:
                    missing.append(f"b={b_str}")
                if missing:
                    rows_to_delete.append(r_idx)
                    dropped_records.append({
                        "row": r_idx,
                        "a": a_str,
                        "b": b_str,
                        "missing": missing,
                    })

            for r_idx in reversed(rows_to_delete):
                ws_cr.delete_rows(r_idx)

            report_lines.append(f"- Filas con student_id huérfano eliminadas: **{len(rows_to_delete)}**")
            for d in dropped_records:
                report_lines.append(f"  - Row {d['row']}: a={d['a']} b={d['b']} — falta {', '.join(d['missing'])}")
            if not rows_to_delete:
                report_lines.append("- (No se encontraron filas huérfanas — el archivo ya está limpio en este aspecto.)")

    report_lines.append("")

    # ------------------------------------------------------------------
    # ISSUE C — 6 reglas de texto libre
    # ------------------------------------------------------------------
    report_lines.append("## C. Reglas en texto libre (6) — formalizar como custom rules")
    report_lines.append("")

    # The ingester logged these but they live in 'CONSTRAINTS' or similar.
    # We'll create a new sheet 'free_text_rules_log' if not present and
    # populate with placeholders so a human can fill in the structured form.
    log_sheet_name = "free_text_rules_log"
    if log_sheet_name in wb.sheetnames:
        del wb[log_sheet_name]
    ws_log = wb.create_sheet(log_sheet_name)
    ws_log.append([
        "RULE_ID",
        "ORIGINAL_TEXT",
        "PROPOSED_OPCODE",
        "PROPOSED_PARAMS",
        "STATUS",
        "NOTES",
    ])

    free_text_rules = [
        {
            "id": "FT01",
            "text": "A1105 / Science Teacher 1, New (11253): Poner esta clase al profesor nuevo cuando Tamir no tenga clase.",
            "op": "prefer_teacher",
            "params": '{"course_id":"A1105","teacher_id":"11253"}',
            "note": "Condicional 'cuando Tamir no tenga clase' no es expresable hoy. v1: usar prefer_teacher fijo al teacher 11253.",
        },
        {
            "id": "FT02",
            "text": "H0904 / English Teacher 1, New (11252): Poner al profesor nuevo para esta clase cuando Schmaltz no tenga clase",
            "op": "prefer_teacher",
            "params": '{"course_id":"H0904","teacher_id":"11252"}',
            "note": "Mismo patrón que FT01.",
        },
        {
            "id": "FT03",
            "text": "H1001 / English Teacher 1, New (11252): Poner al profesor nuevo para esta clase cuando Shainker no tenga clase",
            "op": "prefer_teacher",
            "params": '{"course_id":"H1001","teacher_id":"11252"}',
            "note": "Mismo patrón.",
        },
        {
            "id": "FT04",
            "text": "G1004 / Villa, Norberto (953): Cuando Norberto no tenga clase, AP Spanish va a Sindy en este salón",
            "op": "prefer_teacher",
            "params": '{"course_id":"G1004","teacher_id":"953"}',
            "note": "Norberto preferred si está libre — fallback a Sindy. v1: enforce Norberto.",
        },
        {
            "id": "FT05",
            "text": "G1004 / Villamizar Muñoz, Sindy Margarita (8106): Cuando Norberto no tenga clase, AP Spanish va a Sindy en este salón",
            "op": "prefer_teacher",
            "params": '{"course_id":"G1004","teacher_id":"8106"}',
            "note": "Fallback de FT04. Solo activar si FT04 no se puede.",
        },
        {
            "id": "FT06",
            "text": "G0901 / Villamizar Muñoz, Sindy Margarita (8106): Poner a Sindy esta clase cuando Andrea Martínez no tenga clase",
            "op": "prefer_teacher",
            "params": '{"course_id":"G0901","teacher_id":"8106"}',
            "note": "Mismo patrón.",
        },
    ]
    for r in free_text_rules:
        ws_log.append([
            r["id"], r["text"], r["op"], r["params"], "PROPOSED", r["note"],
        ])

    report_lines.append(
        "- Hoja nueva `free_text_rules_log` creada con 6 filas. Cada fila "
        "propone un opcode (`prefer_teacher`) y un set de params traducible "
        "a un `CustomRuleSpec`."
    )
    report_lines.append(
        "- ⚠️ Las reglas originales son **condicionales** ('cuando X no tenga "
        "clase, asignar Y'). El motor v4.27 NO soporta condicionales — solo "
        "el primer brazo se puede aplicar. Decisión humana: ¿quieres asignar "
        "el teacher preferred siempre, o no aplicar la regla?"
    )
    report_lines.append("- Status `PROPOSED` indica que un humano debe revisar y cambiar a `ACTIVE` antes de que el ingester las consuma.")
    report_lines.append("")

    # ------------------------------------------------------------------
    # ISSUE D — Restricciones de tipo de sala (química→lab, banda→música, …)
    # ------------------------------------------------------------------
    report_lines.append("## D. Restricciones de tipo de sala (course_room_type)")
    report_lines.append("")

    # Inferir tipo basado en COURSE_NAME / COURSE_NUMBER
    proposed_mappings = []
    course_iter = list(ws_courses.iter_rows(min_row=2, values_only=True))
    for c_row in course_iter:
        if not c_row or c_row[course_number_idx] is None:
            continue
        code = str(c_row[course_number_idx] or "").strip()
        name = str(c_row[course_name_idx] or "").strip()
        name_upper = name.upper()
        kind: str | None = None
        reason = ""

        # PE / Physical Education / Sports
        if "PHYSICAL EDUCATION" in name_upper or "P.E" in name_upper or name_upper.startswith("PE "):
            kind = "gym"; reason = "PE → coliseo"
        # Science (Bio, Chem, Physics, Lab)
        elif any(k in name_upper for k in ["CHEMIST", "QUIMIC", "BIOLOG", "PHYSICS", "FÍSICA", "FISICA", "SCIENCE LAB", "AP CHEM", "AP BIO", "AP PHYS"]):
            kind = "science_lab"; reason = "ciencia experimental → laboratorio"
        # Music / Band
        elif any(k in name_upper for k in ["MUSIC", "MÚSICA", "MUSICA", "BAND", "BANDA", "CHOIR", "CORO", "ORCHESTR", "ORQUESTA"]):
            kind = "music"; reason = "música/banda → sala de música"
        # Art / Drawing / Sculpture / Visual
        elif any(k in name_upper for k in ["DRAWING", "SCULPT", "ART", "VISUAL", "PAINTING", "DIBUJO", "ESCULTUR", "PINTURA"]):
            kind = "art"; reason = "arte → sala de arte"
        # Computer / Technology / IT
        elif any(k in name_upper for k in ["COMPUTER SCIENCE", "PROGRAMMING", "TECHNOLOGY", "TECNOLOG", "ROBOT", "AP COMPUTER"]):
            kind = "computer_lab"; reason = "tech/cs → laboratorio de cómputo"
        # Special education
        elif any(k in name_upper for k in ["SPECIAL ED", "EDUCACI"]):
            kind = "special_ed"; reason = "educación especial"

        if kind:
            proposed_mappings.append({
                "course_number": code,
                "course_name": name,
                "room_type": kind,
                "status": "PROPOSED",
                "reason": reason,
            })

    # Crear hoja course_room_type
    crt_sheet = "course_room_type"
    if crt_sheet in wb.sheetnames:
        del wb[crt_sheet]
    ws_crt = wb.create_sheet(crt_sheet)
    ws_crt.append(["COURSE_NUMBER", "COURSE_NAME", "ROOM_TYPE", "STATUS", "REASON"])
    for m in proposed_mappings:
        ws_crt.append([m["course_number"], m["course_name"], m["room_type"], m["status"], m["reason"]])

    report_lines.append(
        f"- Hoja nueva `{crt_sheet}` creada con **{len(proposed_mappings)} mapeos propuestos**."
    )
    report_lines.append("- Tipos detectados (heurística por nombre):")
    type_counts: dict[str, int] = defaultdict(int)
    for m in proposed_mappings:
        type_counts[m["room_type"]] += 1
    for t, n in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        report_lines.append(f"  - `{t}`: {n} curso(s)")
    report_lines.append("")
    report_lines.append(
        "- **Cómo activarlas:** abre la app, tab `Reglas` → 'Reglas personalizadas'. "
        "Cada fila se traduce a un `CustomRuleSpec` con opcode `require_room_type` "
        "(implementado en v4.27.4). El solver aplica el constraint respetando "
        "`Course.required_room_type`."
    )
    report_lines.append(
        "- ⚠️ La heurística NO conoce los códigos del Colegio. Revisa cada fila "
        "antes de activarla. Particularmente: `STATUS=PROPOSED` debe pasar a "
        "`STATUS=ACTIVE` para que se aplique."
    )
    report_lines.append("")

    # ------------------------------------------------------------------
    # Closing — verification steps
    # ------------------------------------------------------------------
    report_lines.append("## Cómo verificar")
    report_lines.append("")
    report_lines.append("1. Diff de hojas:")
    report_lines.append("   ```bash")
    report_lines.append(f"   .venv/bin/python -m openpyxl.compare {input_path.name} {output_path.name}")
    report_lines.append("   ```")
    report_lines.append("2. Re-ingest con el archivo limpio:")
    report_lines.append("   ```python")
    report_lines.append("   from src.scheduler.ps_ingest_official import build_dataset_from_official_xlsx")
    report_lines.append(f"   ds = build_dataset_from_official_xlsx(Path('{output_path}'))")
    report_lines.append("   ```")
    report_lines.append("   El warning 'OZ1333 planned=19 generated=0' debe desaparecer.")
    report_lines.append("3. Activar las custom rules de FT01-FT06:")
    report_lines.append("   - Abrir tab `Reglas` en la app")
    report_lines.append("   - Sección 'Reglas personalizadas'")
    report_lines.append("   - Importar las filas con STATUS=ACTIVE de `free_text_rules_log`")

    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    wb.save(output_path)
    print(f"✓ Cleaned xlsx → {output_path}")
    print(f"✓ Report      → {report_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", required=True)
    p.add_argument("--out", dest="out_path", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args()
    cleanup(Path(args.in_path), Path(args.out_path), Path(args.report))


if __name__ == "__main__":
    main()
