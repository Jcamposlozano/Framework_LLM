# Auditoría ejecutable e integración técnica de extracteval

Fecha: 31 de octubre de 2026. Base: `origin/main`, commit
`849f57211fc117bab5806f3a3f03e04026529771`. Rama: `audit/extracteval-phases-1-3`.
Entorno: Linux x86_64, Python 3.12.14 y versiones de `requirements-dev.lock`.
Todas las notas utilizadas son inventadas. No se utilizaron claves ni se hicieron
llamadas a proveedores. La ruta real se ejercitó exclusivamente mediante transporte
sustituido; no se verificó disponibilidad de cuenta ni aceptación remota del esquema.

## Arquitectura revisada

| Componente | Estado y responsabilidad |
|---|---|
| `core/` | Contratos públicos 1.0, valores etiquetados, dimensiones semánticas/operativas, referencias expertas, parámetros, trazas y hashes. Sin importaciones de adaptadores; prueba de límites arquitectónicos existente. |
| `application/extraction.py` | A reutiliza `VerificationPayload` como respuesta intermedia y produce seis `ExtractionResult`. Configuración y auditoría propias; verifica diccionario, prompt, esquema y posprocesamiento. |
| `application/verification.py` | V recibe documento, diccionario y configuración; su interfaz no acepta A. Filtra metadatos y valida propuestas. No interpreta clínicamente las negaciones por código. |
| `application/comparison.py`, `reconciliation.py` | Comparación reproducible y política externa. La política vigente no autoriza reemplazos: discrepancias y evidencia insuficiente requieren revisión. B conserva la identidad y hash de A. |
| `application/pipeline.py`, `adapters/storage/` | Persistencia JSON de creación exclusiva, manifiestos, controles de integridad y etapas reanudables. La nueva intención durable de V impide repetir un envío incierto. |
| `application/stability*.py` | Reutiliza A/V/B; modalidades completa y A fija, reserva de intentos, identificadores de repetición, análisis por documento y pares comunes A/B. |
| `adapters/models/` | Mocks programados y HTTP Responses sin SDK adicional. Conserva modelo solicitado/efectivo, tokens, identificadores y errores saneados; ausencia de uso reportado permanece desconocida. |
| `scripts/` | Puentes de laboratorio, importación, diseño y estabilidad. La nueva auditoría compone estas funciones existentes; no añade otro extractor, comparador o reconciliador. |
| `templates/laboratorio_yaml_json/` | Plantillas de trabajo; variables vacías y etapas pendientes en un laboratorio nuevo son deliberadas. La auditoría copia el diccionario EPOC existente y comprueba igualdad completa tras prepararlo. |
| `tests/`, `docs/` | Contratos, límites, escenarios sintéticos, CLI, persistencia y estabilidad. Los informes históricos describen entregas anteriores; este documento registra la revisión actual. |

Duplicaciones identificadas: `ConstantModel`/`ScriptedModel` son mocks generales de
Fase 1; `MockExtractorModel`/`MockVerifierModel` añaden identidades distintas y
respuestas documentales estructuradas. No son extractores clínicos alternativos.
Las plantillas legadas se conservan por compatibilidad y migración. Los fixtures
separados A/V son intencionales: no se deriva V de la salida generada por A.

`DocumentResolver`, `ResultRepository` y `ArtifactStore` son puertos de extensión
sin implementación general utilizada por estos CLI. No se eliminaron como código
muerto: forman parte de la API pública. `reconciler_model` se conserva como metadato
de configuración; el reconciliador implementado es determinista y no llama a un LLM.
No se detectó una dependencia necesaria ausente para el flujo seleccionado. YAML y
XLSX son extras `lab`/`dev`; el cliente HTTP usa la biblioteca estándar. La instalación
editable debe permitir el aislamiento de build para resolver requisitos del backend.

## Defectos corregidos

| Criticidad | Defecto comprobado | Corrección y evidencia |
|---|---|---|
| Alta | El esquema para Responses conservaba `oneOf` y `discriminator` de la unión etiquetada de Pydantic. | Se convierte a `anyOf`, conservando los `kind` exclusivos; se eliminan discriminadores y valores predeterminados. Se mantienen objetos cerrados y campos requeridos. Prueba recursiva del esquema enviado por A/V y comprobación de que el esquema público no se muta. |
| Alta | V podía reenviarse tras una interrupción antes de guardar el resultado. | `verification-request.json` se persiste antes de generar; sin resultado durable se bloquea la repetición automática. V completo se guarda antes de retornar al coordinador. Pruebas de interrupción antes y después de persistir V, más reanudación de estabilidad sin generación adicional. |
| Alta | A no podía guardar una respuesta válida que reportara `temperature=1.0`: el registro aplicaba a parámetros observados las restricciones de parámetros solicitables. | Reproducido con transporte simulado: `UnsupportedConfigurationError` al construir `ModelRunRecord`. Las capacidades siguen validando solicitudes; `ModelParameters` valida valores observados, que se conservan como auditoría sin habilitar su envío. Contratos JSON y valores clínicos sin cambios. |
| Media | El informe mostraba acuerdos marginales A/B junto a una diferencia calculada sobre pares comunes, con denominadores potencialmente distintos. | Las columnas junto a B − A ahora muestran los mismos pares comunes que esa diferencia. Se conserva el análisis marginal en JSON. Regresión con denominadores marginales 1 y denominador común 0. |
| Media | Una respuesta sin `usage` se representaba mediante un objeto vacío de tokens. | `usage=None` distingue consumo no reportado de cero observado; regresión del adaptador. |
| Baja | `mypy` fallaba por un `type: ignore[arg-type]` innecesario. | Se retiró el comentario. Comprobación limpia sin caché y comprobación incremental; no se deshabilitaron diagnósticos. |

## Validación ejecutada

Desde la raíz del repositorio, usando el entorno virtual:

```sh
.venv/bin/python -m pytest -q -rs
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy --no-incremental
.venv/bin/mypy
.venv/bin/python -m build --no-isolation
.venv/bin/python -m pip check
.venv/bin/python scripts/auditar_integracion.py \
  --destino laboratorios/auditoria-tecnica-2026-10-31-final
```

Resultado final: **259 pruebas aprobadas, 1 omitida**. La omitida depende del estudio
local ignorado `laboratorios/mi_estudio_001`, ausente en un checkout distribuido.
Ruff, formato, mypy, build de sdist/wheel y `pip check` aprobados. Los tests bloquean
conexiones de red; la auditoría ejecutable también las bloquea y registra cualquier
intento. Sus comandos no activan el modo real.

Las nuevas pruebas de los CLI sustituyen la fábrica HTTP antes de construirla y
eliminan `OPENAI_API_KEY` del entorno de prueba. Usan autorizaciones inventadas solo
para comprobar las barreras sobre documentos sintéticos; no modifican las
autorizaciones del laboratorio. También prueban rechazo por hash distinto,
autorización incompleta y ausencia de `--authorize-real`, antes de construir transporte.
Respuestas truncadas y rechazos conservan uso e identidad y generan fallos técnicos,
sin convertirlos en categorías clínicas. Las pruebas existentes cubren timeout,
indisponibilidad, reintentos acotados y errores de esquema.

## Evidencia A → V → B y Fase 3

El [resumen versionado](evidence/auditoria-tecnica-2026-10-31.json) contiene hashes,
conteos y denominadores de la ejecución. Los artefactos completos se conservan,
ignorados por Git, en `laboratorios/auditoria-tecnica-2026-10-31-final/`:

- `auditoria.json`: resultado del ejecutable y huellas de A/V/B.
- `ejecuciones/fase2/demo-extractor-v1/a/`: solicitud, ejecución, A y manifiesto.
- `ejecuciones/fase2/demo-extractor-v1/b/`: V, comparación, decisiones, B y manifiesto.
- `ejecuciones/estabilidad/piloto-mock-v1/`: 100 repeticiones, ledger de 160 intentos,
  JSON, informe e inventario SHA-256 de integridad.
- `03_estabilidad/resultados.json` e `informe.md`: vistas del piloto.
- `primera_prueba/gobierno.pendiente.json`: plantilla con todas las autorizaciones
  en falso. No habilita una ejecución real.

A/V/B produce seis decisiones: **2 KEEP_A y 4 HUMAN_REVIEW**. La negación explícita
de exacerbación actual conserva la cadena categórica `"false"`; la fecha desconocida
queda sin valor y con estado `indeterminate`. Las pruebas adicionales verifican fecha
ISO explícita, dominios, evidencia incorrecta, abstención y seis fallos operativos ante
una respuesta A inválida. La prueba de independencia introduce marcadores exclusivos
de A y comprueba que no aparecen en la solicitud V. No se afirma que un mock extraiga
o comprenda negaciones: sus respuestas están programadas.

El piloto usa **10 documentos inventados × 5 repeticiones × 2 modalidades**:
100 identidades únicas, 97 ejecuciones sin fallo técnico y 3 con timeout programado.
Consume 60 intentos A y 100 V, de los que 157 devuelven respuesta mock y 3 fallan.
En completa hay cinco A distintas por documento; en A fija se reutilizan exactamente
la identidad y hash de una A por documento. Se verificaron todos los hashes A/B.
La segunda ejecución conserva resultados y árbol de artefactos, sin nuevos intentos.

Los denominadores excluyen errores/falta de respuesta del acuerdo semántico y
mantienen un acuerdo operativo separado. El contraste A/B usa pares comunes del
mismo documento; las fechas se comparan como fechas ISO. Los rangos y conteos de
fechas, estados y errores están separados. No se calculan PGEC, exactitud ni intervalos
confirmatorios; A fija es constante por diseño. Los tres fallos programados son
resultados esperados del piloto, no fallos de pytest.

## Primera prueba real futura: preparada, sin ejecutar

La preparación anterior deja un documento **completamente sintético**, un diccionario
compartido, prompts versionados de A/V, esquema y configuración `gpt-4.1-mini`.
La política conservadora no cambia. El comando requiere una autorización revisada
vinculada al hash exacto del documento y una credencial suministrada de forma segura
fuera del repositorio. La plantilla pendiente no satisface esa autorización. Esta
auditoría no configura credenciales ni habilita acceso a `api.openai.com`.

Comandos exactos desde la raíz para una futura ejecución autorizada; **no se ejecutaron**:

```sh
export LAB=laboratorios/auditoria-tecnica-2026-10-31-final
GOBIERNO="$LAB/primera_prueba/gobierno.revisado.json"

.venv/bin/python -m extracteval extract \
  --config "$LAB/configuraciones/extraccion/v1/config.json" \
  --input "$LAB/configuraciones/extraccion/v1/demo-documento.json" \
  --output "$LAB/primera_prueba/a" --mode real \
  --authorize-real --governance "$GOBIERNO"

# Registrar A mediante el puente tipado existente, sin modificar el corpus.
PYTHONPATH=scripts .venv/bin/python - <<'PY'
import os
from pathlib import Path
from extracteval.core.documents import Document
from verificacion_laboratorio import register_original

lab = Path(os.environ["LAB"])
doc = Document.model_validate_json(
    (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
)
entry = register_original(
    lab, document_id=doc.document_id,
    source=lab / "primera_prueba/a/extraction_a.json", document=doc,
)
with (lab / "primera_prueba/entrada-v.json").open("xb") as stream:
    stream.write(entry.read_bytes())
PY

.venv/bin/python -m extracteval verify \
  --config "$LAB/configuraciones/verificacion/v1/config.json" \
  --input "$LAB/primera_prueba/entrada-v.json" \
  --output "$LAB/primera_prueba/vb" --stage all --mode real \
  --authorize-real --governance "$GOBIERNO"
```

Ejecutar cada paso solo si el anterior termina con código 0; una carpeta nueva evita
mezclar tentativas. La A fallida se conserva para auditoría, pero no se continúa esta
primera prueba como si fuera una extracción satisfactoria. A usa cero reintentos de
proveedor; V mantiene su presupuesto vigente de hasta dos reintentos. El adaptador
consulta primero la disponibilidad del modelo y luego genera la respuesta; el ledger
de estabilidad cuenta intentos `generate`, no solicitudes HTTP. No hay presupuesto
monetario inventado ni costos sin tabla de precios versionada.

Los artefactos `execution.json` y `verification.json` contienen modelo solicitado y
efectivo, parámetros, identificadores, tokens cuando se reportan y errores saneados.
B y su manifiesto se guardan por separado. Solo una ejecución futura podrá comprobar
la disponibilidad del modelo, la aceptación del esquema por el proveedor y la respuesta
del LLM; estos comandos no constituyen una prueba de esas propiedades.

## Pendientes por criticidad

| Criticidad | Pendiente | Efecto |
|---|---|---|
| Alta, requisito externo para el futuro ensayo | Revisión y autorización documentada, credencial segura y acceso de red al proveedor. | La ruta real permanece cerrada por defecto. Ninguna autorización operativa existente se cambió. |
| Alta, científica | Definiciones y decisiones clínicas pendientes, referencia experta, protocolo y diseño confirmatorio. | No interpretar integración técnica ni estabilidad mock como validación científica. |
| Media | Prueba real de una sola nota sintética: cuenta, esquema, identidad y consumo efectivos. | Pendiente por restricción explícita de esta tarea; los transportes simulados no la sustituyen. |
| Media | Interrupción con intención durable pero sin respuesta persistida. | Se detiene y requiere inspección; no promete recuperar una respuesta perdida ni reenvía automáticamente. |
| Baja | Matriz Python 3.11/3.13 y plataformas distintas de Linux 3.12. | No ejecutada; la validación de esta entrega se limita al entorno indicado. |

No quedan fallos técnicos sin explicar en las comprobaciones requeridas. Se
conservaron contratos públicos, diccionario, reglas, PGEC, protocolo y autorizaciones.
No se procesaron historias clínicas ni se sobrescribieron artefactos científicos.

## Archivos de esta entrega

- `src/extracteval/core/specification.py`: tipado del adaptador semántico.
- `src/extracteval/core/experiments.py`: parámetros observados frente a solicitados.
- `src/extracteval/application/verification.py`: esquema y persistencia de V completo.
- `src/extracteval/application/pipeline.py`: intención durable antes de enviar V.
- `src/extracteval/application/stability_analysis.py`: denominadores del informe.
- `src/extracteval/adapters/models/openai.py`: uso no reportado como `None`.
- `tests/test_extraction.py`: integración de ambos CLI y barreras sin credenciales.
- `tests/test_phase2.py`: interrupciones de V y recuperación durable.
- `tests/test_phase2_openai_cli.py`: subconjunto de esquema y ausencia de mutaciones.
- `tests/test_stability.py`: coherencia entre pares mostrados y diferencia A/B.
- `scripts/auditar_integracion.py`: reproducción local con conexiones bloqueadas.
- `README.md`: estado efectivo y límites de las Fases 1–3.
- `docs/auditoria-integracion-2026-10-31.md`: informe, comandos y pendientes.
- `docs/evidence/auditoria-tecnica-2026-10-31.json`: evidencia sintética resumida.
