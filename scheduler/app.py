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


# ============================================================================
# Optional password gate for hosted deployments.
#
# Activated only when env var APP_PASSWORD is set (typical for Render /
# Streamlit Cloud). Local dev runs are unaffected.
# ============================================================================

import os as _os
import hmac as _hmac

_REQUIRED_PASSWORD = _os.environ.get("APP_PASSWORD", "").strip()


def _gate() -> None:
    if not _REQUIRED_PASSWORD:
        return  # local dev — no gate
    if st.session_state.get("_auth_ok"):
        return
    st.markdown("# 🔒 Columbus Scheduling Engine")
    st.caption("Acceso restringido. Ingresa el password compartido por el administrador.")
    pwd = st.text_input("Password", type="password", key="_auth_pwd")
    if st.button("Ingresar", type="primary"):
        if _hmac.compare_digest(pwd, _REQUIRED_PASSWORD):
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("Password incorrecto.")
    st.stop()


_gate()

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
    # v4.27.20 — origen de los datos cargados (REQ-2)
    "loaded_files": [],      # list of dicts: {role, name, path, size, sha256, ingested_at}
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================================
# Helpers
# ============================================================================


def _friendly_ingest_error(exc: Exception) -> tuple[str, str]:
    """Translate a raw exception from the ingester into (title, body_markdown)
    with a suggested solution.

    Falls back to a generic message if the exception doesn't match a known
    pattern. Patterns are ordered most-specific first.
    """
    msg = str(exc)
    cls = type(exc).__name__

    # Pattern 1: v5 archivo subido al ingester legacy.
    # openpyxl raises ValueError("Worksheet <name> does not exist.")
    if "Worksheet" in msg and "does not exist" in msg:
        # Extract the missing sheet name if possible
        import re
        m = re.search(r"Worksheet\s+'?([^']+?)'?\s+does not exist", msg)
        missing_sheet = m.group(1) if m else "(desconocido)"
        return (
            "❌ Formato de archivo incorrecto",
            f"""**Qué pasó:** el archivo subido NO contiene la hoja `{missing_sheet}`
que el ingester legacy necesita.

**Causa probable:** subiste el archivo nuevo (formato consolidado v5,
ej: `schedule_master_data_hs.xlsx`) en el slot que espera el archivo
legacy (ej: `1._STUDENTS_PER_COURSE_2026-2027.xlsx`).

**Cómo arreglarlo:**

1. Verifica que tu archivo SÍ tenga la hoja `UPDATED MARCH 20 -
   COURSE_GRADE`. Ábrelo en Excel y mira las pestañas abajo.
2. Si NO la tiene → estás usando el archivo nuevo (v5). Tienes 2 opciones:
   - **Opción A:** consigue el archivo legacy del Colegio
     (`1._STUDENTS_PER_COURSE_*.xlsx`)
   - **Opción B:** convierte tu xlsx v5 a CSVs vía CLI y usa la opción
     "Carpeta canónica de CSVs" en su lugar (ver INSTALACION.md)
3. Si la hoja **sí** existe pero el error sigue, el archivo puede estar
   dañado. Re-exporta desde PowerSchool y vuelve a intentar.""",
        )

    # Pattern 2: master infeasible — frecuente con coplanning hard
    if "infeasible" in msg.lower() or "INFEASIBLE" in msg:
        return (
            "❌ El motor no encontró un horario factible",
            """**Qué pasó:** el solver no pudo construir un horario que cumpla todas
las reglas duras simultáneamente.

**Causas probables (orden de frecuencia):**

1. **Coplanning hard activado** con datos muy ajustados (~70% de los
   casos). El default es ON; en datos del Colegio a veces lo hace
   imposible.
2. **Cap de balance K demasiado estricto** (`max_section_spread_per_course`).
3. **Demasiadas separations** acumuladas hacen imposible distribuir
   estudiantes.
4. **Falta capacidad** en algún curso saturado.

**Cómo arreglarlo (en orden):**

1. Tab **Reglas** → Reglas duras → desactiva
   **"Co-planning de departamentos"** → Aplicar → Solve.
2. Si sigue infeasible: sube **"Spread máx entre secciones"** de 4 a 6.
3. Si sigue: revisa la tab **Cumplimiento** del último intento
   parcial para ver qué reglas dieron problema.""",
        )

    # Pattern 3: ortools / solver crashes — usually OOM or thread issue
    if "MemoryError" in cls or "out of memory" in msg.lower():
        return (
            "❌ Memoria insuficiente",
            """**Qué pasó:** el solver se quedó sin memoria.

**Causa probable:** dataset grande (multi-grado) con poca RAM disponible.

**Cómo arreglarlo:**

1. Cierra otras apps que consuman memoria (Chrome con muchas pestañas, etc.)
2. En la tab Solve, **baja los presupuestos de tiempo:**
   - Master: 15s
   - Student: 60s
3. Prueba con **un solo grado** primero. Si funciona, el dataset
   multi-grado excede tu RAM.""",
        )

    # Pattern 4: archivo no encontrado / path inválido (CSV folder)
    if "FileNotFoundError" in cls or "No such file" in msg or "not found" in msg.lower():
        return (
            "❌ Archivo o carpeta no encontrada",
            f"""**Qué pasó:** la ruta especificada no existe.

**Detalle del error:** `{msg}`

**Cómo arreglarlo:**

1. Verifica que la ruta sea correcta y absoluta.
2. Si usaste "Carpeta canónica de CSVs", la carpeta debe contener
   los 8 archivos: `courses.csv`, `teachers.csv`, `rooms.csv`,
   `sections.csv`, `students.csv`, `course_requests.csv`,
   `behavior.csv`, `rotation.csv`.""",
        )

    # Pattern 5: openpyxl errors specific to xlsx parsing
    if "openpyxl" in msg or "InvalidFileException" in cls or "BadZipFile" in cls:
        return (
            "❌ Archivo xlsx dañado o no válido",
            f"""**Qué pasó:** openpyxl no pudo abrir el archivo.

**Detalle:** `{msg}`

**Cómo arreglarlo:**

1. Abre el archivo en Excel. Si Excel lo abre bien, ciérralo y
   re-súbelo a la app.
2. Si Excel también falla → el archivo está dañado. Pídele al
   Colegio una nueva exportación.
3. Verifica que el archivo no esté abierto en Excel mientras lo
   subes (Excel a veces lo bloquea).""",
        )

    # Fallback: error inesperado
    return (
        "❌ Error inesperado durante la ingesta",
        f"""**Tipo de error:** `{cls}`

**Mensaje:** `{msg}`

**Qué hacer:**

1. Toma screenshot de este mensaje.
2. Anota qué archivo subiste y qué grados tenías seleccionados.
3. Reporta al equipo técnico (IT) con los datos de arriba.

Mientras tanto, puedes intentar:
- Probar con la opción **"Sample integrado"** para confirmar que la
  app funciona sin tu archivo
- Probar con un solo grado en lugar de Todo HS
- Re-iniciar la app (`Ctrl+C` en Terminal y `./start_local.sh`)""",
    )


def _show_friendly_error(exc: Exception) -> None:
    """Render a friendly error message in Streamlit. Replaces st.error()."""
    title, body_md = _friendly_ingest_error(exc)
    st.error(title)
    st.markdown(body_md)


# ============================================================================
# Validador pre-ingest (REQ-3 parte B)
# ============================================================================

# Hojas requeridas y opcionales por formato
LEGACY_REQUIRED_SHEETS = [
    "UPDATED MARCH 20 - COURSE_GRADE",
    "LISTADO MAESTRO CURSOS Y SECCIO",
]
LEGACY_OPTIONAL_SHEETS = [
    "Math Final March 20", "English Final March 20", "Science Final March 20",
    "Social Studies Final March 20", "Spanish Final March 20",
    "Tech Final March 20", "PE Final March 20", "Arts Final March 20",
    "TA Final March 20", "CO PLANNING INFO", "Teacher courses",
]
V5_REQUIRED_SHEETS = [
    "courses", "rooms", "teachers", "teacher_assignments",
    "student_requests", "required_courses",
]


def _validate_xlsx_sheets(xlsx_path: Path) -> dict:
    """Inspecciona un xlsx y reporta qué formato es + qué hojas faltan.

    Returns:
        {
          "format": "legacy" | "v5" | "unknown",
          "sheets": [...],
          "required_present": [...],
          "required_missing": [...],
          "optional_present": [...],
          "optional_missing": [...],
          "verdict": "ok" | "incomplete" | "wrong_format",
          "summary": str (markdown)
        }
    """
    from openpyxl import load_workbook
    try:
        wb = load_workbook(xlsx_path, read_only=True)
        sheets = wb.sheetnames
        wb.close()
    except Exception as e:
        return {"format": "unknown", "sheets": [], "verdict": "error",
                "summary": f"❌ No se pudo abrir el archivo: {e}"}

    # Detectar formato
    legacy_score = sum(1 for s in LEGACY_REQUIRED_SHEETS if s in sheets)
    v5_score = sum(1 for s in V5_REQUIRED_SHEETS if s in sheets)

    if legacy_score == len(LEGACY_REQUIRED_SHEETS):
        fmt = "legacy"
    elif v5_score == len(V5_REQUIRED_SHEETS):
        fmt = "v5"
    elif v5_score >= 5:
        fmt = "v5"  # mostly v5
    elif legacy_score >= 1:
        fmt = "legacy"  # partial legacy
    else:
        fmt = "unknown"

    if fmt == "legacy":
        required = LEGACY_REQUIRED_SHEETS
        optional = LEGACY_OPTIONAL_SHEETS
    elif fmt == "v5":
        required = V5_REQUIRED_SHEETS
        optional = []
    else:
        required = []
        optional = []

    req_present = [s for s in required if s in sheets]
    req_missing = [s for s in required if s not in sheets]
    opt_present = [s for s in optional if s in sheets]
    opt_missing = [s for s in optional if s not in sheets]

    # Verdict
    if fmt == "unknown":
        verdict = "wrong_format"
    elif req_missing:
        verdict = "incomplete"
    else:
        verdict = "ok"

    # Summary markdown
    parts = []
    parts.append(f"**Formato detectado:** `{fmt}`")
    parts.append(f"**Hojas en el archivo:** {len(sheets)}")
    if fmt == "v5":
        parts.append(
            "⚠️ Este es el formato **consolidado v5** — el uploader actual "
            "espera el formato **legacy**. Necesitas usar la opción "
            '"Carpeta canónica de CSVs" después de convertirlo via CLI.'
        )
    if req_present:
        parts.append(f"**✅ Hojas requeridas presentes ({len(req_present)}/{len(required)}):**")
        for s in req_present:
            parts.append(f"  - `{s}`")
    if req_missing:
        parts.append(f"**❌ Hojas requeridas faltantes ({len(req_missing)}):**")
        for s in req_missing:
            parts.append(f"  - `{s}`")
    if opt_missing and fmt == "legacy":
        parts.append(f"**⚠️ Hojas opcionales faltantes ({len(opt_missing)}):**")
        for s in opt_missing[:5]:
            parts.append(f"  - `{s}`")
        if len(opt_missing) > 5:
            parts.append(f"  - ... y {len(opt_missing) - 5} más")

    return {
        "format": fmt,
        "sheets": sheets,
        "required_present": req_present,
        "required_missing": req_missing,
        "optional_present": opt_present,
        "optional_missing": opt_missing,
        "verdict": verdict,
        "summary": "\n".join(parts),
    }


def _kpi_cards(kpi) -> None:
    """Render the v2 §10 KPI cards as a 6-up grid + actionable suggestions
    when a target is missed (REQ-C2)."""
    cols = st.columns(6)
    # value, target_text, target_met (bool), suffix, suggestion_md if not met
    targets = {
        "Fully scheduled": (
            kpi.fully_scheduled_pct, "≥98%", kpi.fully_scheduled_pct >= 98.0, "%",
            "Hay estudiantes a los que les falta algún curso requerido. "
            "Revisa la tab Cumplimiento → R_max_class_size: probablemente "
            "una sección saturada. Considera agregar más secciones a los "
            "cursos saturados."
        ),
        "Required fulfillment": (
            kpi.required_fulfillment_pct, "≥98%", kpi.required_fulfillment_pct >= 98.0, "%",
            "Algunos cursos requeridos no se pudieron asignar. "
            "Causa típica: capacidad insuficiente. Revisa `unmet_requests.csv` "
            "en Exportar para ver qué cursos faltan y a quiénes."
        ),
        "First-choice electives": (
            kpi.first_choice_elective_pct, "≥80%", kpi.first_choice_elective_pct >= 80.0, "%",
            "**Acción recomendada (probada):**\n\n"
            "1. Tab **Reglas** → 'Peso electivas rank-1' → sube a **50**\n"
            "2. Tab **Solve** → 'Presupuesto tiempo student' → sube a **600s**\n"
            "3. Re-corre Solve\n\n"
            "Mejora esperada: +5-7 pp en electivas rank-1."
        ),
        "Section balance": (
            kpi.section_balance_max_dev, "≤3", kpi.section_balance_max_dev <= 3, " students",
            "Hay demasiada diferencia entre tamaños de secciones del mismo curso. "
            "Tab **Reglas** → 'Peso balance entre secciones' → sube a 15. "
            "O baja 'Peso electivas rank-1' a 10 (sacrifica electivas para mejorar balance)."
        ),
        "Unscheduled": (
            kpi.unscheduled_students, "0", kpi.unscheduled_students == 0, "",
            "Estudiantes sin algún curso obligatorio. Revisa la lista en tab "
            "Cumplimiento → R_max_class_size. Probablemente hay un curso que "
            "necesita más secciones o capacidad."
        ),
        "Time conflicts": (0, "0", True, "", ""),
    }
    for col, (label, (value, target, met, suffix, suggestion)) in zip(cols, targets.items()):
        with col:
            color = "#28a745" if met else "#dc3545"
            indicator = "✅" if met else "❌"
            display_value = f"{value:.1f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"
            st.markdown(
                f"""
                <div style="border:2px solid {color};border-radius:8px;padding:12px;text-align:center;min-height:120px;">
                    <div style="color:#888;font-size:0.85em;">{label}</div>
                    <div style="font-size:1.6em;font-weight:bold;color:{color};">{display_value}</div>
                    <div style="font-size:0.85em;">target {target} {indicator}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Sugerencias accionables si hay KPIs por debajo de meta (REQ-C2)
    failed = [(label, suggestion) for label, (_, _, met, _, suggestion) in targets.items()
              if not met and suggestion]
    if failed:
        st.markdown("")  # spacing
        with st.expander(f"💡 {len(failed)} KPI(s) por debajo de meta — ver sugerencias", expanded=True):
            for label, suggestion in failed:
                st.markdown(f"### ❌ {label}")
                st.markdown(suggestion)
                st.markdown("---")


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


def _set_dataset(ds: Dataset, source: str, loaded_files: list[dict] | None = None) -> None:
    st.session_state["dataset"] = ds
    st.session_state["dataset_source"] = source
    st.session_state["loaded_files"] = loaded_files or []
    # New dataset → invalidate any persisted bundle pointer & solve outputs
    st.session_state["bundle_id"] = None
    st.session_state["rule_overrides"] = {}
    for k in ("master", "students", "unmet", "kpi", "master_status", "student_status"):
        st.session_state[k] = DEFAULTS[k]


def _file_metadata(path: Path, role: str) -> dict:
    """Compute path/size/sha256 metadata for a file. Used in 'Archivos cargados'."""
    import hashlib
    from datetime import datetime, timezone
    p = Path(path).resolve()
    if not p.exists():
        return {"role": role, "name": p.name, "path": str(p), "size": 0,
                "sha256": "(no encontrado)", "ingested_at": ""}
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "role": role,
        "name": p.name,
        "path": str(p),
        "size": p.stat().st_size,
        "sha256": h,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


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
    st.caption("Motor de horarios alineado a v2 §10")

    st.divider()
    st.subheader("Fuente de datos")

    src = st.radio(
        "Elige una fuente",
        ["Sample integrado (Grado 12, 130 estudiantes)", "Carpeta canónica de CSVs", "xlsx real de Columbus"],
        label_visibility="collapsed",
    )

    if src == "Sample integrado (Grado 12, 130 estudiantes)":
        seed = st.number_input("Semilla aleatoria", value=42, step=1, min_value=0)
        n_students = st.number_input("Número de estudiantes", value=130, step=10, min_value=10, max_value=1000)
        if st.button("🔄 Generar sample", width='stretch'):
            with st.spinner("Generando..."):
                ds = make_grade_12_dataset(n_students=int(n_students), seed=int(seed))
                _set_dataset(ds, f"sample · seed={seed} · n={n_students}", loaded_files=[
                    {"role": "sample sintético", "name": f"make_grade_12_dataset(seed={seed}, n={n_students})",
                     "path": "(generado en memoria — no es archivo real)", "size": 0,
                     "sha256": f"seed-{seed}-n-{n_students}", "ingested_at": ""}
                ])
            st.success(f"Cargado: {len(ds.students)} estudiantes, {len(ds.sections)} secciones")
            st.rerun()

    elif src == "Carpeta canónica de CSVs":
        with st.expander("ℹ️ ¿Qué archivos espera la carpeta?"):
            st.markdown("""
La carpeta debe contener exactamente **8 archivos CSV**:

| Archivo | Contenido |
|---|---|
| `courses.csv` | Catálogo de cursos: id, nombre, departamento, max_size, etc. |
| `teachers.csv` | Profesores: id, nombre, calificaciones, max_load |
| `rooms.csv` | Salas: id, nombre, capacidad, tipo (gym/lab/etc.) |
| `sections.csv` | Secciones: course_id, teacher_id, max_size |
| `students.csv` | Estudiantes: id, nombre, grado, counselor |
| `course_requests.csv` | Solicitudes: student_id, course_id, rank |
| `behavior.csv` | Pares: separations + groupings disciplinarios |
| `rotation.csv` | Bell schedule (5 días × 5 bloques → schemes) |

**Cómo obtenerlos:**
- **Opción 1** — generar con CLI: `python -m src.scheduler.cli generate-sample --out data/sample`
- **Opción 2** — convertir desde xlsx: `python -m src.scheduler.cli import-ps --demand <xlsx> --out data/columbus`
- **Opción 3** — ya viene `data/sample` con los 8 CSVs sintéticos para probar

Para inspeccionar la estructura: abre cualquier CSV en Excel.
""")
        path = st.text_input("Ruta a la carpeta de CSVs", value="data/sample")
        if st.button("📂 Cargar CSVs", width='stretch'):
            try:
                ds = read_dataset(Path(path))
                # Capturar metadata de los 8 archivos canónicos
                csv_files = [
                    "courses.csv", "teachers.csv", "rooms.csv", "sections.csv",
                    "students.csv", "course_requests.csv", "behavior.csv", "rotation.csv",
                ]
                meta = []
                for fname in csv_files:
                    p = Path(path) / fname
                    if p.exists():
                        meta.append(_file_metadata(p, role=fname.replace(".csv", "")))
                _set_dataset(ds, f"csv · {path}", loaded_files=meta)
                st.success(f"Cargado desde {path}: {len(ds.students)} estudiantes, {len(ds.sections)} secciones")
                st.rerun()
            except Exception as e:
                _show_friendly_error(e)

    elif src == "xlsx real de Columbus":
        st.caption("Sube los workbooks operativos de Columbus")

        # Plantillas descargables (REQ-4)
        tpl_legacy = Path("data/templates/plantilla_legacy.xlsx")
        if tpl_legacy.exists():
            with open(tpl_legacy, "rb") as f:
                st.download_button(
                    "📥 Descargar plantilla (formato legacy)",
                    data=f.read(),
                    file_name="plantilla_legacy.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="xlsx vacío con las hojas y columnas que el motor espera. Útil como referencia.",
                    width='stretch',
                )

        # Tooltip con schema esperado (REQ-3 parte A)
        with st.expander("ℹ️ ¿Qué archivos espera y qué deben contener?"):
            st.markdown("""
**Workbook de demanda** (obligatorio):
- Nombre típico: `1._STUDENTS_PER_COURSE_2026-2027.xlsx`
- Hojas requeridas:
  - `UPDATED MARCH 20 - COURSE_GRADE` — solicitudes por estudiante
  - `LISTADO MAESTRO CURSOS Y SECCIO` — secciones, teachers, salas
  - `Math Final March 20`, `English Final March 20`, `Science Final March 20`,
    `Social Studies Final March 20`, `Spanish Final March 20`,
    `Tech Final March 20`, `PE Final March 20`, `Arts Final March 20`,
    `TA Final March 20` — finales por departamento
  - `CO PLANNING INFO` — grupos de profesores que comparten free time
  - `Teacher courses` — calificaciones por teacher

**Workbook de schedule** (opcional):
- Nombre típico: `HS_Schedule_25-26.xlsx`
- Aporta: groupings y separations heredados del año pasado
- Si NO lo subes, el motor funciona pero sin esa info disciplinaria

⚠️ **Importante:** este uploader espera el formato **legacy**. Si tu
archivo es el nuevo `schedule_master_data_hs.xlsx` (formato consolidado
v5 con 11 hojas), te dará error porque las hojas tienen otros nombres.
En ese caso, conviértelo primero a CSVs vía CLI y usa la opción
"Carpeta canónica de CSVs".

📥 **¿No tienes archivo y quieres probar?** Cambia a la opción "Sample
integrado" arriba — genera datos sintéticos para experimentar.
""")
        demand_file = st.file_uploader("Workbook de demanda (1._STUDENTS_PER_COURSE_*.xlsx)", type=["xlsx"], key="demand_xlsx")
        sched_file = st.file_uploader("Workbook de schedule (HS_Schedule_*.xlsx, opcional)", type=["xlsx"], key="sched_xlsx")

        st.markdown("**Grados a incluir** ❓",
                    help="Marca los checkboxes de los grados que quieres ingerir. "
                         "Los presets de abajo son atajos comunes.")

        # Initialize state for individual grade checkboxes
        for g in (9, 10, 11, 12):
            key = f"grade_chk_{g}"
            if key not in st.session_state:
                # Default: solo G12 marcado (compatibilidad con v4.27.14)
                st.session_state[key] = (g == 12)

        # Presets de un click — modifican los checkboxes via session_state
        preset_cols = st.columns(4)
        if preset_cols[0].button("Todo HS\n(9-12)", help="Marca G9, G10, G11, G12"):
            for g in (9, 10, 11, 12):
                st.session_state[f"grade_chk_{g}"] = True
            st.rerun()
        if preset_cols[1].button("Último año\n(solo 12)", help="Marca solo G12"):
            for g in (9, 10, 11, 12):
                st.session_state[f"grade_chk_{g}"] = (g == 12)
            st.rerun()
        if preset_cols[2].button("Últimos 2\n(11, 12)", help="Marca G11 + G12"):
            for g in (9, 10, 11, 12):
                st.session_state[f"grade_chk_{g}"] = (g in (11, 12))
            st.rerun()
        if preset_cols[3].button("Primer ciclo\n(9, 10)", help="Marca G9 + G10"):
            for g in (9, 10, 11, 12):
                st.session_state[f"grade_chk_{g}"] = (g in (9, 10))
            st.rerun()

        # Checkboxes individuales (siempre visibles — descubribilidad)
        chk_cols = st.columns(4)
        chk_cols[0].checkbox("G9", key="grade_chk_9")
        chk_cols[1].checkbox("G10", key="grade_chk_10")
        chk_cols[2].checkbox("G11", key="grade_chk_11")
        chk_cols[3].checkbox("G12", key="grade_chk_12")

        # Resolver lista final de grados
        selected_grades = [g for g in (9, 10, 11, 12) if st.session_state.get(f"grade_chk_{g}")]
        if not selected_grades:
            st.warning("⚠️ Selecciona al menos un grado.")
            grade_arg: int | list[int] = 12
            grade_label = "(ninguno)"
        elif len(selected_grades) == 1:
            grade_arg = selected_grades[0]
            grade_label = f"G{selected_grades[0]}"
        else:
            grade_arg = selected_grades
            grade_label = "+".join(f"G{g}" for g in selected_grades)
        # Caption explicativa
        if len(selected_grades) >= 3:
            st.caption(
                f"📚 Ingestará {len(selected_grades)} grados ({', '.join(f'G{g}' for g in selected_grades)}). "
                "Más estudiantes → solver tarda más. Recomendado: subir 'Presupuesto tiempo student' a 600s en tab Solve."
            )
        elif selected_grades:
            st.caption(f"Ingestará: {', '.join(f'G{g}' for g in selected_grades)}")
        year = st.text_input("Año", value="2026-2027")

        # Persistir a disco inmediatamente al subir, para que el coordinador
        # vea el path antes de hacer click en Ingestar.
        tmp_uploads = Path("/tmp/scheduler_uploads")
        tmp_uploads.mkdir(exist_ok=True)
        if demand_file is not None:
            demand_disk = tmp_uploads / demand_file.name
            if not demand_disk.exists() or demand_disk.stat().st_size != len(demand_file.getbuffer()):
                demand_disk.write_bytes(demand_file.getbuffer())
            st.success(f"📁 Demanda en disco: `{demand_disk}` ({demand_disk.stat().st_size:,} bytes)")
        if sched_file is not None:
            sched_disk = tmp_uploads / sched_file.name
            if not sched_disk.exists() or sched_disk.stat().st_size != len(sched_file.getbuffer()):
                sched_disk.write_bytes(sched_file.getbuffer())
            st.success(f"📁 Schedule en disco: `{sched_disk}` ({sched_disk.stat().st_size:,} bytes)")

        # Validador pre-ingest (REQ-3 parte B) — solo del archivo demanda
        ingest_disabled = demand_file is None
        if demand_file is not None:
            validation = _validate_xlsx_sheets(demand_disk)
            if validation["verdict"] == "ok":
                st.success("✅ Validación: el archivo tiene todas las hojas requeridas. Listo para ingestar.")
                with st.expander("Ver detalle de validación"):
                    st.markdown(validation["summary"])
            elif validation["verdict"] == "incomplete":
                st.warning("⚠️ El archivo NO tiene todas las hojas requeridas. La ingesta probablemente falle.")
                st.markdown(validation["summary"])
                ingest_disabled = True
            elif validation["verdict"] == "wrong_format":
                st.error("❌ Formato no reconocido. Este uploader espera el archivo **legacy**.")
                st.markdown(validation["summary"])
                ingest_disabled = True
            else:
                st.error(validation["summary"])
                ingest_disabled = True

        if st.button("📥 Ingestar", width='stretch', disabled=ingest_disabled):
            with st.spinner("Leyendo archivos xlsx..."):
                tmp = tmp_uploads
                demand_path = tmp / demand_file.name
                sched_path = (tmp / sched_file.name) if sched_file is not None else None
                try:
                    ds = build_dataset_from_columbus(demand_path, sched_path, grade=grade_arg, year=year)
                    meta = [_file_metadata(demand_path, role="Workbook de demanda")]
                    if sched_path is not None:
                        meta.append(_file_metadata(sched_path, role="Workbook de schedule"))
                    _set_dataset(ds, f"columbus · {demand_file.name} · grade={grade_label}", loaded_files=meta)
                    st.success(f"Ingestado: {len(ds.students)} estudiantes, {len(ds.sections)} secciones, "
                               f"{len(ds.behavior.separations)} separaciones, {len(ds.behavior.groupings)} groupings")
                    st.rerun()
                except Exception as e:
                    _show_friendly_error(e)

    st.divider()
    if _has_dataset():
        st.markdown(f"**Cargado:** `{st.session_state['dataset_source']}`")
        ds = st.session_state["dataset"]
        st.caption(f"{len(ds.students)} estudiantes · {len(ds.sections)} secciones · "
                   f"{len(ds.teachers)} teachers · {len(ds.rooms)} salas")
    else:
        st.info("Elige una fuente de datos arriba")

    st.divider()
    st.subheader("Persistencia")
    persist = st.checkbox(
        "Guardar corridas en SQLite",
        value=st.session_state.get("persist_enabled", False),
        help="Guarda bundles, configs de reglas y resultados de cada solve para que "
             "cualquier corrida pasada se pueda consultar y re-exportar. "
             "Ruta de la BD: $COLUMBUS_DB o data/columbus.sqlite.",
    )
    st.session_state["persist_enabled"] = persist
    if persist:
        db = _get_db()
        if db is not None:
            st.caption(f"BD: `{db.path}`")


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
    tab_help,
) = st.tabs([
    "1️⃣ Inputs",
    "📋 Reglas",
    "2️⃣ Solve",
    "✅ Cumplimiento",
    "3️⃣ Explorar",
    "🔒 Locks y Prefs",
    "📜 Corridas",
    "4️⃣ Escenarios",
    "5️⃣ Exportar",
    "❓ Ayuda",
])

# ----------------------------------------------------------------------------
# TAB 1: SETUP — dataset overview + readiness
# ----------------------------------------------------------------------------

with tab_setup:
    if not _has_dataset():
        st.info("Elige una fuente de datos en el sidebar para empezar.")
    else:
        ds = st.session_state["dataset"]
        rep = validate_dataset(ds)

        # Panel permanente de archivos cargados (REQ-2)
        loaded = st.session_state.get("loaded_files") or []
        if loaded:
            with st.expander(f"📂 Origen de los datos ({len(loaded)} archivo(s))", expanded=True):
                rows = []
                for f in loaded:
                    size_kb = f["size"] / 1024 if f["size"] else 0
                    rows.append({
                        "Rol": f["role"],
                        "Archivo": f["name"],
                        "Ruta completa": f["path"],
                        "Tamaño": f"{size_kb:.1f} KB" if size_kb > 0 else "—",
                        "SHA256 (primeros 12)": f["sha256"][:12] if f["sha256"] else "—",
                    })
                st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
                if loaded[0].get("ingested_at"):
                    st.caption(f"⏰ Ingestado: {loaded[0]['ingested_at']}")
                st.caption(
                    "Esta tabla muestra qué archivos físicos están detrás del "
                    "dataset activo. Útil para auditar (¿qué versión usé en "
                    "esta corrida?) y para reportar problemas a IT."
                )

        col_left, col_right = st.columns([1, 2])
        with col_left:
            _readiness_card(rep.score, len(rep.errors), len(rep.warnings))
        with col_right:
            st.subheader("Vista del dataset")
            stats_cols = st.columns(4)
            stats_cols[0].metric("Estudiantes", len(ds.students))
            stats_cols[1].metric("Secciones", len(ds.sections))
            stats_cols[2].metric("Teachers", len(ds.teachers))
            stats_cols[3].metric("Salas", len(ds.rooms))

        if rep.errors:
            st.error(f"⚠️ {len(rep.errors)} error(es) bloqueante(s) — corrige antes de solve")
            for issue in rep.errors:
                st.write(f"  - **{issue.code}** · `{issue.entity_id or '-'}` · {issue.message}")
        if rep.warnings:
            with st.expander(f"{len(rep.warnings)} advertencia(s)"):
                for issue in rep.warnings:
                    st.write(f"- **{issue.code}** · `{issue.entity_id or '-'}` · {issue.message}")

        # v4.27 — persiste el dataset activo en SQLite para que sobreviva al reinicio.
        if st.session_state.get("persist_enabled"):
            db = _get_db()
            st.divider()
            cols_persist = st.columns([2, 1])
            with cols_persist[0]:
                bundle_label = st.text_input(
                    "Etiqueta del bundle",
                    value=st.session_state["dataset_source"][:60] or "ad-hoc",
                    key="bundle_label_input",
                )
            with cols_persist[1]:
                st.write("")
                st.write("")
                if st.button("💾 Guardar bundle a BD", width='stretch'):
                    repo = InputBundleRepo(db)
                    src = st.session_state["dataset_source"]
                    kind = (
                        "xlsx" if src.startswith("columbus")
                        else "sample" if src.startswith("sample")
                        else "csv"
                    )
                    bid = repo.save(bundle_label, kind, ds)
                    st.session_state["bundle_id"] = bid
                    st.success(f"Guardado como bundle #{bid}")
            if st.session_state.get("bundle_id"):
                st.caption(f"Bundle activo: #{st.session_state['bundle_id']}")

        st.divider()
        st.subheader("Desglose de cursos")
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
                "ID Curso": c.course_id,
                "Nombre": c.name,
                "Departamento": c.department,
                "Requerido": "✓" if c.is_required else "",
                "Lab": "✓" if c.is_lab else "",
                "Secciones": n_sect,
                "Capacidad": cap,
                "Demanda rank-1": demand,
                "Holgura": cap - demand,
            })
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)


# ----------------------------------------------------------------------------
# TAB 1.5: RULES — registry-driven toggles + sliders
# ----------------------------------------------------------------------------

with tab_rules:
    if not _has_dataset():
        st.info("Carga un dataset primero.")
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

        # ============================================================
        # Reglas personalizadas — Fase 2 funcional (v4.27.7)
        # ============================================================
        st.divider()
        st.subheader("➕ Reglas personalizadas")
        st.caption(
            "Reglas que extienden el comportamiento por defecto. Se aplican al "
            "próximo solve y se persisten con el rule_config si activas DB."
        )

        from src.scheduler.rules.custom import (
            CustomRuleSpec,
            supported_opcodes,
            serialize_custom_rules,
            deserialize_custom_rules,
        )

        # session_state list of CustomRuleSpec (as dicts for easier JSON-ability)
        if "custom_rules" not in st.session_state:
            st.session_state["custom_rules"] = []

        # ----- Formulario para agregar nueva regla -----
        with st.expander("Agregar nueva regla", expanded=False):
            cr_cols = st.columns([2, 2, 1])
            with cr_cols[0]:
                cr_id = st.text_input("ID único", key="cr_new_id", placeholder="ej. user_pe_no_block5")
                cr_label = st.text_input("Etiqueta", key="cr_new_label", placeholder="ej. PE no en bloque 5")
            with cr_cols[1]:
                cr_op = st.selectbox("Opcode", supported_opcodes(), key="cr_new_op")
                cr_kind = st.selectbox("Tipo", ["hard", "soft"], key="cr_new_kind")
            with cr_cols[2]:
                st.write("")
                st.write("")
                cr_enabled = st.checkbox("Activa", value=True, key="cr_new_enabled")

            # Params dinámicos según opcode
            params: dict = {}
            help_text = {
                "forbid_pair": "Estudiantes A y B nunca en la misma sección",
                "forbid_slot": "Teacher T no puede dictar en cierto bloque (1-5)",
                "require_room": "Curso C solo en sala R",
                "require_room_type": "Curso C solo en salas tipo {gym, science_lab, music, art, computer_lab, special_ed}",
                "prefer_teacher": "Estudiante S debe quedar con teacher T en curso C",
                "cohort_together": "Lista de estudiantes (separados por coma) deben compartir secciones",
            }
            st.caption(help_text.get(cr_op, ""))

            if cr_op == "forbid_pair":
                p_cols = st.columns(2)
                params["student_a"] = p_cols[0].text_input("Student A", key="cr_p_sa")
                params["student_b"] = p_cols[1].text_input("Student B", key="cr_p_sb")
            elif cr_op == "forbid_slot":
                p_cols = st.columns(2)
                params["teacher_id"] = p_cols[0].text_input("Teacher ID", key="cr_p_tid")
                params["block"] = p_cols[1].number_input("Block (1-5)", min_value=1, max_value=5, value=1, key="cr_p_blk")
            elif cr_op == "require_room":
                p_cols = st.columns(2)
                params["course_id"] = p_cols[0].text_input("Course ID", key="cr_p_cid")
                params["room_id"] = p_cols[1].text_input("Room ID", key="cr_p_rid")
            elif cr_op == "require_room_type":
                p_cols = st.columns(2)
                params["course_id"] = p_cols[0].text_input("Course ID", key="cr_p_crt_cid")
                params["room_type"] = p_cols[1].selectbox(
                    "Room type",
                    ["standard", "science_lab", "computer_lab", "art", "music", "gym", "special_ed"],
                    key="cr_p_crt_rt",
                )
            elif cr_op == "prefer_teacher":
                p_cols = st.columns(3)
                params["student_id"] = p_cols[0].text_input("Student ID", key="cr_p_sid")
                params["course_id"] = p_cols[1].text_input("Course ID", key="cr_p_pt_cid")
                params["teacher_id"] = p_cols[2].text_input("Teacher ID", key="cr_p_pt_tid")
            elif cr_op == "cohort_together":
                params["student_ids_csv"] = st.text_area(
                    "Student IDs (separados por coma)",
                    key="cr_p_cohort",
                    placeholder="27001, 27002, 27003",
                )

            if st.button("➕ Agregar regla"):
                if not cr_id or not cr_label:
                    st.error("ID y Etiqueta son requeridos.")
                elif any(r["id"] == cr_id for r in st.session_state["custom_rules"]):
                    st.error(f"Ya existe una regla con id `{cr_id}`.")
                else:
                    final_params = {k: v for k, v in params.items() if v != ""}
                    if cr_op == "cohort_together" and "student_ids_csv" in final_params:
                        ids = [s.strip() for s in final_params["student_ids_csv"].split(",") if s.strip()]
                        final_params = {"student_ids": ids}
                    new_rule = {
                        "id": cr_id,
                        "kind": cr_kind,
                        "label": cr_label,
                        "solver_op": cr_op,
                        "params": final_params,
                        "enabled": cr_enabled,
                    }
                    st.session_state["custom_rules"].append(new_rule)
                    st.success(f"Agregada `{cr_id}` ({cr_op}).")
                    st.rerun()

        # ----- Importadores: course_room_type / free_text_rules_log -----
        with st.expander("📥 Importar reglas desde xlsx (course_room_type / free_text_rules_log)"):
            xlsx_path = st.text_input(
                "Ruta a xlsx con hojas",
                value="data/cleanup/master_data_hs_CLEANED.xlsx",
                key="cr_import_path",
            )
            cols_imp = st.columns(2)
            with cols_imp[0]:
                if st.button("📥 Importar `course_room_type` (STATUS=ACTIVE)"):
                    try:
                        from openpyxl import load_workbook
                        wb = load_workbook(xlsx_path, data_only=True)
                        if "course_room_type" not in wb.sheetnames:
                            st.warning("Hoja `course_room_type` no encontrada.")
                        else:
                            ws = wb["course_room_type"]
                            n_imported = 0
                            for row in ws.iter_rows(min_row=2, values_only=True):
                                if not row or row[0] is None:
                                    continue
                                course = str(row[0]).strip()
                                room_type = str(row[2] or "").strip().lower()
                                status = str(row[3] or "").upper().strip()
                                if status != "ACTIVE":
                                    continue
                                rid = f"crt_{course}"
                                if any(r["id"] == rid for r in st.session_state["custom_rules"]):
                                    continue
                                st.session_state["custom_rules"].append({
                                    "id": rid,
                                    "kind": "hard",
                                    "label": f"Sala {room_type} para {course}",
                                    "solver_op": "require_room_type",
                                    "params": {"course_id": course, "room_type": room_type},
                                    "enabled": True,
                                })
                                n_imported += 1
                            st.success(f"Importadas {n_imported} reglas. (Las que están en STATUS≠ACTIVE se ignoran.)")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Falló: {e}")
            with cols_imp[1]:
                if st.button("📥 Importar `free_text_rules_log` (STATUS=ACTIVE)"):
                    try:
                        from openpyxl import load_workbook
                        import json as _json
                        wb = load_workbook(xlsx_path, data_only=True)
                        if "free_text_rules_log" not in wb.sheetnames:
                            st.warning("Hoja `free_text_rules_log` no encontrada.")
                        else:
                            ws = wb["free_text_rules_log"]
                            n_imported = 0
                            for row in ws.iter_rows(min_row=2, values_only=True):
                                if not row or row[0] is None:
                                    continue
                                rule_id = str(row[0]).strip()
                                op = str(row[2] or "").strip()
                                params_raw = str(row[3] or "").strip()
                                status = str(row[4] or "").upper().strip()
                                if status != "ACTIVE" or not op or not params_raw:
                                    continue
                                try:
                                    params_parsed = _json.loads(params_raw)
                                except Exception:
                                    continue
                                rid = f"ft_{rule_id}"
                                if any(r["id"] == rid for r in st.session_state["custom_rules"]):
                                    continue
                                st.session_state["custom_rules"].append({
                                    "id": rid,
                                    "kind": "hard",
                                    "label": f"Free-text {rule_id}",
                                    "solver_op": op,
                                    "params": params_parsed,
                                    "enabled": True,
                                })
                                n_imported += 1
                            st.success(f"Importadas {n_imported} reglas free-text.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Falló: {e}")

        # ----- Lista de custom rules activas -----
        rules_list = st.session_state["custom_rules"]
        if rules_list:
            st.markdown(f"**{len(rules_list)} regla(s) personalizada(s):**")
            for idx, r in enumerate(list(rules_list)):
                cols_r = st.columns([3, 2, 2, 1, 1])
                cols_r[0].markdown(f"**{r['label']}**\n\n_{r['id']}_")
                cols_r[1].caption(f"Op: `{r['solver_op']}` ({r['kind']})")
                cols_r[2].caption(f"Params: `{r['params']}`")
                with cols_r[3]:
                    new_enabled = st.checkbox("On", value=r["enabled"], key=f"cr_en_{idx}")
                    if new_enabled != r["enabled"]:
                        st.session_state["custom_rules"][idx]["enabled"] = new_enabled
                        st.rerun()
                with cols_r[4]:
                    if st.button("🗑", key=f"cr_del_{idx}"):
                        st.session_state["custom_rules"].pop(idx)
                        st.rerun()
            st.caption(
                "Las reglas se aplican automáticamente en el próximo solve. "
                "Solo las que están `On` se evalúan."
            )
        else:
            st.info("No hay reglas personalizadas todavía. Agrega una arriba o importa desde xlsx.")


# ----------------------------------------------------------------------------
# TAB 2: SOLVE
# ----------------------------------------------------------------------------

with tab_solve:
    if not _has_dataset():
        st.info("Carga un dataset primero.")
    else:
        ds = st.session_state["dataset"]

        st.subheader("Configuración del solver")
        cfg_cols = st.columns(3)
        with cfg_cols[0]:
            mode = st.selectbox("Modo", ["single", "lexmin"], index=0,
                                help="single: suma ponderada (rápido). lexmin: 2 fases (electivas → groupings) con cap balance hard.")
            master_time = st.number_input("Presupuesto tiempo master (s)", value=30, min_value=5, max_value=600, step=5)
            student_time = st.number_input("Presupuesto tiempo student (s)", value=180, min_value=10, max_value=1200, step=10)
        with cfg_cols[1]:
            spread_cap = st.slider("Cap balance hard K (max−min por curso)", 2, 10, ds.config.hard.max_section_spread_per_course,
                                   help="K=5 → max-dev ≤ 3 (meta v2 §10). K=8 = laxo; K=3 = estricto (puede hacer electivas infeasible).")
            elective_w = st.slider("Peso electiva rank-1", 1, 50, ds.config.soft.first_choice_electives)
            balance_w = st.slider("Peso balance soft", 0, 30, ds.config.soft.balance_class_sizes)
        with cfg_cols[2]:
            grouping_w = st.slider("Peso pares grouping", 0, 20, ds.config.soft.grouping_codes)
            coplan_w = st.slider("Peso co-planning (0=off)", 0, 10, ds.config.soft.co_planning,
                                 help="Co-planning agrupa secciones del mismo dept; >0 puede dañar electivas.")
            teacher_load_w = st.slider("Peso balance carga teacher", 0, 20, ds.config.soft.teacher_load_balance)

        # Show rule overrides badge if any are pending.
        if st.session_state.get("rule_overrides"):
            n = len(st.session_state["rule_overrides"])
            st.info(f"📋 {n} regla(s) modificada(s) en la tab Rules — aplicarán automáticamente al solve")

        # C4 — Estimar tiempo antes de Solve
        n_students = len(ds.students)
        n_sections = len(ds.sections)
        # Heurística empírica:
        # - Master: típicamente <5s pero puede llegar al budget si datos complejos
        # - Student: ~0.4s por estudiante con budget alto, hasta budget máximo
        est_master = min(int(master_time), max(2, n_sections // 50))
        est_student = min(int(student_time), max(10, int(n_students * 0.4)))
        est_total_min = (est_master + est_student) / 60
        # Tendencias para ajustar
        warnings = []
        if n_students > 1000 and student_time < 300:
            warnings.append(f"Dataset grande ({n_students} estudiantes) con student_time={int(student_time)}s "
                            f"corto. Recomendado: subir a 600s para mejorar electivas.")
        if mode == "lexmin":
            warnings.append("⚠️ Modo `lexmin` colapsa required (validado en simulación). Usa `single`.")
        if elective_w >= 50 and student_time >= 600:
            note = "✅ Configuración óptima detectada (peso electivas=50 + student_time≥600s)"
        else:
            note = ""
        # Render
        with st.container():
            est_cols = st.columns([2, 1])
            with est_cols[0]:
                st.markdown(
                    f"⏱️ **Tiempo estimado de cómputo:** ~{est_total_min:.1f} minutos "
                    f"({est_master}s master + ~{est_student}s student) "
                    f"para **{n_students} estudiantes**, **{n_sections} secciones**."
                )
                if note:
                    st.caption(note)
                for w in warnings:
                    st.caption(f"⚠️ {w}")
            with est_cols[1]:
                if est_total_min > 10:
                    st.warning(f"~{est_total_min:.0f} min — ten paciencia")
                elif est_total_min < 1:
                    st.success("⚡ <1 min — rápido")

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

            # Aplicar reglas personalizadas (Phase 2 DSL) si existen
            cr_list = st.session_state.get("custom_rules") or []
            if cr_list:
                from src.scheduler.rules.custom import (
                    CustomRuleSpec,
                    apply_custom_rules_to_dataset,
                )
                specs = [
                    CustomRuleSpec(
                        id=r["id"],
                        kind=r["kind"],
                        label=r["label"],
                        solver_op=r["solver_op"],
                        params=r["params"],
                        enabled=r["enabled"],
                    )
                    for r in cr_list
                ]
                ds_run = apply_custom_rules_to_dataset(ds_run, specs)
                st.info(f"Aplicadas {sum(1 for r in cr_list if r['enabled'])} regla(s) personalizada(s) al dataset.")

            db = _get_db() if st.session_state.get("persist_enabled") else None

            if db is not None:
                # Persistence path: runner handles bundle/rule_config/run lifecycle.
                with st.spinner("Resolviendo (con persistencia)..."):
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
                    st.error(f"Falló el solve master: {outcome.master_status}")
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
                        f"✓ Corrida #{outcome.run_id} · {outcome.master_status} / {outcome.student_status} · "
                        f"{len(outcome.result.students)} estudiantes · {len(outcome.result.unscheduled_requests)} sin cumplir"
                    )
            else:
                # Ruta legacy — sin persistencia
                with st.spinner(f"Etapa 1: horario master (presupuesto {master_time}s)..."):
                    t0 = time.time()
                    master, _, m_status = solve_master(ds_run, time_limit_s=master_time)
                    m_elapsed = time.time() - t0
                if not master:
                    st.error(f"Falló el solve master: {m_status}")
                else:
                    st.session_state["master"] = master
                    st.session_state["master_status"] = m_status
                    st.session_state["master_seconds"] = m_elapsed
                    st.success(f"✓ Etapa 1: {m_status} · {len(master)} secciones ubicadas · {m_elapsed:.1f}s")

                    with st.spinner(f"Etapa 2: asignación de estudiantes (modo={mode}, presupuesto {student_time}s)..."):
                        t0 = time.time()
                        students, unmet, _, s_status = solve_students(
                            ds_run, master, time_limit_s=student_time, mode=mode
                        )
                        s_elapsed = time.time() - t0
                    if not students:
                        st.error(f"Falló el solve student: {s_status}")
                    else:
                        st.session_state["students"] = students
                        st.session_state["unmet"] = unmet
                        st.session_state["student_status"] = s_status
                        st.session_state["student_seconds"] = s_elapsed
                        st.session_state["kpi"] = compute_kpis(ds_run, master, students, unmet)
                        st.session_state["dataset"] = ds_run
                        st.success(f"✓ Etapa 2: {s_status} · {len(students)} estudiantes asignados · "
                                   f"{len(unmet)} rank-1 sin cumplir · {s_elapsed:.1f}s")

        if _has_solution():
            st.divider()
            st.subheader("KPI vs metas v2 §10")
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
        st.info("Corre el solver primero (tab 2).")
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
            st.subheader("Grid del horario master (Día × Bloque)")
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
            course_filter = st.multiselect("Filtrar por curso", sorted(df["Course"].unique()))
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
            search = st.text_input("Buscar estudiantes (nombre o ID)", "")
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
                    st.subheader("Todas las solicitudes sin cumplir")
                    st.dataframe(df, width='stretch', hide_index=True, height=420)


# ----------------------------------------------------------------------------
# TAB 3.5: LOCKS & PREFERENCES (v2 §6.2 / §13)
# ----------------------------------------------------------------------------

with tab_locks:
    if not _has_dataset():
        st.info("Carga un dataset primero.")
    else:
        ds = st.session_state["dataset"]
        st.caption("Edita locks de secciones y preferencias de teachers. Los cambios persisten en el dataset cargado; corre Solve (tab 2) para aplicarlos.")

        sub_locks, sub_prefs = st.tabs(["Locks de secciones", "Preferencias de teachers"])

        with sub_locks:
            st.subheader("Locks de secciones (v2 §13)")
            st.caption("Fija una sección a un scheme específico (1..8 o ADVISORY) o sala. Vacío = sin restringir.")
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
                        help="Elige scheme 1..8, o vacío para sin lock",
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
                    st.success(f"Actualizados {changes} campo(s). Corre Solve en tab 2 para aplicar.")
                else:
                    st.info("No se detectaron cambios.")

        with sub_prefs:
            st.subheader("Preferencias de teachers (v2 §6.2)")
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
                    st.success(f"Actualizados {changes} campo(s). Corre Solve en tab 2 para aplicar.")
                else:
                    st.info("No se detectaron cambios.")


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

        all_runs = run_repo.list_all(limit=200)
        # Filtro por tag (F3)
        all_tags: set[str] = set()
        for r in all_runs:
            if r.tags:
                all_tags.update(t.strip() for t in r.tags.split(",") if t.strip())
        filter_tag = None
        if all_tags:
            filter_tag = st.selectbox(
                "Filtrar por etiqueta",
                options=["(todas)"] + sorted(all_tags),
                index=0,
            )
            if filter_tag == "(todas)":
                filter_tag = None
        runs = [r for r in all_runs if filter_tag is None or
                (r.tags and filter_tag in [t.strip() for t in r.tags.split(",")])]

        st.subheader(f"Histórico ({len(runs)} corrida(s){f' con etiqueta `{filter_tag}`' if filter_tag else ''})")

        if not runs:
            st.info("No hay corridas con esos filtros. Corre el solver con persistencia activa para ver corridas aquí.")
        else:
            run_rows = []
            for r in runs:
                run_rows.append({
                    "ID": r.id,
                    "Label": r.label,
                    "Created": r.created_at[:19].replace("T", " "),
                    "Status": r.status,
                    "Tags": r.tags or "",
                    "Notas": (r.notes[:40] + "…") if r.notes and len(r.notes) > 40 else (r.notes or ""),
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

                # F3 — Notas y tags por corrida
                with st.expander("📝 Notas y etiquetas", expanded=bool(meta.notes or meta.tags)):
                    nt_cols = st.columns([3, 2])
                    with nt_cols[0]:
                        new_notes = st.text_area(
                            "Notas",
                            value=meta.notes or "",
                            key=f"notes_run_{selected}",
                            placeholder="Ej: 'Esta es la corrida final aprobada por dirección académica.'",
                            height=100,
                        )
                    with nt_cols[1]:
                        new_tags = st.text_input(
                            "Etiquetas (separadas por coma)",
                            value=meta.tags or "",
                            key=f"tags_run_{selected}",
                            placeholder="ej: aprobado, final, 2026-2027",
                        )
                        # Botones rápidos para tags comunes
                        tag_cols = st.columns(3)
                        if tag_cols[0].button("➕ #draft", key=f"tag_draft_{selected}"):
                            existing = [t.strip() for t in (new_tags or "").split(",") if t.strip()]
                            if "draft" not in existing:
                                existing.append("draft")
                            run_repo.set_tags(selected, ",".join(existing))
                            st.rerun()
                        if tag_cols[1].button("✅ #aprobado", key=f"tag_apv_{selected}"):
                            existing = [t.strip() for t in (new_tags or "").split(",") if t.strip()]
                            if "aprobado" not in existing:
                                existing.append("aprobado")
                            run_repo.set_tags(selected, ",".join(existing))
                            st.rerun()
                        if tag_cols[2].button("🗑 #descartado", key=f"tag_disc_{selected}"):
                            existing = [t.strip() for t in (new_tags or "").split(",") if t.strip()]
                            if "descartado" not in existing:
                                existing.append("descartado")
                            run_repo.set_tags(selected, ",".join(existing))
                            st.rerun()
                    if st.button("💾 Guardar notas y etiquetas", key=f"save_meta_run_{selected}"):
                        run_repo.set_notes(selected, new_notes.strip() or None)
                        # Normalizar tags: quitar espacios, lowercase
                        clean_tags = ",".join(
                            t.strip().lower().replace(" ", "_")
                            for t in (new_tags or "").split(",") if t.strip()
                        )
                        run_repo.set_tags(selected, clean_tags or None)
                        st.success("Guardado.")
                        st.rerun()

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
        st.info("Carga un dataset primero.")
    else:
        ds = st.session_state["dataset"]

        preset = st.selectbox("Preset", list(PRESETS.keys()))
        col_l, col_r = st.columns(2)
        with col_l:
            sc_master_time = st.number_input("Tiempo master por escenario (s)", value=20, min_value=5, max_value=300, step=5, key="sc_master")
        with col_r:
            sc_student_time = st.number_input("Tiempo student por escenario (s)", value=60, min_value=10, max_value=600, step=10, key="sc_student")

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

        if st.button("▶️ Correr escenarios", type="primary", width='stretch'):
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
                # CSV compatible con el visor estático en
                # https://publicaciones.columbus.edu.co/web_resources/visor_schedules/
                "student_schedules_friendly.csv": tmp / "reports" / "student_schedules_friendly.csv",
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
        st.subheader("Mapeo de campos (referencia)")
        st.caption("Ajusta nombres de columnas por instancia PS del Colegio usando el PS Data Dictionary si es necesario.")
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


# ----------------------------------------------------------------------------
# TAB HELP — explicación de cada regla en español para no-técnicos
# ----------------------------------------------------------------------------

with tab_help:
    st.title("❓ Ayuda — guía de la aplicación")
    st.caption(
        "Esta sección explica qué hace cada parte del motor y qué significa cada regla. "
        "Pensada para coordinadores académicos y administradores que NO necesitan leer código."
    )

    st.divider()
    st.subheader("Flujo de trabajo recomendado")
    st.markdown("""
1. **Inputs** — Carga los datos del Colegio (xlsx) o un sample integrado para pruebas.
2. **Reglas** — Revisa qué reglas están activas y ajusta pesos según prioridades del Colegio.
3. **Solve** — Corre el motor. Tarda entre 1 y 10 minutos según el tamaño del dataset.
4. **Cumplimiento** — Mira el % de cumplimiento por regla. Las reglas duras siempre deben estar al 100%.
5. **Explorar** — Examina el horario generado: secciones, estudiantes, teachers.
6. **Corridas** — Compara dos o más corridas guardadas para ver el efecto de cambios en las reglas.
7. **Exportar** — Descarga los CSVs compatibles con PowerSchool.
""")

    st.divider()
    st.subheader("Reglas duras (hard) — el motor SIEMPRE las cumple")
    st.markdown("""
Si una regla dura no se puede cumplir, el motor reporta **infeasible** y no genera horario.
""")

    rule_explanations_hard = {
        "R_enforce_separations": (
            "Separaciones obligatorias",
            "Pares de estudiantes que NUNCA pueden estar en la misma sección. "
            "Útil para conflictos disciplinarios o de personalidad.",
        ),
        "R_enforce_restricted_teachers": (
            "Teachers restringidos por estudiante",
            "Cada estudiante tiene una lista de teachers que no pueden dictarle. "
            "El motor garantiza que ninguno de esos teachers aparezca en su horario.",
        ),
        "R_enforce_coplanning_groups": (
            "Co-planning de departamentos",
            "Grupos de teachers (definidos en la hoja co-planning) deben tener al menos un "
            "scheme libre en común para poder reunirse a planear. "
            "Costo: ~50 estudiantes pueden quedar sin su electiva preferida cuando esto está activo.",
        ),
        "R_max_class_size": (
            "Tamaño máximo de clase",
            "Ninguna sección puede tener más de N estudiantes inscritos (default 25, "
            "AP Research 26).",
        ),
        "R_ap_research_max_size": (
            "Tamaño máximo AP Research",
            "Excepción específica para AP Research que permite 26 en lugar de 25.",
        ),
        "R_max_consecutive_classes": (
            "Clases consecutivas máx por teacher",
            "Ningún teacher dicta más de N bloques seguidos en un día (default 4). "
            "Garantiza tiempo de descanso/preparación.",
        ),
        "R_max_section_spread_per_course": (
            "Spread máx entre secciones del mismo curso",
            "Si Álgebra II tiene 3 secciones, la diferencia entre la más llena y la más "
            "vacía no puede pasar de N estudiantes (default 4). Política Colegio: ideal 4, aceptable 5.",
        ),
        "R_min_sections_for_balance": (
            "Mínimo de secciones para evaluar balance",
            "Cursos con menos de N secciones no se someten al constraint de balance "
            "(no tiene sentido balancear 1 sola sección).",
        ),
    }

    for rule_id, (label, desc) in rule_explanations_hard.items():
        with st.expander(f"**{label}** (`{rule_id}`)"):
            st.markdown(desc)

    st.divider()
    st.subheader("Pesos suaves (soft) — el motor INTENTA optimizarlos")
    st.markdown("""
Los pesos definen prioridades cuando el motor no puede cumplir todo. Un peso de 0 desactiva
ese objetivo. Pesos altos hacen que el motor prefiera satisfacer ese criterio sobre otros.
""")

    rule_explanations_soft = {
        "R_w_first_choice_electives": (
            "Electivas rank-1",
            "Premia cumplir cada solicitud de electiva en primera opción. "
            "Subir el peso → más estudiantes obtienen su electiva preferida (puede sacrificar balance).",
        ),
        "R_w_balance_class_sizes": (
            "Balance entre secciones (suave)",
            "Penaliza desviación entre tamaños de secciones del mismo curso. "
            "Complementa el constraint duro (R_max_section_spread_per_course).",
        ),
        "R_w_co_planning": (
            "Co-planning suave",
            "Premia agrupar teachers del mismo departamento. Default 0 (off). "
            "Subirlo concentra secciones del mismo dept en pocos schemes y puede dañar electivas.",
        ),
        "R_w_grouping_codes": (
            "Grouping codes (pares que SÍ deben estar juntos)",
            "Premia mantener juntos pares de estudiantes en la lista de groupings. "
            "Es el opuesto de las separaciones — se aplica como suave por default.",
        ),
        "R_w_teacher_load_balance": (
            "Balance de carga teachers",
            "Penaliza desbalance en bloques por día entre teachers. "
            "Garantiza distribución pareja del trabajo.",
        ),
        "R_w_teacher_preferred_courses": (
            "Cursos preferidos por teacher",
            "Premia asignar al teacher cursos en su lista preferred_course_ids.",
        ),
        "R_w_teacher_avoid_courses": (
            "Cursos evitados por teacher",
            "Penaliza asignar al teacher cursos en su lista avoid_course_ids.",
        ),
        "R_w_teacher_preferred_blocks": (
            "Bloques preferidos por teacher",
            "Premia dictar en bloques que el teacher prefiere (ej: 'no quiero dictar primer bloque').",
        ),
        "R_w_teacher_avoid_blocks": (
            "Bloques evitados por teacher",
            "Penaliza dictar en bloques que el teacher evita.",
        ),
        "R_w_singleton_separation": (
            "Separación de cursos singleton",
            "Empuja cursos con una sola sección hacia schemes diferentes para reducir conflictos. "
            "Default 0 (off).",
        ),
        "R_w_separation_violation": (
            "Violación de separación (cuando hard=off)",
            "Penalización aplicada solo si la regla R_enforce_separations está apagada. "
            "Alto → cumple casi todas las separaciones; bajo → permite romperlas.",
        ),
    }

    for rule_id, (label, desc) in rule_explanations_soft.items():
        with st.expander(f"**{label}** (`{rule_id}`)"):
            st.markdown(desc)

    st.divider()
    st.subheader("KPIs principales y qué significan")
    st.markdown("""
| KPI | Meta v2 §10 | Significado |
|---|---|---|
| **Fully scheduled %** | ≥98% | Estudiantes que recibieron TODOS sus cursos requeridos |
| **Required fulfillment %** | ≥98% | Solicitudes obligatorias cumplidas (de todas las solicitudes obligatorias) |
| **First-choice electives %** | ≥80% | Electivas rank-1 cumplidas (de todas las solicitudes rank-1) |
| **Section balance (max dev)** | ≤3 | Mayor diferencia entre tamaños de secciones del mismo curso |
| **Unscheduled** | 0 | Estudiantes sin algún curso obligatorio |
| **Time conflicts** | 0 | Siempre 0 — el motor lo garantiza estructuralmente |
""")

    st.divider()
    st.subheader("Reglas personalizadas (Phase 2)")
    st.markdown("""
La app permite autorear reglas custom desde la tab **Reglas** sin tocar
código. Cada regla tiene un opcode que define qué hace.

| Opcode | Para qué sirve | Ejemplo |
|---|---|---|
| `forbid_pair` | Estudiantes A y B nunca en la misma sección | "Pedro y Juan separados" |
| `forbid_slot` | Teacher T no puede dictar en cierto bloque | "Sandro no en bloque 5" |
| `require_room` | Curso C solo en sala R específica | "AP Bio solo en Lab 901" |
| `require_room_type` | Curso C solo en salas tipo X | "PE va a gym, Banda a music" |
| `prefer_teacher` | Estudiante S debe quedar con teacher T en curso C | "Ariana asiste a Gloria en AP Drawing" |
| `cohort_together` | Lista L de estudiantes comparte secciones | "Equipo de robótica junto" |

**Cómo importar reglas desde xlsx:**
- La tab `Reglas` tiene importadores para las hojas `course_room_type`
  y `free_text_rules_log` del archivo limpio. Cambia `STATUS=PROPOSED`
  → `STATUS=ACTIVE` en Excel y luego un click importa todas.
- También puedes agregar reglas manualmente con el formulario.

**Tipo de sala (room_type) — valores válidos:**
- `gym` — coliseos, canchas (PE)
- `science_lab` — laboratorios de ciencia (química, biología, física)
- `computer_lab` — laboratorios de cómputo (Tech, AP CS)
- `music` — sala de música (banda, coro, orquesta)
- `art` — sala de arte (drawing, painting, sculpture)
- `special_ed` — educación especial
- `standard` — salón regular (default)
""")

    st.divider()
    st.subheader("Glosario rápido")
    st.markdown("""
- **Bundle** — un conjunto de inputs (cursos, teachers, salas, secciones, estudiantes, requests). Cada bundle se guarda con un ID único.
- **Rule config** — configuración de reglas (toggles + pesos). También se guarda con ID propio.
- **Run** — una corrida del solver = un bundle + un rule config + los resultados que produjo. Cada run tiene su propio ID y queda en el histórico.
- **Master** — etapa 1 del solver: decide qué scheme y qué sala usa cada sección.
- **Student** — etapa 2 del solver: asigna cada estudiante a una sección por curso solicitado.
- **Scheme** — número 1..8 que representa una "huella" de día/bloque. Por ejemplo, scheme 3 = lunes B1, miércoles C2, jueves D3.
- **Coplanning group** — grupo de teachers que necesitan un horario común libre para reuniones.
- **Separation** — par de estudiantes que NO pueden estar en la misma sección.
- **Grouping** — par de estudiantes que SÍ deben estar en la misma sección.
- **Singleton course** — curso con una sola sección.
- **PowerSchool export** — los 3 CSVs (sections, enrollments, master_schedule) listos para importar a PowerSchool.
""")

    st.divider()
    st.subheader("Soporte")
    st.markdown(
        "- **Errores en el solver:** revisa los warnings en la tab Inputs; "
        "datos sucios suelen ser la causa principal.\n"
        "- **Master infeasible:** el caso más común es coplanning hard activo + datos muy ajustados. "
        "Apaga `R_enforce_coplanning_groups` y vuelve a correr.\n"
        "- **Cobertura baja de electivas:** sube `R_w_first_choice_electives`, baja `R_w_balance_class_sizes`, "
        "o agrega más secciones al curso de alta demanda."
    )
