# NEREIDAS+ AI Dashboard (FastAPI)

Servicio web autocontenido para consultar en tiempo real los resultados del paper *AI4Nature@AVSS2026* (*"Spatio-Temporal Characterization of Nutrient Loading in Mar Menor..."*). Descarga periódicamente el Excel de aforos del Canal Mar Menor, re-ejecuta el pipeline de análisis y publica métricas, tablas y figuras a través de una API REST y un dashboard HTML/JS.

---

## Arquitectura

| Componente | Función |
|------------|---------|
| `scraper.py` | Descarga el Excel de aforos desde el portal del Canal Mar Menor (`canalmarmenor.carm.es`). Compara hashes y solo reemplaza el fichero si ha cambiado; admite una URL directa de respaldo (`FALLBACK_EXCEL_URL`). |
| `pipeline.py` | Ejecuta secuencialmente los scripts de reproducibilidad `01`–`03` del repo `MM-NET-Mar-Menor-Nutrient-Estimation-AI4NATURE/` y agrega sus `results_0X.json` en un único `data/latest.json`. También dispara la construcción de la caché interactiva. |
| `data_store.py` | Construye y sirve una caché Parquet (`data/cache/`) de las series (nitratos, fosfatos, caudal SAIH, precipitación SIAM) para las consultas interactivas por rango de fechas. |
| `analysis_core.py` | Recalcula sobre la marcha el reparto de fuentes, el ratio N:P, la correlación cruzada y el análisis C–Q para el rango de fechas solicitado. |
| `generate_map.py` | Genera el mapa del área de estudio (Mar Menor + cuenca del Albujón) con los puntos de muestreo. |
| `main.py` | Aplicación FastAPI: sirve el frontend y expone los endpoints REST. |
| APScheduler | Lanza `scraper` + `pipeline` cada 6 h (configurable vía `SCRAPER_INTERVAL_HOURS`). |
| `static/` | Dashboard HTML/CSS/JS vanilla (Plotly vía CDN), sin frameworks de frontend. |

> **Nota sobre los scripts de análisis:** `pipeline.py` espera encontrar el repo de reproducibilidad en `MM-NET-Mar-Menor-Nutrient-Estimation-AI4NATURE/` *dentro* de este directorio (clónalo o enlázalo ahí) para poder recalcular los resultados en vivo. Si no está presente, el dashboard sigue funcionando con los `results_0X.json`, figuras y caché ya incluidos en `data/`.

---

## Puesta en marcha (desarrollo / local)

Todo —código, datos y entorno virtual— vive dentro de este directorio. El script `run_dev.sh` crea el `.venv`, instala dependencias y arranca el servidor:

```bash
cd /home/aurorax/Git_repos/MM-NET/MM-NET-Mar-Menor-Nutrient-Estimation-Tool
./run_dev.sh
```

Esto:
- Crea `.venv/` la primera vez e instala `requirements.txt` (Python 3.12 + FastAPI + TensorFlow + scikit-learn + pandas, en CPU).
- Exporta `NEREIDAS_DATA_DIR` y `RESULTS_OUTPUT_DIR` apuntando a `./data`.
- Lanza `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`.

Arranque manual equivalente (con el venv ya activo):

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Acceder

- **Dashboard:** http://localhost:8000/
- **API docs (Swagger):** http://localhost:8000/docs
- **Health:** http://localhost:8000/health

### Actualización manual

Para forzar una descarga + re-ejecución sin esperar al planificador:

```bash
curl -X POST http://localhost:8000/api/trigger-update
```

Desde el dashboard, el botón *"Update now"* hace lo mismo.

> **Primer arranque:** el pipeline puede tardar varios minutos la primera vez (entrenamiento LSTM/GRU). TensorFlow corre en CPU; no se requiere GPU.

> **Producción:** coloca un reverse proxy (Nginx o Traefik) delante de uvicorn para terminar TLS con tu dominio.

---

## Configuración por variables de entorno

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `NEREIDAS_DATA_DIR` | `./data` | Ruta del Excel, los datos de SAIH/SIAM y la caché. |
| `RESULTS_OUTPUT_DIR` | `./data` | Donde se escriben `latest.json` y los JSON agregados. |
| `SCRAPER_INTERVAL_HOURS` | `6` | Frecuencia de chequeo del Excel, en horas. |
| `FALLBACK_EXCEL_URL` | *(vacío)* | URL directa al Excel si el scraper no logra localizar el enlace en el portal. |

---

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/health` | Healthcheck |
| GET | `/api/status` | Estado del servicio, última ejecución del pipeline y metadatos del scraper |
| GET | `/api/results` | JSON agregado (`latest.json`) con la salida de los scripts |
| GET | `/api/figures` | Lista de figuras disponibles (SVG/PNG) |
| GET | `/api/images/{name}` | Sirve una figura concreta |
| GET | `/api/map` | Figura del mapa del área de estudio |
| GET | `/api/data-range` | Rango de fechas disponible en la caché |
| GET | `/api/section/01` | Reparto de fuentes + ratio N:P (parámetros `start_date`, `end_date`) |
| GET | `/api/section/02` | Respuesta hidrológica: correlación cruzada + análisis C–Q (`start_date`, `end_date`) |
| GET | `/api/latest-records` | Últimos registros en el punto Albujón (Pt. 2) |
| POST | `/api/trigger-update` | Fuerza la ejecución de scraper + pipeline en segundo plano |
| GET | `/api/download/figures` | Descarga todas las figuras en un ZIP |
| GET | `/api/download/metrics` | Descarga las métricas de forecasting en CSV |

---

## Fuentes de datos

Tres redes de monitorización independientes, coherentes con el manuscrito:

- **Ramblas MARMENOR (IMIDA/DGMM):** muestras semanales de concentración de NO₃ y PO₄ y estimaciones de caudal en los puntos de control.
- **SAIH–CHS:** caudal, precipitación y nivel a resolución de 5 min en las estaciones de aforo de la cuenca.
- **SIAM:** precipitación diaria de cinco estaciones (CA12, CA73, TP22, TP42, TP91), 2016 a 2026, usada como registro de precipitación en los modelos de forecasting.
