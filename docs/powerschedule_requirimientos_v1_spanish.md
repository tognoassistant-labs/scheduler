Motor de Horarios — Documento de Problema

Para entrega a agente / proveedor

───

1. Contexto institucional

Columbus es una institución escolar con programas de High School, Middle and Elementary, la construcción de horarios académicos es un proceso manual, complejo y difícil de sostener en el tiempo.

Este documento consolida el problema de negocio, los datos disponibles y los requerimientos funcionales para que un agente o proveedor pueda evaluar, estimar y planificar el desarrollo de una solución.

───

2. Problema de negocio

La construcción de horarios depende de trabajo manual intensivo. El proceso actual presenta:

• Alta dependencia de personas específicas — el conocimiento del horario vive en quienes lo construyen
• Dificultad para replicar — cada año escolar se empieza desde cero o casi cero
• Inflexibilidad ante cambios — ajustar el horario cuando hay cambios de staff o estudiantes es lento y propenso a errores
• Sin capacidad de simular escenarios — no hay forma fácil de preguntar "¿qué pasa si..."
• Escalabilidad limitada — cubrir HS, MS y ES bajo el mismo enfoque requiere rediseñar desde cero.


La necesidad expresada es contar con una solución parametrizable por escuela, grado y año escolar, que reduzca la dependencia del armado manual, aumente la consistencia del proceso y pueda operar distintos modelos académicos.

───

3. Alcance funcional esperado

La solución debe funcionar como un motor de horarios que:

1. Reciba información estructurada (estudiantes, profesores, cursos, salones, reglas)
2. Aplique reglas configurables (constraints duros y blandos)
3. Genere un horario maestro (asignación profesores ↔ bloques ↔ salones)
4. Asigne estudiantes a secciones respetando constraints
5. Permita validar escenarios antes de adoptarlos
6. Produzca salidas estructuradas compatibles con PowerSchool
7. Permita revisión y ajustes manuales por parte del equipo administrativo
8. Permita la adicion de nuevas reglas
9. Permita la improvisación ante nuevos escenarios, como ocurren en la vida de una escuela.

───

4. Escenarios académicos

4.1 High School (caso de referencia principal)

Estructura horaria:

• 5 días de clase: Día A, Día B, Día C, Día D, Día E
• 5 bloques de clase por día
• 8 esquemas rotativos (secuencias de bloques que rotan sobre los días)
• Cada estudiante debe inscribirse en 8 cursos
• Cada curso se ve 3 veces por semana
• Un curso puede tener múltiples secciones (grupos)
• Un curso puede ser impartido por hasta 3 profesores distintos
• 2 semestres/4 quarters - (S1, S2)/(Q1,Q2, Q3, Q4)
• Los profesores pueden tener preps (grupos que no son cursos — horas libres)

Advisory:

• Sesión fija para todos los estudiantes de HS
• Ubicación: Día E, Bloque 3 (inamovible)

Ejemplo de rotación (Esquemas):


| Bloque | Día A | Día B | Día C | Día D | Día E              |
| ------ | ----- | ----- | ----- | ----- | ------------------ |
| 1      | 1     | 6     | 3     | 8     | 5                  |
| 2      | 2     | 7     | 4     | 1     | 6                  |
| 3      | 3     | 8     | 5     | 2     | x-block (Advisory) |
| 4      | 4     | 1     | 6     | 3     | 7                  |
| 5      | 5     | 2     | 7     | 4     | 8                  |


4.2 Middle School (escenario secundario)

• Estructura más simple que HS
• Días A-E, 5 bloques por día
• 2 semestres/4 quarters - (S1, S2)/(Q1,Q2, Q3, Q4)
• Estudiantes con cursos fijos (sin electivos múltiples como HS)
• 6th grade y 7th/8th grade con estructuras distintas

───

5. Datos disponibles

5.1 Archivos de datos reales

High School — HS_Schedule_25-26.xlsx

• Sheet Schedule: estructura del horario maestro (bloques × días, profesores, salones, número de estudiantes)
• Sheet Students: ~520 estudiantes con sus 8 cursos asignados por esquema (columnas E1–E8 = secciones de electivos), conflictos, códigos de separación/agrupamiento
• Sheet Esquemas: 8 esquemas de cursos por estudiante
• Sheet Teachers: lista de profesores con # de preps y horas
• Sheet SALONES: asignación profesor-curso-sala
• Sheet Students per Teacher: distribución de estudiantes por profesor

Middle School — MS_schedule_2024_2025.xlsx

• Misma estructura general, adaptada a MS
Students per course 2026-2027 — 1_STUDENTS_PER_COURSE_2026_2027.xlsx

• Sheet UPDATED MARCH 20 - COURSE_GRADE: enrollment por curso y grado (9–12), número de secciones
• Sheet LISTADO MAESTRO CURSOS Y SECCIONES: curso, profesor asignado, sala, # secciones por profesor, total secciones por curso
• Sheet Teacher courses: qué cursos enseña cada profesor

5.2 Estructura de datos de estudiantes (HS Students sheet)

Cada fila de estudiante contiene:

• GR, ID, Name
• English, E (sección), Spanish, E, Math, E, Science, E — con secciones 1–8 para electivos
• PE, E, Sociales, E, FRC/Robotics, E, Art/Band/Tech, E, Elective, E
• E1–E8: códigos de sección de electivos
• Scheduled: total de cursos asignados (8 = completo)
• Conflicts: número de conflictos
• Separate Code: estudiantes que deben estar separados
• Together code: estudiantes que deben estar juntos

5.3 Lo que aún no está disponible

• Catálogo de cursos completo con prerrequisitos
• Cualificaciones formales profesor-curso (más allá del LISTADO MAESTRO)
• Horario de disponibilidad de profesores
• Matriz explícita de convivencia en formato estructurado

───

6. Constraints documentados

6.1 Hard constraints (nunca violar)

1. Ningún estudiante en dos clases al mismo tiempo
2. Ningún profesor en dos clases al mismo tiempo
3. Ningún salón usado por dos clases al mismo tiempo
4. Cupo máximo por sección: 25 estudiantes (AP Research: 26)
5. Ningún profesor con más de 4 clases consecutivas
6. Advisory exclusivamente en Día E, Bloque 3 — inamovible
7. Cursos de laboratorio deben ir en sala de laboratorio
8. Estudiantes no deben tener clase con profesor que se ha indicado evitar
9. Estudiantes con código de separación (Separate Code) no deben compartir ninguna clase

6.2 Soft constraints (optimizar)

1. Balance de secciones: distribución equitativa de estudiantes entre secciones del mismo curso
2. Cumplimiento de electivos: asignar electivos de primera elección
3. Coplanificación: garantizar tiempo libre simultáneo para pares/trios de profesores
4. Convivencia positiva: estudiantes con código de agrupamiento deberían compartir más clases
5. Distribución docente: carga equilibrada entre profesores
6. Evitar último bloque de rotación de forma consistente para profesores

───

7. Proceso en dos fases

Fase 1 — Generar horario maestro

• Asignar profesores y salas a bloques/días de cada esquema
• Meta: compartir con líderes escolares antes de asignar estudiantes

Fase 2 — Asignar estudiantes a secciones

• Colocar a cada estudiante en una sección de cada uno de sus 8 cursos
• Aplicar: balance, convivencia, preferencias

───

8. Herramienta visual existente

Existe una herramienta en JavaScript/HTML (app, index, styles.css) que permite explorar esquemas rotativos y visualizar la distribución. No resuelve la asignación optimizada de estudiantes ni la generación automática del horario maestro.

───

9. Integración con PowerSchool

Objetivo: generar horarios y enrollments que puedan importarse a PowerSchool.

Método inicial: CSV export/import
Método avanzado (futuro): API de PowerSchool

───

10. Criterios de éxito

copy

| Métrica                                       | Meta            |
| --------------------------------------------- | --------------- |
| Estudiantes completamente agendados           | ≥ 98%           |
| Conflicts restantes tras optimización         | < 5%            |

copy

| Cumplimiento de cursos requeridos             | ≥ 98%           |
| Cumplimiento de electivos de primera elección | ≥ 80%           |
| Balance de secciones (desviación máxima)      | ≤ 3 estudiantes |
| Reducción de tiempo vs. proceso manual        | ≥ 90%           |


───

11. Stack tecnológico recomendado

• 
Lenguaje: Java
• Motor de optimización: Google OR-Tools o una propuesta distinta que el agente haga
• Lectura de archivos: Apache POI (lectura de .xlsx)
• Backend: Spring Boot (opcional, según complejidad de UI)
• Base de datos: PostgreSQL (para persistencia de escenarios y configuraciones)
• Exportación: CSV para PowerSchool

───
12. Preguntas abiertas antes de iniciar

1. ¿Se tiene acceso a la API de PowerSchool o solo a exportación CSV? Ambas
2. ¿La herramienta visual existente debe integrarse o funcionar independientemente? independiente
3. ¿Cuál es el grado/año escolar prioritario para el piloto inicial? 12
4. ¿Existe la matriz de convivencia en formato estructurado? si
5. ¿Cuántos desarrolladores y con qué perfil? Claude Code
6. ¿Cuál es la fecha límite para el piloto funcional? 1 mayo

───

