# Glosario

## Estructura del horario

**Slot:** unidad horaria. Notación `<día><bloque>` con día ∈ {A,B,C,D,E} y bloque ∈ {1,2,3,4,5}. Ejemplo: `A2` = lunes, bloque 2.

**Scheme / Period:** grupo de 3 slots que define cuándo se reúne una sección académica. Si dos secciones tienen los mismos 3 slots, comparten Period. No hay scheme→slot mapping autoritativo en este dataset — debes inferir Period numerando conjuntos únicos de slots.

**Bloque E3:** slot especial reservado para Advisory (homeroom). No asignar otras secciones allí.

## Términos del dominio

**Section / Sección:** instancia concreta de un curso. Un curso (e.g. `H0904` English 9) puede tener varias secciones (`H0904.1`, `H0904.2`, ...) con distinto profesor y aula, pero generalmente con slots diferentes.

**Singleton:** curso con UNA sola sección. Sus 3 slots son rígidos.

**Master:** la primera fase del solver — decide qué secciones existen, en qué slots, con qué profesor. **En este experimento el Master está congelado** (`sections.csv` no se toca).

**Phase 2 / Student assigner:** la segunda fase — asigna cada estudiante a secciones específicas dado el Master fijo. **Esto es lo que tú estás haciendo.**

## Términos académicos

**AP (Advanced Placement):** programa del College Board. Cursos AP son para estudiantes que buscan crédito universitario. NO sustituibles por curso regular del mismo dominio.

**Required course:** curso obligatorio para todos los estudiantes del grado correspondiente. Marcado `is_required=True` en `courses.csv`.

**Elective:** curso opcional. Mayoría tienen flexibilidad alta (sustituibles).

**Advisory / Homeroom:** período de seguimiento académico. En HS hay 23+ secciones de `ADVHS01` (una por homeroom). Cada estudiante va a la que le toque por grupo.

**TA (Teacher Assistant):** estudiante (típicamente G12) que ayuda a un profesor específico en una clase específica como parte de su carga académica. Aparecen en `teacher_assistants.csv`.

**G9 / G10 / G11 / G12:** grados 9-12 (high school). G12 = último año.

## Términos de constraints

**Term pair:** dos cursos que ocupan el mismo slot pero en semestres distintos del año (e.g. AP Macro en S1, AP Micro en S2). Caso único en HS: I1212/I1213.

**Simultaneous pair:** dos cursos que comparten slot intencionalmente — co-teaching, team-teaching, o electivas alineadas. Un estudiante toma UNO de ellos, no ambos.

**Separate (student pair):** dos estudiantes que NO pueden compartir sección. Razones: conflictos, recomendación de coordinación.

**Together (student pair):** dos estudiantes que DEBEN compartir sección si toman el mismo curso. Razones: gemelos, mismo soporte académico.

**Teacher avoid:** un estudiante NO puede tener un profesor específico. Razones: conflictos previos, relación familiar.

## Convenciones del dataset

**external_id:** identificador del estudiante en PowerSchool (e.g. `27028`). Es el que usa el colegio.

**teacher_id:** identificador interno del profesor en la BD (integer). En el CSV de output, va junto a TeacherName.

**room_id:** identificador del aula (string, e.g. `15`). Es la id del DB.

**enrollment_state:** estado del request. En este dataset todos están en `REQUESTED` o `APPROVED` — trátalos igual ("el alumno quiere ese curso").

**published:** flag de schedules en producción. NO aplica a este experimento porque estás CONSTRUYENDO los schedules; el output no necesita esta columna.

## Pesos

**Priority A-F:** prioridad del estudiante (A=máxima). Pesos: A=10000, B=1000, C=100, D=10, F=1.

**Flexibility A-F:** flexibilidad del curso (A=más flexible, F=más rígido). Pesos INVERTIDOS: A=1, B=2, C=5, D=50, F=500.

**Placement weight:** `PRIORITY × FLEXIBILITY`. Rango: 1 (alumno F + curso A flexible) ↔ 5,000,000 (alumno A + curso F rígido).
