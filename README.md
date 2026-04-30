# NEREIDAS+ AI Dashboard (FastAPI + Docker)

Servicio web autocontenido para consultar en tiempo real los resultados del paper *AI4Nature@AVSS2026*. Se actualiza automáticamente descargando el Excel de aforos del Canal Mar Menor y re-ejecutando el pipeline de análisis.

---

## Arquitectura

| Componente | Función |
|------------|---------|
| `scraper.py` | Descarga el Excel de la web del Canal Mar Menor si ha cambiado. |
| `pipeline.py` | Ejecuta secuencialmente los 4 scripts de `paper_results_scripts/`. |
| `main.py` | FastAPI: sirve el frontend y expone endpoints REST. |
| APScheduler | Lanza scraper + pipeline cada 6 horas (configurable). |
| `static/` | Dashboard HTML/CSS/JS vanilla, sin frameworks de frontend. |

---

## Despliegue con Docker Compose

### 1. Requisitos previos
- Docker & Docker Compose instalados.
- Puerto 8000 libre en el servidor.
- (Opcional) Un dominio apuntando a la IP del servidor.

### 2. Construir y levantar

Desde la raíz del repositorio:

```bash
cd /home/aurorax/Git_repos/blueAI-alfred   # o la ruta donde clonaste
sudo docker compose up -d --build
```

Esto:
- Construye la imagen con Python 3.12 + TensorFlow + LightGBM + XGBoost + FastAPI.
- Monta `NEREIDAS+/` como volumen para acceso a los datos crudos (SAIH, SIAM, Excel).
- Persiste resultados generados en `web_service/data/`.

### 3. Acceder

- **Dashboard:** http://localhost:8000/
- **API docs:** http://localhost:8000/docs
- **Health:** http://localhost:8000/health

### 4. Actualización manual

Si sabes que el Excel se ha actualizado y no quieres esperar al cron:

```bash
curl -X POST http://localhost:8000/api/trigger-update
```

Desde el dashboard hay un botón *"Actualizar ahora"* que hace lo mismo.

---

## Configuración por variables de entorno

Edita `docker-compose.yml` si necesitas cambiar:

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `NEREIDAS_DATA_DIR` | `/data/NEREIDAS+` | Ruta donde está el Excel y los CSVs de SAIH/SIAM. |
| `RESULTS_OUTPUT_DIR` | `/data/results` | Donde se escriben los JSONs agregados. |
| `SCRAPER_INTERVAL_HOURS` | `6` | Frecuencia de chequeo del Excel en horas. |
| `FALLBACK_EXCEL_URL` | — | Si el scraper no puede parsear el portal, usa esta URL directa. |

---

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/api/status` | Estado del servicio y última ejecución |
| GET | `/api/results` | JSON agregado con métricas de los 4 scripts |
| GET | `/api/figures` | Lista de PNGs generados |
| GET | `/api/images/{name}` | Sirve una figura PNG |
| POST | `/api/trigger-update` | Fuerza ejecución de scraper + pipeline |

---

## Notas importantes

- **Primer arranque:** El pipeline puede tardar varios minutos la primera vez (entrenamiento LSTM/GRU + LightGBM).
- **GPU:** La imagen no usa GPU. TensorFlow corre en CPU. Si tienes CUDA disponible en el servidor, puedes cambiar la base del Dockerfile a una imagen con soporte GPU.
- **SSL/TLS:** En producción público, coloca Nginx o Traefik delante del contenedor (reverse proxy) para terminar SSL con tu dominio.
