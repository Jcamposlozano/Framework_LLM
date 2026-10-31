# Verificación técnica de fase 2

Fecha: 19 de octubre de 2026. Entorno comprobado: macOS, Python 3.13.12, Pydantic 2.14.1. El paquete declara Python ≥3.11; no se ejecutó una matriz de intérpretes.

| Comprobación ejecutada | Resultado |
|---|---|
| Batería completa contra el paquete 0.2.0 instalado desde wheel | 181 pruebas correctas, sin advertencias de pruebas |
| Pruebas nuevas de fase 2 | 48 correctas; sin conexiones externas |
| `ruff check .` | Sin hallazgos |
| `ruff format --check .` | 74 archivos conformes |
| `mypy` estricto | Sin errores en 31 archivos de biblioteca y ejemplos |
| `git diff --check` | Sin errores de espacios |
| `python -m build --no-isolation` | sdist y wheel construidos; wheel desde sdist |
| Instalación local de wheel 0.2.0 | Correcta |
| `pip check` | Sin requisitos rotos |
| CLI genérica mock y reanudación | Correctas; mismo run_id y artefactos conservados |
| Preparación y ejecución por etapas en `mi_estudio_001` | Lectura, comparación y reconciliación persistidas |
| Seguimiento de `demo-v1` | Una discrepancia; seis revisiones humanas; integridad correcta |

Las 133 pruebas preexistentes permanecen correctas. Se conservaron los cambios locales previos a la implementación.

## Cobertura

`tests/test_phase2.py` cubre propuestas para exacerbación actual, previa, negación, síntomas insuficientes, fecha explícita, ambigüedad, consulta sin inferencia de inicio y contradicciones entre secciones. Son respuestas **simuladas**: se verifica el procedimiento, no la capacidad clínica de un modelo.

También comprueba citas inexistentes, offsets y secciones, diferencias y acuerdos sin evidencia, errores técnicos, JSON inválido, inmutabilidad de A, separación de metadatos, ausencia de A en la interfaz, permisos de almacenamiento, reanudación, detección de cambios y manipulación, políticas aprobadas/no aprobadas, normalización autorizada, las cuatro decisiones, reglas externas de consistencia y repetibilidad del comparador.

`tests/test_phase2_openai_cli.py` usa transporte HTTP falso para comprobar selección de modelo, esquema estricto, parámetros, tokens, id de respuesta, reintentos por límites, agotamiento del presupuesto, respuestas incompletas, bloqueo de llamadas reales no autorizadas y vinculación de gobierno de datos al documento.

`tests/test_phase2_laboratorio.py` crea laboratorios inventados para comprobar conservación del corpus y las siete etapas, diccionario propio, reglas como avisos, progreso por procedimientos, conversión explícita de booleanos, archivo A original conservado byte por byte, campos auxiliares y versiones nuevas al cambiar la especificación.

## Límites y decisiones pendientes

- No se hicieron llamadas reales a OpenAI ni se verificó acceso de una cuenta a un modelo. La disponibilidad se comprueba al activar el modo real autorizado.
- El adaptador real se verificó mediante un transporte falso, no con la API en vivo. La documentación oficial se consultó para seleccionar un modelo documentado y construir la solicitud.
- Los costos permanecen null: no hay tabla de precios verificable y versionada incorporada.
- El reconciliador es determinista. La configuración independiente de un modelo asesor queda registrada, pero no se invoca ese modelo.
- No se implementó un extractor inicial, ni estadísticas, PGEC o calibración. Se importa A de un extractor externo.
- El diccionario del estudio, las reglas temporales y las reglas de reemplazo siguen pendientes de aprobación clínica.
- La comprobación inicial disponía de ocho documentos. El corpus activo posterior contiene 5.924 notas importadas desde Excel y sigue sin ejecuciones de modelos; su importación no acredita anonimización de la narrativa.
- El gobierno de datos se representa como una declaración explícita vinculada por hash. Su autenticidad institucional requiere verificación fuera del software.
- Los hashes detectan cambios respecto de los manifiestos; no constituyen firmas digitales ni certifican corrección clínica. Se requiere control de acceso del responsable del laboratorio.

La demostración documenta funcionamiento técnico. No demuestra que B sea más exacta que A y no sustituye la evaluación contra referencia experta.

## Ampliación: corpus XLSX

La importación Excel añade once pruebas sintéticas: **192 pruebas totales correctas**, sin advertencias; Ruff sin hallazgos y 79 archivos conformes; mypy sin errores en 31 archivos. Se reconstruyeron sdist/wheel y se instaló el wheel; `pip check` no encontró requisitos rotos.

Se verificó localmente el corpus completo de `mi_estudio_001`: 5.924 textos y fechas de atención coinciden con las celdas del Excel; los document_id son únicos. Se omitieron 136 filas totalmente vacías. El Excel conservó su hash. Esta comprobación de fidelidad de importación no es una evaluación clínica ni ejecutó un modelo. La carga anterior conservaba informe y correspondencia, pero su JSON documental estaba ausente: se respaldaron los archivos disponibles.

## Auditoría e integración posterior

La auditoría posterior se documenta en [phase2-audit.md](phase2-audit.md). La línea base de esta revisión fue de 192 pruebas correctas; después de añadir cinco casos y reforzar la comprobación de trazabilidad de importación, pasan 197 pruebas. Se reprodujeron y corrigieron defectos de vinculación de fuentes, seguimiento de enlaces y referencias de esquema/configuración. El diseño incorpora datos del verificador existente como candidato técnico; no se validó científicamente ni se creó un extractor LLM clínico.
