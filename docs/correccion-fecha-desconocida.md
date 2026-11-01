# Fecha desconocida en Extractor A

## Causa raíz y representación existente

La ejecución reportada `primera-a-personal-001` recibió una respuesta del modelo
`gpt-4.1-mini-2025-04-14` con `{"kind":"date","value":"0000-01-01"}` para
`fecha_indice_evento`, pese a que la nota dice «Fecha de inicio desconocida».
El año cero no es válido. Pydantic rechazó el payload con `date_parsing` y A registró
`invalid_response`; no se trató de un fallo de transporte. El rechazo fue correcto.
Esta corrección usa una reproducción sintética del caso comunicado, no modifica ni
reinterpreta la ejecución histórica.

Antes del cambio se inspeccionaron `VerificationPayload`, `VariableVerification`,
`SemanticState`, `DateValue`, el diccionario EPOC y el prompt A. El diccionario ya
indica no inventar fechas y usar ausencia de valor cuando no pueda determinarse una
fecha válida. `proposed_value` admite `null`; `DateValue.value` no admite una fecha
inválida ni `null` dentro del objeto. El estado `value` exige una propuesta no nula;
`indeterminate` permite ausencia de valor y ya se usa en el fixture de esta nota.

La representación compatible para este caso es:

```json
{
  "variable_id": "fecha_indice_evento",
  "proposed_value": null,
  "semantic_state": "indeterminate",
  "evidence": [],
  "evidence_type": "none",
  "applied_rule_ids": [],
  "uncertainty_flags": ["insufficient_documentation"],
  "requires_human_review": true
}
```

Este ejemplo muestra una propuesta dentro de `VerificationPayload.variables`, no el
payload completo. No se cambia el significado de indeterminación, abstención,
ausencia documentada o falta de respuesta. La evidencia se conserva cuando exista;
el fixture vigente no aporta cita para esta variable.

## Corrección mínima y trazabilidad

El prompt v1 ordenaba no inventar fechas, pero no daba un ejemplo explícito para la
fecha desconocida con `proposed_value: null`. El nuevo `clinical-extractor.v2` añade
esa instrucción y prohíbe rellenar una fecha desconocida con `0000-01-01`,
`1900-01-01`, la fecha actual u otros valores predeterminados. El resto del prompt
permanece idéntico. Esto guía al modelo; no constituye una nueva prueba real de su
adherencia a las instrucciones.

La validación estricta y los esquemas se mantienen sin cambios. No hay coerción,
reemplazo silencioso ni lista negra de fechas válidas: `1900-01-01` sigue siendo una
fecha válida si está documentada y autorizada por el diccionario. Un modelo que
vuelva a emitir un año cero seguirá produciendo un fallo técnico auditable.

Se conserva intacto el prompt v1 y su SHA-256
`2ffe1fb39905bb106a6663ba647de2bd58dc866f8fb41ce34663eb7c84909e7d`.
El SHA-256 del nuevo prompt v2 es
`43a5cccc701553eb30c88a38d3b8492baae3f7dcd4864a27390677823ab9231d`.
Las nuevas preparaciones copian `extractor_v2.txt`, registran
`prompt_version: clinical-extractor.v2` y verifican su hash con el cargador existente.
Preparar sobre una configuración v1 se rechaza antes de escribir archivos;
no se migran configuraciones o resultados históricos automáticamente.

Para una tentativa futura, prepara un laboratorio nuevo y sigue la
[guía de autorización personal sintética](primera-extraccion-personal-sintetica.md)
con un nombre de laboratorio y destino de ejecución nuevos. La preparación usará v2.
No reutilices ni sobrescribas `primera-a-personal-001`. No se han inventado
autorizaciones institucionales ni efectuado llamadas a OpenAI en esta corrección.

## Archivos modificados y comprobaciones

- `prompts/clinical-extractor.v2.txt`: versión nueva de A con instrucciones para
  fechas desconocidas; v1 se conserva.
- `scripts/extraccion_laboratorio.py`: selecciona v2, registra su versión/hash y
  rechaza la actualización implícita de configuraciones anteriores.
- `tests/test_extraction.py`: regresiones de año cero, fecha desconocida válida,
  conservación de las otras cinco variables y paso por V/B; prueba de fecha válida
  explícita `1900-01-01` y conservación de configuraciones v1.
- `docs/extractor-a.md` y este informe: documentación del cambio y su alcance.

La regresión construye una respuesta Responses completada del modelo reportado con
transporte simulado. Se comprueba `date_parsing` directamente, `invalid_response` en
A, conservación de identidad/uso/respuesta original y ausencia de valores reparados
o estados clínicos inventados. El caso positivo usa el mismo documento con `null` e
`indeterminate`, valida las seis propuestas y completa V/B sin modificar A.

Los contratos, diccionario, prompts V, política B, autorizaciones y resultados
previos no cambian. Las pruebas usan exclusivamente datos sintéticos y bloquean
conexiones de red.

Comandos desde la raíz del repositorio:

```sh
.venv/bin/python -m pytest -q -rs
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/python -m build --no-isolation
.venv/bin/python -m pip check
```

Resultado: **298 pruebas aprobadas y 1 omitida** por ausencia del estudio local
ignorado `laboratorios/mi_estudio_001`. Ruff y formato aprobados (96 archivos);
mypy aprobado (36 archivos); sdist/wheel construidos y `pip check` sin dependencias
incompatibles. No se ejecutó una nueva prueba real con OpenAI.
