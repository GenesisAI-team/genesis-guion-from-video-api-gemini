# GENESIS Video AI — Gemini Edition

Aplicación de escritorio para Windows que analiza vídeos (MOV/MP4) con **Google Gemini API**
y propone **guiones audiovisuales verificables** construidos únicamente con material
realmente grabado: archivo de origen, tiempos de entrada/salida, orden narrativo y
duración calculada.

> Estado: **Fase 1 — base técnica**. Todavía no hay análisis ni generación de guiones.

## Requisitos

- Windows 10/11 (x64)
- [uv](https://docs.astral.sh/uv/) — gestiona el intérprete Python y el entorno virtual
- FFmpeg / ffprobe en el `PATH` (solo necesario a partir de la Fase 2)

El proyecto usa **Python 3.12**, instalado y gestionado por `uv`. Nunca se instala nada
en el Python global del sistema.

## Puesta en marcha

```powershell
uv python install 3.12
uv sync
uv run pytest
```

## Comandos de calidad

| Comando | Qué hace |
| --- | --- |
| `uv run pytest` | Suite de tests |
| `uv run pytest --cov=genesis_video_ai --cov-report=json:coverage.json` | Tests + informe de cobertura |
| `uv run python -m tools.check_coverage` | Gate de cobertura **100/80/0 por archivo** |
| `uv run python -m tools.prepush` | Gate completo de push (suite + cobertura) |
| `uv run ruff check .` | Lint |
| `uv run ruff format --check .` | Formato |
| `uv run pre-commit run --all-files` | Todos los hooks de la etapa `pre-commit` |
| `uv run pre-commit run --all-files --hook-stage pre-push` | Gate de push |

Instalación de hooks:

```powershell
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Estructura

```
src/genesis_video_ai/
  ui/          # PySide6: ventanas y controladores de interacción
  analysis/    # ffprobe/FFmpeg y análisis técnico del material
  editorial/   # motor editorial: segmentos, selección, validación, guiones
  gemini/      # integración con el SDK oficial google-genai
  jobs/        # gestión de trabajos, temporales y reintentos
  models/      # contratos Pydantic compartidos
tests/
  unit/        # rápidos y deterministas (gate de commit)
  integration/ # flujos controlados, sin llamadas reales a Gemini
tools/         # utilidades de calidad (gate de cobertura)
```

## Reglas del proyecto

- Las reglas de negocio (validación de tiempos, duración, referencias a originales)
  viven en `editorial/` como funciones puras y deterministas.
- Nada de llamadas reales a Gemini en tests ni en hooks.
- Presupuesto objetivo **0 €**: nunca se activa facturación automáticamente.
- No se versiona material audiovisual ni credenciales.

Ver `AGENTS.md` para el protocolo de trabajo completo.
