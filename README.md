# GENESIS Video AI — Gemini Edition

Aplicación de escritorio para Windows que analiza vídeos (MOV/MP4) con **Google Gemini API**
y propone **guiones audiovisuales verificables** construidos únicamente con material
realmente grabado: archivo de origen, tiempos de entrada/salida, orden narrativo y
duración calculada.

> Estado: **Fase 2 — análisis audiovisual técnico y segmentos**. Existe el análisis
> técnico del material, sus contratos y los validadores editoriales; todavía no
> hay generación de guiones.

## Requisitos

- Windows 10/11 (x64)
- [uv](https://docs.astral.sh/uv/) — gestiona el intérprete Python y el entorno virtual
- FFmpeg / ffprobe en el `PATH` (necesario para analizar los originales)

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
  ui/          # PySide6: ventanas y controladores de interacción (Fase 4)
  analysis/    # ffprobe: duración, pistas y metadatos MOV/MP4 con errores clasificados
  editorial/   # motor editorial puro: rangos, orden, integridad y duración total
  gemini/      # puerto Gemini y fake; el cliente real llega en la Fase 3
  jobs/        # trabajos y temporales de sesión con limpieza garantizada
  models/      # contratos Pydantic: fuentes, pistas, segmentos y peticiones
tests/
  unit/        # rápidos y deterministas (gate de commit)
  integration/ # ffprobe real sobre fixtures sintéticos, sin llamadas a Gemini
tools/         # utilidades de calidad (gate de cobertura)
```

## Qué sabe hacer la Fase 2

- **Análisis técnico** (`analysis.ffprobe.probe_video`): lee duración real,
  pistas y metadatos de MOV/MP4. Solo lectura del original, límite de peso
  (4 GiB por defecto) y fallos clasificados: original inexistente, contenedor
  no soportado, ffprobe ausente, ffprobe fallido o salida no interpretable.
- **Contratos** (`models.contracts`): `SourceMedia` (original medido),
  `StreamInfo` (pistas) y `Segment` (intervalo in/out referenciado por
  `source_id`), todos inmutables y explicitando rutas absolutas.
- **Validación editorial** (`editorial.sequence`): reglas puras sobre la
  secuencia — misma fuente, orden temporal, sin solapamientos, dentro de la
  duración real, y duración total coherente con lo pedido (la insuficiencia
  se declara).
- **Temporales** (`jobs.tempfiles.session_temp_dir`): directorio de sesión
  que se garantiza eliminado, incluso ante fallos.
- **Puerto Gemini** (`gemini.port`): protocolo `GeminiScriptPort` y
  `FakeGeminiScriptPort` que registra peticiones sin simular inferencia de
  ningún tipo.

## Roadmap

- [x] Fase 1 — base técnica, repositorio y quality gates (GEN-18)
- [x] Fase 2 — análisis audiovisual técnico y segmentos (GEN-36)
- [ ] Fase 3 — cliente Gemini y generación de guiones verificables
- [ ] Fase 4 — jobs completos, interfaz de usuario PySide6 y exportación

## Reglas del proyecto

- Las reglas de negocio (validación de tiempos, duración, referencias a originales)
  viven en `editorial/` como funciones puras y deterministas.
- Nada de llamadas reales a Gemini en tests ni en hooks.
- Presupuesto objetivo **0 €**: nunca se activa facturación automáticamente.
- No se versiona material audiovisual ni credenciales.

Ver `AGENTS.md` para el protocolo de trabajo completo.
