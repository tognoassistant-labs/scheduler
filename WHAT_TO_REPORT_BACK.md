# Lo que el siguiente agente debe entregarte cuando vuelvas

> Esta es **tu lista** Hector. El agente que recibe `handoff_2026-04-26_continuation/` debe poner sus salidas en la carpeta `agent_returns_here/`. Cuando vuelvas a prender el computador, revisa esa carpeta y pídele explícitamente cualquier item de la lista que falte.

---

## Mínimo absoluto que debes recibir

Independiente de lo que el agente haya decidido hacer, exige estos 4 archivos en `agent_returns_here/`:

### 1. `agent_returns_here/SESSION_LOG.md`
Bitácora cronológica con timeline + net result en un párrafo. Si no hizo nada, lo dice ("no work performed; waited for X / Y").

### 2. `agent_returns_here/CHANGES_TO_CODE.md`
Lista de archivos modificados con resumen de 1 línea por cambio + resultado de `pytest tests/ --ignore=tests/test_hypothesis.py` (cuántos pasan/fallan). Si tocó solver: confirmación de que corrió `verify_bundle.py` y dio PASS.

### 3. `agent_returns_here/COLUMBUS_AGENT_REPORT.md`
Si el agente de Columbus respondió, copia o resumen. Si NO, decirlo: "no response from Columbus agent during this session." También aquí cualquier follow-up de Hector con respuestas del cliente sobre Decisiones 1-10.

### 4. `agent_returns_here/QUESTIONS_FOR_HECTOR.md`
Preguntas pendientes para ti. Decisiones grandes (cambios de scope, switch de stack, regenerar bundle) NO las toma el agente solo — se quedan acá con tradeoffs y recomendación.

---

## Items adicionales si el agente avanzó significativamente

### Si Hector resolvió Decisiones 1-10 (las del previous_session_outputs)

- Estado actualizado por decisión (RESUELTA / PARCIAL / OPEN).
- Para cada RESUELTA: qué opción se aplicó, qué archivos se tocaron, qué tests pasaron.
- Si quedó PARCIAL: por qué (a menudo es un edge case que la opción inicial no cubre — ver Decisión 2 como ejemplo, donde subir budget de 25s a 60s no resolvió porque el problema era estructural).

### Si recibió respuesta del agente de Columbus al verifier

- ¿`verifier_exit_code` == 0 (PASS)?
- ¿`failed_checks[]` por escuela?
- ¿Las preguntas A1-A9 quedaron respondidas? (las B1-B6 fueron contestadas en este session — ya están)
- ¿Credenciales de sandbox PowerSchool? Si sí, ¿se hizo dry-run?
- Si el reporte indica fallas, análisis de causa raíz.

### Si el cliente confirmó Decisión 10 (Q/TermID granularity)

- ¿`TermID=3600` es year, semester, o quarter?
- Si es quarter: lista de TermIDs por categoría (`Course.term: YEAR | SEMESTER | QUARTER`).
- ¿Bundle v3 regenerado? Si sí, hash + ubicación + qué cambió vs v2.
- ¿Notificación a Columbus sobre v2 → v3?

### Si el agente avanzó el doc de skills

- `docs/scheduler_skills_log.md` debe tener entradas nuevas en el "Updates log".
- Si descubrió nuevos perfiles de agente, deben estar en la tabla "Specialized profiles inferred during execution".

### Si el agente intentó pero no pudo algo

- En `QUESTIONS_FOR_HECTOR.md`, el bloqueo concreto:
  - Qué intentaba hacer
  - Qué obstáculo encontró (especialmente: si fue tema de Python/ortools, lo dice — ver footguns en START_HERE)
  - Qué necesita de ti para destrabarse

---

## Hash del bundle al momento de la entrega (verificar integridad)

Al inicio de tu próxima sesión, corre:
```bash
shasum -a 256 /Users/hector/Projects/handoff_2026-04-26_continuation/bundle_for_columbus/columbus_2026-2027_bundle_v2.zip
```

Si el hash no coincide con el documentado, el bundle fue modificado. El agente debe haberlo registrado en SESSION_LOG.md.

**Hash al momento de entrega 2026-04-26 PM:**
```
5a2932b8a9b7f0371b488c012296073549b000976d93ade08b4c65432ab46a89  columbus_2026-2027_bundle_v2.zip
```

Mismo hash que el handoff de la mañana — el bundle no se ha tocado desde entonces.

También guardado en `bundle_for_columbus/SHA256SUM.txt`.

---

## Si nada cambió

Si el siguiente agente no hizo cambios sustantivos (solo esperó al cliente, por ejemplo):

- `agent_returns_here/SESSION_LOG.md` con la entrada honesta "no work performed; waited for X / Y"
- Confirmación de que el bundle está intacto (mismo SHA-256 que arriba)
- Hash de los archivos de código clave (`master_solver.py`, `student_solver.py`, `exporter.py`, `models.py`, `ps_ingest.py`) para confirmar que no hubo edits no documentados.
