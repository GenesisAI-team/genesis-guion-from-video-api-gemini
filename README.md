# GENESIS Video AI — Gemini Edition

Aplicación de escritorio para Windows que analiza vídeos (MOV/MP4) con **Google Gemini API**
y propone **guiones audiovisuales verificables** construidos únicamente con material
realmente grabado: archivo de origen, tiempos de entrada/salida, orden narrativo y
duración calculada.

> Estado: **Fase 3 — cliente Gemini y guiones trazables**. La base técnica (Fase 1),
> el análisis audiovisual con ffprobe y los contratos editoriales (Fase 2) están
> cerrados; la UI de escritorio PySide6 llega en la Fase 4.

## Qué añade la Fase 3

- **Cliente real de Gemini detrás del puerto**: `RealGeminiScriptPort` implementa
  `GeminiScriptPort` con el SDK oficial `google-genai`, aislado y sustituible por
  dobles (`FakeGeminiScriptPort`, `ScriptedGeminiScriptPort`).
- **Errores tipados y límites**: cuota (429), credenciales (401/403), plazo
  (`timeout_s`), cancelación cooperativa por evento y respuesta inválida.
- **Guiones trazables**: la propuesta (`ScriptProposal`) lleva origen, tramos in/out
  reales, narración y duración total calculada de las entradas.
- **Sin confianza ciega**: la salida del modelo se valida contra un esquema JSON
  estricto y contra las reglas editoriales del material medido
  (`editorial/script_validation.py`). Los segmentos inventados se rechazan
  (`InventedSegmentError`) y la insuficiencia se declara (`InsufficientMaterialError`).

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

## CI

El workflow `.github/workflows/ci.yml` ejecuta en cada push a `main` y en cada PR:
Ruff (lint y formato), suite completa y gate de cobertura 100/80/0 con `uv`.
**Sin claves API, sin facturación y sin llamadas reales a Gemini.**

## Ejecución real con Gemini (solo opt-in manual)

Por defecto el presupuesto es **0 €**: ningún test ni hook llama a la API y sin
credencial el cliente falla de forma controlada. Para una prueba manual puntual,
exporta la clave en el entorno (nunca en Git) y lanza la generación desde Python:

```python
from pathlib import Path

from genesis_video_ai.gemini.client import RealGeminiScriptPort
from genesis_video_ai.gemini.config import GeminiClientConfig
from genesis_video_ai.gemini.port import ScriptProposalRequest
from genesis_video_ai.models.contracts import Segment, SourceMedia

source = SourceMedia(
    id="src-1",
    path=Path(r"C:\ruta\original.mp4"),
    container="mp4",
    duration_s=120.0,
    size_bytes=1,
    format_name="mp4",
)
request = ScriptProposalRequest(
    source=source,
    segments=(Segment(source_id=source.id, start_s=0.0, end_s=45.0),),
    requested_duration_s=45.0,
)
proposal = RealGeminiScriptPort(GeminiClientConfig.from_env()).propose_script(request)
print(proposal)
```

El coste de cada ejecución real depende de las tarifas vigentes de Google para el
modelo configurado (`gemini-2.5-flash` por defecto); el nivel gratuito de la API
cubre pruebas manuales puntuales sin facturación.

## Estructura

```
src/genesis_video_ai/
  ui/          # PySide6: ventanas y controladores de interacción (Fase 4)
  analysis/    # ffprobe/FFmpeg y análisis técnico del material
  editorial/   # motor editorial: segmentos, selección, validación y reglas puras
  gemini/      # puerto, cliente real, configuración, prompts y errores tipados
  jobs/        # gestión de trabajos, temporales y reintentos
  models/      # contratos Pydantic compartidos
tests/
  unit/        # rápidos y deterministas (gate de commit)
  integration/ # flujos controlados, sin llamadas reales a Gemini
tools/         # utilidades de calidad (gate de cobertura)
.github/workflows/  # CI de quality gates sin coste
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
- **Puerto Gemini** (`gemini.port`): protocolo `GeminiScriptPort`,
  `FakeGeminiScriptPort` que registra peticiones sin simular inferencia de
  ningún tipo, y `ScriptedGeminiScriptPort` con respuestas programadas.

## Qué sabe hacer la Fase 3

- **Cliente real** (`gemini.client.RealGeminiScriptPort`): genera el guion con
  la API oficial detrás de `GeminiScriptPort`; construye el prompt con el
  original y el material medido, fuerza salida JSON con esquema y valida la
  respuesta antes de entregar una propuesta trazable.
- **Configuración** (`gemini.config.GeminiClientConfig`): modelo, plazo,
  límites de salida, temperatura, tolerancia de redondeo y clave vía entorno
  (`GEMINI_API_KEY`/`GOOGLE_API_KEY`), guardada como `SecretStr`.
- **Errores tipados** (`gemini.errors`): indisponibilidad, credenciales
  inválidas, cuota (429), plazo excedido, cancelación y respuesta inválida.
- **Validación editorial de la propuesta** (`editorial.script_validation`):
  los tramos propuestos deben derivar del material medido
  (`InventedSegmentError` si no), ordenados, sin solapes, dentro de la
  duración real, y el total se contrasta con lo pedido (insuficiencia
  declarada, exceso rechazado).
- **Contrato de guion** (`ScriptProposal`/`ScriptEntry`): origen, ventanas
  in/out reales, narración y duración total calculada de las entradas.

## Roadmap

- [x] Fase 1 — base técnica, repositorio y quality gates (GEN-18)
- [x] Fase 2 — análisis audiovisual técnico y segmentos (GEN-36)
- [x] Fase 3 — cliente Gemini y generación de guiones verificables (GEN-45)
- [ ] Fase 4 — jobs completos, interfaz de usuario PySide6 y exportación

## Reglas del proyecto

- Las reglas de negocio (validación de tiempos, duración, referencias a originales)
  viven en `editorial/` como funciones puras y deterministas; los prompts, el SDK y
  la configuración viven en `gemini/` y no deciden nada editorial.
- Nada de llamadas reales a Gemini en tests ni en hooks; la ejecución real es
  siempre manual y opt-in.
- Presupuesto objetivo **0 €**: nunca se activa facturación automáticamente.
- No se versiona material audiovisual ni credenciales; la clave viaja por entorno.

## Limitaciones conocidas (Fase 3)

- Un solo original por propuesta: `ScriptProposalRequest` referencia una única
  fuente; el material multi-fuente queda para fases posteriores.
- La cancelación es cooperativa: al expirar el plazo el hilo de trabajo se abandona
  (el SDK no expone aborto de petición en llamadas síncronas).
- El modelo solo recorta dentro de los segmentos medidos; no genera material nuevo
  y la insuficiencia se declara si el material no alcanza la duración pedida.
- Sin UI de escritorio todavía (Fase 4) y sin exportación/renderizado (fuera de alcance).

Ver `AGENTS.md` para el protocolo de trabajo completo.
