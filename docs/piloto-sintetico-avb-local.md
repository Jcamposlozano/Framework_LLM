# Completar A → V → B desde una extracción A local ya guardada

Este procedimiento reutiliza `primera-a-personal-003`: no vuelve a ejecutar A ni
modifica sus archivos. Ejecuta una verificación V independiente y produce comparación
y B con la política conservadora existente. Solo acepta el documento completo cuyo
hash corresponde a `demo-extractor-epoc-001`.

La autorización `extract_a` anterior no permite enviar V. Para este paso se introduce
la operación personal `verify_v`, con consentimiento independiente. Ambas operaciones
siguen limitadas al mismo fixture sintético y a `gpt-4.1-mini`; sus autorizaciones no
son intercambiables. Los controles institucionales para otros documentos y los de
estabilidad permanecen intactos.

## Preparación local sin llamadas

Desde la raíz de tu checkout, con la credencial ya cargada en la misma terminal:

```sh
git fetch origin
git switch feat/synthetic-avb-pilot

export LAB=laboratorios/piloto-local-sintetico-002
export PILOTO="$LAB/ejecuciones/piloto-avb-real-001"
export EXTRACTEVAL_VERIFIER_MODEL=gpt-4.1-mini

PYTHONPATH="$PWD/src:$PWD/scripts" .venv/bin/python scripts/completar_piloto_sintetico.py preparar \
  --laboratorio "$LAB" --destino "$PILOTO" --mode real
```

Por defecto se toma A de `$LAB/ejecuciones/primera-a-personal-003`. Puede indicarse
otra carpeta con `--extraccion-a`, pero debe contener una extracción completada del
mismo fixture exacto y manifiesto válido. El modo real también exige que A sea real.
No se admite una extracción fallida como base ni un destino que contenga o esté
contenido en la carpeta original de A.

La preparación comprueba el manifiesto, hashes, documento, diccionario y trazas.
Guarda la entrada tipada para V/B y una configuración que referencia el diccionario,
prompt V y política vigentes. V recibe exclusivamente documento, diccionario y su
propia configuración: no recibe A, sus identificadores, respuestas o decisiones.

Se genera `revision-evidencia-a.json`: conserva cada evidencia original e informa
la posición candidata si la cita aparece exactamente una vez en el documento y su
sección es consistente. Cuenta coincidencias solapadas y usa índices Unicode
`[start,end)`. Si hay ambigüedad, ausencia de cita o sección incorrecta no adivina
posiciones. **No aplica ninguna reparación a A ni usa estas posiciones candidatas
para silenciar advertencias en V/B.**

Las citas con offsets incorrectos continúan registradas como tales. B puede requerir
revisión humana por esos hallazgos o por el diccionario pendiente de aprobación.
Completar el recorrido técnico no acredita la corrección clínica de la evidencia.

## Ejecutar V real y generar B

El siguiente comando registra un consentimiento personal separado con
`operation: verify_v` y `external_calls_authorized: true`. Ejecutarlo expresa tu
autorización para enviar **esta única nota sintética** a OpenAI. No afirma que exista
autorización institucional ni extiende la autorización a otros documentos.

**Este paso sí realiza una llamada de generación y puede consumir tokens.** El
adaptador consulta primero el modelo y luego solicita V; no vuelve a generar A.
Para V personal se desactivan los reintentos automáticos, como en A.

```sh
PYTHONPATH="$PWD/src:$PWD/scripts" .venv/bin/python scripts/completar_piloto_sintetico.py ejecutar \
  --laboratorio "$LAB" --destino "$PILOTO" --mode real --autorizar-v-real
```

El script usa los CLI y pipeline existentes; B no llama a otro LLM. Conserva la
política de reconciliación sin reglas de reemplazo aprobadas y comprueba A de nuevo
después de la llamada. No corrige valores clínicos, fechas o evidencias en silencio.

El destino queda vinculado a modo, configuración y hashes originales. La repetición
de una ejecución completa recupera los resultados existentes sin enviar V otra vez.
Una interrupción con intención guardada pero sin resultado durable se detiene para
inspección. Ante un fallo, conserva el destino; una nueva tentativa debe ser una
decisión explícita y usar otro destino. No borres la intención para forzar un reenvío.

## Inspección offline

```sh
PYTHONPATH="$PWD/src:$PWD/scripts" .venv/bin/python scripts/completar_piloto_sintetico.py inspeccionar \
  --laboratorio "$LAB" --destino "$PILOTO" --mode real
```

La inspección no llama al proveedor ni reescribe los resultados. Verifica los hashes
y recalcula la comparación y reconciliación deterministas para contrastarlas con
los archivos guardados. Debe informar `a_unchanged: true`; revisa también `status`,
`v_error`, `v_model`, `v_usage`, `v_evidence_findings` y las seis `b_decisions`.
Código 0 significa finalización técnica; código 2 señala un fallo o inconsistencia.
`HUMAN_REVIEW` es una decisión de la política, no equivale a un error de transporte.

Artefactos nuevos, separados de la A histórica:

```text
piloto-avb-real-001/
  preparacion.json
  integridad-preparacion.json
  entrada.json
  configuracion-v.json
  respuesta-v-mock.json
  revision-evidencia-a.json
  consentimiento-v.json
  vb/
    governance.json
    verification-request.json
    verification.json
    comparison.json
    decisions.json
    extraction_b.json
    manifest-all.json
  resultado.json
```

`respuesta-v-mock.json` solo sirve al modo offline; no se incluye en la solicitud al
proveedor. Su fixture se construye independientemente de la salida guardada de A.
Para una prueba mock usa otro destino, omite `--mode real` y
`--autorizar-v-real`; el modo predeterminado continúa siendo mock.

## Validación de implementación

Las pruebas bloquean conexiones externas y sustituyen el transporte de OpenAI.
Comprueban ejecución completa y recuperación sin duplicaciones, separación A/V,
consentimiento específico por operación, rechazo de documentos modificados y
consentimiento ausente, cero reintentos personales, detección de cambios en A/V/B,
recomputación de decisiones, preservación de los bytes de A y localización literal
sin conjeturas ni modificaciones de evidencia.

Esta implementación no ha ejecutado V real desde el entorno en la nube. La A real
que ya existe está en el equipo del usuario; la prueba real pendiente se realiza
con los comandos anteriores en ese equipo. No se suben claves ni laboratorios a Git.

Comprobaciones de esta entrega: **311 pruebas aprobadas y 1 omitida** por ausencia
del estudio local ignorado. Ruff, formato, mypy, construcción sdist/wheel y
`pip check` aprobados. Se añadieron 13 casos de prueba para el recorrido completo,
consentimientos, integridad y localización de citas.
