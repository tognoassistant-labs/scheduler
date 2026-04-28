# MVP priorizado - Motor de horarios

## Propósito
Definir un alcance mínimo viable para retomar la iniciativa del motor de horarios con una primera fase controlada, útil y validable por la operación.

## Criterio de priorización
El MVP se prioriza con base en tres principios:
- resolver el mayor dolor operativo actual
- reducir complejidad inicial de implementación
- permitir validación temprana con usuarios reales

## Objetivo del MVP
Contar con una primera versión funcional que permita construir y validar escenarios básicos de horario para un contexto académico acotado, sin intentar cubrir desde el inicio todos los casos institucionales posibles.

## Alcance recomendado del MVP
Se recomienda que el MVP cubra inicialmente:
- una escuela o unidad académica piloto
- uno o pocos grados piloto
- un único periodo o año escolar de referencia
- una versión controlada del proceso de generación y validación

## Capacidades mínimas del MVP

### MVP-01. Carga de insumos base
Permitir el registro o carga de los insumos mínimos necesarios para construir el horario del piloto.

### MVP-02. Configuración básica por contexto
Permitir parametrizar al menos:
- escuela
- grado
- año escolar

### MVP-03. Construcción de un horario maestro inicial
Permitir generar una primera versión del horario maestro con base en reglas y estructuras previamente definidas.

### MVP-04. Validación básica de conflictos
Permitir identificar conflictos evidentes o incumplimientos básicos en el escenario generado.

### MVP-05. Revisión operativa del resultado
Permitir que responsables del proceso revisen el horario propuesto antes de considerarlo válido.

### MVP-06. Generación de salida estructurada
Permitir exportar o visualizar el resultado en una forma clara y utilizable para revisión y operación.

## Capacidades deseables pero no obligatorias en el MVP
Estas capacidades agregan valor, pero podrían quedar para una fase posterior si afectan tiempo o claridad del piloto:
- manejo amplio de múltiples escenarios simultáneos
- asignación completa de estudiantes con todas las excepciones institucionales
- reglas avanzadas de optimización
- integración con otros sistemas
- trazabilidad detallada de versiones y auditoría completa

## Fuera de alcance inicial sugerido
Para evitar sobrediseño en la primera fase, se recomienda dejar por fuera inicialmente:
- cobertura total de todas las escuelas y grados
- automatización completa de todos los casos especiales
- integraciones complejas desde la primera iteración
- reglas altamente especializadas no necesarias para validar el piloto
- analítica avanzada o tableros ejecutivos completos

## Secuencia recomendada de implementación
1. consolidar inputs mínimos del piloto
2. definir reglas base del contexto seleccionado
3. generar horario maestro inicial
4. validar conflictos principales
5. revisar con usuarios responsables
6. ajustar y decidir expansión

## Criterios de éxito del MVP
El MVP se consideraría exitoso si logra:
- reducir dependencia del armado manual en el piloto
- producir un horario entendible y utilizable
- evidenciar conflictos de forma temprana
- permitir validación con usuarios operativos
- demostrar que el modelo parametrizable sí puede escalar a escenarios futuros

## Riesgos principales
- querer cubrir demasiados casos desde el inicio
- no definir con precisión los insumos mínimos
- intentar automatizar excepciones antes de estabilizar el flujo base
- falta de validación temprana con usuarios operativos

## Recomendación de siguiente paso
Si la iniciativa se reabre formalmente, el primer paso recomendado es seleccionar el piloto exacto y aterrizar los insumos mínimos, actores responsables y reglas base que gobernarán ese MVP.
