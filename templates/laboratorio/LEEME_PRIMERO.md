# Laboratorio nuevo: empieza aquí

Esta estructura está vacía de documentos, anotaciones, ejecuciones y resultados científicos. Las carpetas organizan las siete etapas metodológicas; no son siete programas ejecutables. Crear el laboratorio no ejecuta ninguna etapa.

## Tus primeras acciones

1. Completa `control/alcance.md`: pregunta, propósito, población y responsables.
2. Prepara tu diccionario en `01_especificacion/diccionario_variables.csv`.
3. Conserva tus textos pseudonimizados en `datos/documentos/documentos.jsonl`, o registra referencias seguras en el inventario.
4. Escribe las instrucciones en `01_especificacion/prompts/extractor_v1.txt` y, si procede, `verificador_v1.txt`.
5. Completa diseño y particiones en `02_diseno/` antes de utilizar la evaluación final.
6. Entrega a cada evaluador su material de anotación y diccionario sin las salidas de A/B.
7. Registra actividades en `control/lista_chequeo.csv` y el estado de cada etapa en `control/estado_etapas.csv`.

Los archivos `.borrador.json` son formularios pendientes con campos nulos. No son configuraciones ejecutables ni contratos Pydantic válidos. Hay que completarlos y convertirlos al contrato correspondiente antes de usarlos. Los CSV son plantillas humanas con encabezados; no se importan automáticamente. Los JSONL vacíos contienen cero registros, no un resultado vacío de un experimento ya ejecutado.

## Dónde va cada cosa

| Material | Ubicación |
|---|---|
| Texto documental | `datos/documentos/documentos.jsonl` |
| Inventario, fuente y agrupación documental | `datos/documentos/inventario_documentos.csv` |
| Diccionario operacional | `01_especificacion/diccionario_variables.csv` |
| Instrucciones del extractor y verificador | `01_especificacion/prompts/` |
| Definición del experimento | `configuraciones/experimento.borrador.json` |
| Muestreo y particiones | `02_diseno/` |
| Plan de repeticiones y variantes de prompt | `03_estabilidad/` |
| Anotaciones originales | `04_referencia/evaluador_01/` y `evaluador_02/` |
| Adjudicación y motivos | `04_referencia/adjudicacion/` |
| Salidas originales por configuración/ejecución | `ejecuciones/A/` y `ejecuciones/B/` |
| Revisión humana operativa | `ejecuciones/revision_operativa/` |
| PGEC y comparación estadística | `05_validez/` |
| Taxonomía y señales | `06_calidad/` |
| Fiabilidad, calibración y política de uso | `07_fiabilidad/` |
| Estado del trabajo y evidencias de cierre | `control/` |

Si usas CSV para anotación, conserva ese archivo como fuente y registra una conversión posterior a JSONL si la necesitas. No mantengas dos versiones editables de la misma anotación sin establecer cuál es la fuente. El CSV de adjudicación incluye razones porque el contrato actual de referencia no tiene un campo específico para ellas.

## Cómo actualizar el tablero

En los CSV utiliza exactamente estos estados:

- `pendiente`: aún no se ha iniciado.
- `en_curso`: un responsable declara que está trabajando en la actividad.
- `bloqueado`: falta una entrada, decisión, recurso o implementación; explica el motivo.
- `completado`: existe el producto, satisface el criterio y fue revisado.
- `no_aplica`: exclusión justificada; no equivale a evidencia obtenida.

Para una actividad cambia su fila en `control/lista_chequeo.csv`: estado, responsable, fecha, evidencia_real y observaciones. Para una etapa cambia `control/estado_etapas.csv`: estado, fechas, resultado_obtenido, ruta_evidencia y validado_por. Las rutas de evidencia son relativas a esta carpeta y deben apuntar a un archivo concreto. Usa un informe de cierre cuando el producto tenga varios archivos.

Un piloto puede delimitar un alcance menor con justificación, pero no debe presentarse como evaluación completa de las siete etapas.

No marques «completado» por haber creado una carpeta, redactado un plan o rellenado un encabezado. Si declaras `no_aplica`, justifica en `observaciones` de la actividad o `justificacion` de la etapa.

Desde la carpeta del framework consulta el tablero con:

```sh
.venv/bin/python scripts/laboratorio.py estado --laboratorio /ruta/a/este/laboratorio
```

Sustituye la ruta por la de tu laboratorio. La consulta no ejecuta modelos ni detecta trabajos de fondo: lee el estado que registraste. Advierte sobre algunas inconsistencias de control, pero no puede certificar la calidad científica de un informe.

## Alcance real del software

`extracteval` 0.1.0 aporta contratos, validación básica, referencias expertas, configuraciones/manifiestos y mocks. No contiene todavía extracción real, repeticiones experimentales, métricas, muestreo, calibración ni persistencia automática. El organizador de carpetas no añade esas capacidades.

La Fase 1 de desarrollo del software no equivale a la Etapa 1 metodológica completada. Puede haber trabajo metodológico manual aunque su automatización esté pendiente.

No escribas probabilidades, PGEC o intervalos ficticios para completar plantillas. Deja vacíos los resultados no obtenidos. Reserva las etiquetas finales y no uses acuerdos entre agentes como referencia experta. Los controles de acceso y el cegamiento requieren un procedimiento real; las carpetas no los garantizan.

## Siguiente lectura

En el repositorio del framework consulta `docs/crear-y-dirigir-un-laboratorio.md`, que explica las siete etapas, los productos y el procedimiento completo. `control/fuente_metodologica.json` identifica el PDF utilizado como referencia de esta plantilla. `control/creacion.json` registra solamente la creación de la estructura, no un manifiesto de experimento.
