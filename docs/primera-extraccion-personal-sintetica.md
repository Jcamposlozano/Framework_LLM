# Una extracción A real con autorización personal y nota sintética verificable

El modo `personal_synthetic_development` permite autorizar una extracción A con
OpenAI y `gpt-4.1-mini` sin afirmar que existe autorización institucional. Esta
implementación se comprobó exclusivamente con transporte simulado: no se hicieron
llamadas reales ni se utilizaron claves o historias clínicas durante su desarrollo.

## Alcance de la autorización

Solo se admite el fixture inventado `demo-extractor-epoc-001`, identificado además
como `extracteval.demo-extractor-epoc.v1`. Su SHA-256 canónico del contrato `Document`
completo está fijado en `application/authorization.py`:

```text
ec6d1883c667b563cb0801e3941481abc831d3a30d6fdaf7bd746b90fbf3421a
```

El verificador compara ese valor de confianza con el hash calculado del documento y
con el hash de la autorización. Incluye texto, identificador, fecha, procedencia,
contexto, entidad y secciones. La indentación del JSON no importa; cambiar cualquier
contenido del contrato impide la autorización personal. No se admite una lista de
fixtures, un hash esperado o un certificado de origen proporcionado por el usuario.
Declarar `synthetic: true`, reutilizar el identificador o recalcular el hash de otra
nota no basta. No se intenta detectar mediante heurísticas si una nota arbitraria
contiene información real: se permite exclusivamente la igualdad con este fixture
inventado incluido en el proyecto.

Las notas clínicas reales, anonimizadas o seudonimizadas siguen usando
`GovernanceAuthorization`, con sus cinco comprobaciones institucionales y hash
vinculado al documento. Su formato anterior no cambia. El modo personal no autoriza
V, estabilidad, otro modelo, otros documentos ni procesamiento de un corpus.

La autorización personal exige el booleano JSON `external_calls_authorized: true` y,
además, el CLI exige `--mode real --authorize-real --governance ...`. Falta de
consentimiento, hash incorrecto o modo desconocido bloquean el envío antes de
construir el cliente HTTP. No se mezclan campos personales e institucionales.
El modo predeterminado continúa siendo `mock`.

## Preparar y revisar, sin llamadas externas

Desde la raíz del checkout, con `.venv` instalado, usa un directorio nuevo. Este
paso reutiliza la preparación existente, conserva exactamente el diccionario y no
ejecuta extracción, V ni estabilidad:

```sh
export LAB=laboratorios/prueba-personal-sintetica-001
PYTHONPATH=scripts .venv/bin/python - <<'PY'
import os
from pathlib import Path
from auditar_integracion import prepare_lab
from extracteval.application.authorization import (
    DEMO_DOCUMENT_SHA256, PersonalSyntheticAuthorization,
)
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash

lab = prepare_lab(Path(os.environ["LAB"]))
doc = Document.model_validate_json(
    (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
)
assert doc.document_id == "demo-extractor-epoc-001"
assert content_hash(doc) == DEMO_DOCUMENT_SHA256
print(doc.model_dump_json(indent=2))  # Solo el fixture previamente verificado.
authorization = PersonalSyntheticAuthorization(
    mode="personal_synthetic_development",
    authorization_reference="personal-demo-extractor-001",
    fixture_id="extracteval.demo-extractor-epoc.v1",
    document_id="demo-extractor-epoc-001",
    document_hash=content_hash(doc),
    operation="extract_a",
    provider="openai",
    model_id="gpt-4.1-mini",
    external_calls_authorized=False,
)
with (lab / "consentimiento.pendiente.json").open("x", encoding="utf-8") as stream:
    stream.write(authorization.model_dump_json(indent=2) + "\n")
PY
```

La nota debe decir exactamente:

> ANÁLISIS: EPOC estable, sin exacerbación actual. Antecedentes inciertos. Fecha de inicio desconocida.

La plantilla pendiente tiene consentimiento en falso y no autoriza un envío. Tras
revisar el documento y decidir personalmente permitir una llamada externa, ejecuta
este paso explícito, que todavía no llama a OpenAI:

```sh
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from extracteval.application.authorization import PersonalSyntheticAuthorization
from extracteval.core.documents import Document

lab = Path(os.environ["LAB"])
pending = PersonalSyntheticAuthorization.model_validate_json(
    (lab / "consentimiento.pendiente.json").read_bytes()
)
authorization = PersonalSyntheticAuthorization.model_validate(
    pending.model_dump() | {"external_calls_authorized": True}
)
doc = Document.model_validate_json(
    (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
)
authorization.validate_document(doc, "gpt-4.1-mini")
with (lab / "consentimiento.personal.json").open("x", encoding="utf-8") as stream:
    stream.write(authorization.model_dump_json(indent=2) + "\n")
PY
```

No marques casillas institucionales inexistentes. La autorización personal no tiene
esos campos. Conserva su referencia, fixture, operación, modelo, hash y consentimiento.
Los comandos de creación no sobrescriben archivos existentes.

## Comando completo para la futura extracción real

Es necesario disponer de acceso a `api.openai.com` y una credencial segura en el
entorno de ejecución, accesible al cliente como `OPENAI_API_KEY`. No incluyas su valor
en comandos guardados, JSON, repositorio ni registros. Esta tarea no configuró ni usó
una credencial. La preparación de la autorización por sí sola no comprueba acceso
de cuenta, red o disponibilidad del modelo.

Este es el único comando de esta guía que realiza llamadas al proveedor. **No se
ejecutó durante la implementación**:

```sh
EXTRACTEVAL_EXTRACTOR_MODEL=gpt-4.1-mini .venv/bin/python -m extracteval extract \
  --config "$LAB/configuraciones/extraccion/v1/config.json" \
  --input "$LAB/configuraciones/extraccion/v1/demo-documento.json" \
  --output "$LAB/ejecuciones/primera-a-personal-001" \
  --mode real \
  --authorize-real \
  --governance "$LAB/consentimiento.personal.json"
```

Se consulta primero la disponibilidad del modelo (`GET /models/...`) y después se
solicita **una extracción** (`POST /responses`), con `store=false` y cero reintentos
automáticos del proveedor para A. No se ejecutan V, B ni un experimento de estabilidad.
Una respuesta de OpenAI puede consumir tokens aunque sea inválida o truncada.

Código de salida 0 indica extracción completada; 2 indica configuración/entrada
inválida o fallo técnico. No inicies otra tentativa sin inspeccionar los artefactos.
Una ejecución completada se recupera sin nuevas llamadas, comprobando hashes y
configuración; si hay una intención guardada y no hay manifiesto, la ejecución se
detiene para inspección. No se promete recuperar una respuesta perdida ni se reenvía
automáticamente. Una autorización válida no demuestra corrección clínica.

## Inspeccionar el resultado sin llamar al proveedor

```sh
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from extracteval.adapters.storage.json_store import JSONRunStore
from extracteval.application.authorization import PersonalSyntheticAuthorization
from extracteval.application.extraction import ExtractionExecution, ExtractionManifest
from extracteval.core.documents import Document
from extracteval.core.hashing import content_hash
from extracteval.core.verification import ExtractionSnapshot

lab = Path(os.environ["LAB"])
store = JSONRunStore(lab / "ejecuciones/primera-a-personal-001")
manifest = store.get("manifest", ExtractionManifest)
assert store.artifact_hashes() == manifest.artifact_hashes
execution = store.get("execution", ExtractionExecution)
snapshot = store.get("extraction_a", ExtractionSnapshot)
authorization = store.get("governance", PersonalSyntheticAuthorization)
doc = Document.model_validate_json(
    (lab / "configuraciones/extraccion/v1/demo-documento.json").read_bytes()
)
authorization.validate_document(doc, "gpt-4.1-mini")
assert execution.document_hash == content_hash(doc)
assert execution.input_hash == manifest.input_hash
assert execution.mode == "real"
assert snapshot == execution.extraction_a
assert len(snapshot.results) == 6
response = execution.audit.response
print(json.dumps({
    "authorization": authorization.model_dump(mode="json"),
    "document_hash": execution.document_hash,
    "a_hash": content_hash(snapshot),
    "requested_model": execution.audit.requested_model,
    "effective_model": response.model.model_dump(mode="json") if response else None,
    "provider_request_id": response.provider_request_id if response else None,
    "usage": response.usage.model_dump(mode="json") if response and response.usage else None,
    "error": execution.audit.error.model_dump(mode="json") if execution.audit.error else None,
    "results": [{
        "variable_id": r.trace.variable_id,
        "value": r.value.model_dump(mode="json") if r.value else None,
        "state": snapshot.semantic_states.get(r.trace.variable_id),
        "operation": r.operation,
        "evidence_items": len(r.evidence.items),
        "technical_error": r.technical_error.code if r.technical_error else None,
    } for r in snapshot.results],
}, ensure_ascii=False, indent=2))
PY
```

Revisa `governance.json`, `request.json`, `execution.json`, `extraction_a.json` y
`manifest.json`. Si falta el manifiesto, trata la tentativa como incompleta; la
inspección anterior fallará deliberadamente. Un `usage=null` significa consumo no
reportado, no consumo cero. No presentes los seis resultados como validación clínica
ni como resultados científicos de fases anteriores.

## Pruebas de implementación

`tests/test_personal_synthetic_authorization.py` comprueba el hash fijado, igualdad
con el fixture existente, manipulación de texto/metadatos/identidad, declaraciones
sintéticas falsas, hashes recalculados, consentimiento ausente/falso o mal tipado,
modos desconocidos y mezcla de campos. Incluye escenarios inventados clasificados
como clínicos reales, anonimizados y seudonimizados; no usa historias clínicas.
Se prueba el CLI personal y el institucional con transporte sustituido, tokens,
modelo efectivo, auditoría, persistencia y reanudación, así como el rechazo antes de
construir transporte y la imposibilidad de usar el modo personal para V.

La batería completa bloquea conexiones de red. Las seis variables, prompts,
reconciliación y artefactos científicos previos permanecen sin cambios.

Validación de esta entrega: **294 pruebas aprobadas y 1 omitida** por depender del
estudio local ignorado `laboratorios/mi_estudio_001`. Las 35 pruebas nuevas de
autorización pasaron, incluidos los bloques Python de preparación, consentimiento e
inspección de esta guía; la extracción se sustituyó por transporte simulado. También
pasaron `ruff check .`, `ruff format --check .`, `mypy`,
`python -m build --no-isolation` y `python -m pip check`, ejecutados con `.venv`.
