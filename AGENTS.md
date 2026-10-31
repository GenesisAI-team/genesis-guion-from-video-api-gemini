# AGENTS.md — Reglas operativas

Repositorio: `GenesisAI-team/genesis-guion-from-video-api-gemini`
Issue principal (fuente de verdad): **GEN-13 — GENESIS Video AI — MVP**
Proyecto Linear: **Ultimate Coding** (`P-GEN-1`), equipo **Genesis** (`GEN`).

Antes de implementar cualquier issue: leer GEN-13, leer la issue concreta, leer este
archivo y consultar la documentación oficial de las librerías implicadas.

## Entorno

- Python **3.12**, gestionado por `uv` (`.python-version`, `requires-python = ">=3.12,<3.13"`).
- **Nunca** instalar dependencias en el Python global (`C:\Python313`) ni ejecutar `pip install` fuera de `uv`.
- Comandos siempre mediante `uv run` para garantizar el intérprete correcto.
- `google-genai`, `PySide6` y `pydantic` se incorporan en las fases que los necesitan,
  no antes. No añadir dependencias sin justificación en la issue.

## Metodología: TDD estricto

**RED → GREEN → REFACTOR** en cada comportamiento con lógica ejecutable:

1. **RED**: escribir el test y demostrar que falla por el motivo correcto.
2. **GREEN**: implementación mínima para pasarlo.
3. **REFACTOR**: mejorar el diseño sin romper la suite.

Prohibido implementar primero y añadir tests después. Prohibido tocar un test para
ocultar un fallo de implementación.

## Métrica única

`Test Success Rate = tests passed / tests executed × 100`. Objetivo: **100 %**.
Los tests omitidos, saltados o no ejecutados se reportan aparte y **no** cuentan como éxito.

## Cobertura: 100/80/0 por archivo

Definida en `coverage-policy.toml`; se aplica con `tools/check_coverage.py`.

| Categoría | Mínimo | Contenido |
| --- | --- | --- |
| `core` | 100 % | Validación de tiempos/segmentos, duración real, referencias a originales, reglas críticas de selección, validación de guiones, control de presupuesto |
| `important` | 80 % | Cliente Gemini, procesamiento de vídeo, jobs/reintentos, exportación, controladores de UI |
| `infrastructure` | — | Constantes, tipos sin lógica, configuración declarativa |

Reglas de aplicación:

- Todo archivo medido debe estar clasificado. Un archivo nuevo sin clasificar **rompe el gate**.
- Si un archivo "declarativo" incorpora lógica real, se reclasifica y se prueba.
- No se usa un porcentaje global para compensar archivos CORE por debajo del 100 %.

## Calidad

- **Ruff** es el linter y formateador de referencia (`uv run ruff check .`, `uv run ruff format`).
- Revisar también manualmente: duplicación conceptual, funciones largas, responsabilidades
  mezcladas y código muerto.
- Hooks con `pre-commit` de Python (no Husky, no Node):
  - `pre-commit`: Ruff + tests unitarios rápidos.
  - `pre-push`: suite completa + gate de cobertura por archivo.
- Ningún hook llama a la API real de Gemini ni genera coste.

## Linear y GitHub

- Todo issue vive en el proyecto **Ultimate Coding** con la etiqueta
  `genesis-guion-from-video-api-gemini` y, cuando aplique, una etiqueta de tipo
  (`Feature`, `Bug`, `Improvement`).
- Estados: `Todo → In Progress → In Review → Done`. **No usar Backlog.**
- Una issue = una rama = este repositorio. Base: `main`.
- Ramas: `feat|fix|refactor|chore|docs|perf/GEN-N-descripcion-corta` (minúsculas, sin acentos).
- Nunca trabajar directamente sobre `main`; todo cambio va por PR con revisión.
- No hacer merge, no crear repositorios, ramas ni PRs sin autorización explícita.

## Restricciones de producto

- Presupuesto objetivo **0 €**. Sin facturación, sin servicios contratados, sin modelos locales.
- Sin almacenamiento permanente: solo temporales de sesión; los originales nunca se tocan.
- No inventar escenas, declaraciones ni material inexistente. Si no hay contenido
  suficiente para la duración pedida, se declara la insuficiencia.
- Sin claves API en código, logs ni repositorio.
- Fuera de alcance: descarga de vídeos, renderizado/edición final, publicación en redes,
  infraestructura cloud propia.
