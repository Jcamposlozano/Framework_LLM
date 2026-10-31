# Ejemplo sintético de fase 2

`input.json` contiene un documento inventado y A. `mock_verification.json` es la respuesta programada del verificador. `output.json` muestra B obtenida con la política conservadora; conserva A y solicita revisión.

Desde la raíz del repositorio:

```bash
.venv/bin/extracteval verify --config configs/epoc/phase2.json \
  --input examples/phase2/input.json --output /tmp/extracteval-demo --mode mock
```

Los identificadores y tiempos cambian entre ejecuciones nuevas. Reanudar el mismo directorio conserva los artefactos. El comparador es determinista para entradas idénticas. No hay métricas de exactitud ni referencia experta en este ejemplo.

Para trabajar con el estudio, usa [la guía del laboratorio](../../docs/fase2-verificacion-laboratorio.md).
