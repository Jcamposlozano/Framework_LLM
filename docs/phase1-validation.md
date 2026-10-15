# Verificación de la Fase 1

Fecha: 2026-10-15. Plataforma comprobada: macOS arm64, Python 3.13.12, Pydantic 2.14.1. Python >=3.11 está declarado; no se ha ejecutado aún una matriz de intérpretes 3.11/3.12.

## Resultados

| Comprobación | Resultado |
|---|---|
| `pytest -q`, instalación editable | 72 pruebas correctas |
| `ruff check .` | Sin hallazgos |
| `ruff format --check .` | 23 archivos Python conformes |
| `mypy` en modo estricto | Sin errores en 15 archivos de biblioteca y ejemplo |
| `python examples/minimal.py` | Ejecución sintética correcta |
| `python -m build --no-isolation` | sdist y wheel correctos; wheel construido desde sdist |
| Instalación del wheel en venv nuevo | Correcta, sin instalación editable ni paquetes globales |
| Importación externa con `python -I` | Ruta comprobada dentro de site-packages del venv nuevo |
| `pip check` en venv nuevo | Sin dependencias rotas |
| Pruebas copiadas fuera del repositorio contra el wheel | 72 pruebas correctas |
| Ejemplo copiado fuera del repositorio | Ejecución correcta contra el wheel instalado |

Los artefactos generados son `dist/extracteval-0.1.0.tar.gz` y `dist/extracteval-0.1.0-py3-none-any.whl`. No se publicaron en un índice de paquetes.

## Cobertura funcional

- Separación de valor, operación, evidencia, abstención y error técnico.
- Categoría `indeterminado` como valor semántico válido, sin abstención implícita.
- Tipos categórico, booleano, numérico, fecha y texto; coerciones incorrectas rechazadas.
- Validación estructural y comprobación explícita del diccionario.
- Ida y vuelta de documentos, diccionarios, resultados, respuestas, referencias y manifiestos.
- Uso del mismo consumidor con dos implementaciones del protocolo de modelo.
- Parámetros no soportados, respuesta estructurada, fallos simulados y errores sin contenido de entrada.
- Huellas estables y sensibles a versiones, referencias de configuración y separación de identificadores internos/externos.
- Modelos distintos para extractor y verificador; limitaciones de reproducibilidad y versión desconocida.
- Adjudicación coherente y rechazo de anotaciones de distintas particiones o documentos.
- Contratos utilizables en proceso separado con importaciones de adaptadores bloqueadas.
- Guardas de importación: núcleo limitado a biblioteca estándar, Pydantic y sus propios contratos.
- Única dependencia directa de ejecución: Pydantic.

Las pruebas unitarias bloquean las conexiones de sockets en su proceso. No se realizaron llamadas a proveedores, experimentos clínicos ni operaciones sobre repositorios externos. Los datos de prueba son sintéticos.

## Límites

La validación de referencias cruzadas es explícita; construir un resultado no carga automáticamente el diccionario ni la configuración. Los contratos de repositorio no implementan todavía persistencia. Las particiones declaradas no garantizan por sí solas separación por entidad. El archivo de requisitos fijados documenta el entorno comprobado, sin hashes ni promesa de resolución idéntica en todas las plataformas.

No se han implementado componentes de la Fase 2, métricas estadísticas ni calibración.
