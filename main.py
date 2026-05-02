#!/usr/bin/env python3
"""
main.py — FastAPI application for the NEREIDAS+ real-time dashboard.
"""

import os
import json
from pathlib import Path
from datetime import datetime
import math
import io
import zipfile

import pandas as pd


def _clean_json(obj):
    """Recursively replace NaN/Inf with None for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse, Response
from apscheduler.schedulers.background import BackgroundScheduler

from scraper import download_latest
from pipeline import run_pipeline

import sys
from pathlib import Path
_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))
from data_store import (
    get_cached_df, get_available_date_range, build_cache,
    CACHE_DIR, invalidate_memory_cache,
)
from analysis_core import (
    compute_source_apportionment, compute_np_ratio,
    compute_crosscorr, compute_cq_analysis,
)

_script_dir = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NEREIDAS_DATA_DIR", str(_script_dir / "data")))
RESULTS_DIR = Path(os.environ.get("RESULTS_OUTPUT_DIR", str(_script_dir / "data")))
MASTER_JSON = RESULTS_DIR / "latest.json"
SCRAPER_INTERVAL_HOURS = int(os.environ.get("SCRAPER_INTERVAL_HOURS", "6"))

app = FastAPI(title="NEREIDAS+ AI Dashboard", version="1.0.0")

# Serve frontend static files
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


# ---------------------------------------------------------------------------
# Scheduled background tasks
# ---------------------------------------------------------------------------
def _scheduled_job():
    print(f"[scheduler] {datetime.now().isoformat()} — running scraper + pipeline")
    try:
        updated, msg = download_latest()
        print(f"[scheduler] scraper: {msg}")
        # Always re-run pipeline; scripts are idempotent and fast enough
        run_pipeline()
        invalidate_memory_cache()
    except Exception as e:
        print(f"[scheduler] ERROR: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(_scheduled_job, "interval", hours=SCRAPER_INTERVAL_HOURS, id="pipeline_job", replace_existing=True)
scheduler.start()


# ---------------------------------------------------------------------------
# Root → serve dashboard
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    index_path = Path(__file__).resolve().parent / "static" / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
@app.get("/api/status")
def api_status():
    """General status and last pipeline timestamp."""
    status = {
        "service": "NEREIDAS+ AI Dashboard",
        "time": datetime.now().isoformat(),
        "scheduler_interval_hours": SCRAPER_INTERVAL_HOURS,
        "last_pipeline": None,
        "excel_present": (DATA_DIR / "26.03.06-Registro_Ramblas_MARMENOR.xlsx").exists(),
        "master_json_present": MASTER_JSON.exists(),
        "scraper_meta": None,
    }
    if MASTER_JSON.exists():
        try:
            with open(MASTER_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            status["last_pipeline"] = data.get("pipeline_timestamp")
            status["errors_count"] = len(data.get("errors", []))
        except Exception:
            pass
    meta_path = DATA_DIR / "download_meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                status["scraper_meta"] = json.load(f)
        except Exception:
            pass
    return status


@app.get("/api/results")
def api_results():
    """Aggregated JSON with all 4 script outputs."""
    if not MASTER_JSON.exists():
        raise HTTPException(status_code=503, detail="No results available yet. Run the pipeline first.")
    with open(MASTER_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/images/{image_name}")
def api_image(image_name: str):
    """Serve generated figures (PNG or SVG)."""
    if ".." in image_name:
        raise HTTPException(status_code=400, detail="Image name not allowed")
    # Search in multiple directories
    search_dirs = [
        _script_dir / "conf_paper_scripts",
        RESULTS_DIR,
    ]
    for d in search_dirs:
        img_path = d / image_name
        if img_path.exists():
            ext = img_path.suffix.lower()
            media = "image/svg+xml" if ext == ".svg" else "image/png"
            return FileResponse(img_path, media_type=media)
    raise HTTPException(status_code=404, detail="Image not found")


@app.post("/api/trigger-update")
def api_trigger(background_tasks: BackgroundTasks, force: bool = False):
    """Trigger scraper + pipeline manually in the background."""
    def _task():
        updated, msg = download_latest()
        print(f"[trigger] scraper: {msg}")
        run_pipeline(force=force)
        invalidate_memory_cache()
    background_tasks.add_task(_task)
    return {"message": "Update running in the background. Check /api/status in a few minutes."}


@app.get("/api/map")
def api_map():
    """Serve the study area map figure."""
    map_paths = [
        _script_dir / "figs" / "map2.svg",
        _script_dir / "figs" / "mapa_muestreo_mar_menor.png",
    ]
    for mp in map_paths:
        if mp.exists():
            media = "image/svg+xml" if mp.suffix == ".svg" else "image/png"
            return FileResponse(mp, media_type=media)
    raise HTTPException(status_code=404, detail="Map figure not found")


@app.get("/api/figures")
def api_figures():
    """List available figures in the results directory."""
    results_figs = []
    script_outputs = _script_dir / "conf_paper_scripts"
    for d in [RESULTS_DIR, script_outputs]:
        if d.exists():
            for ext in ['*.svg', '*.png']:
                results_figs.extend([f.name for f in d.glob(ext) if f.stat().st_size > 0])
    figures = sorted(set(results_figs))
    return {"count": len(figures), "figures": figures}


# ---------------------------------------------------------------------------
# Interactive date-range endpoints
# ---------------------------------------------------------------------------
@app.get("/api/data-range")
def api_data_range():
    if not (CACHE_DIR / "nitratos.parquet").exists():
        raise HTTPException(status_code=503, detail="Cache not available. Run the pipeline first.")
    dr = get_available_date_range(CACHE_DIR)
    return {"start": dr["min"].isoformat(), "end": dr["max"].isoformat()}


@app.get("/api/section/01")
def api_section_01(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Source apportionment + N:P ratio for a date range."""
    if not (CACHE_DIR / "nitratos.parquet").exists():
        raise HTTPException(status_code=503, detail="Cache not available.")

    df_nitratos = get_cached_df("nitratos", CACHE_DIR)
    df_fosfatos = get_cached_df("fosfatos", CACHE_DIR)
    df_no3_diario = get_cached_df("nitratos_diario", CACHE_DIR)
    df_po4_diario = get_cached_df("fosfatos_diario", CACHE_DIR)

    import json as _json
    id_nombre_n = _json.load(open(CACHE_DIR / "id_nombre_n.json", encoding="utf-8"))
    id_nombre_f = _json.load(open(CACHE_DIR / "id_nombre_f.json", encoding="utf-8"))

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        df_nitratos = df_nitratos[(df_nitratos.index >= start) & (df_nitratos.index <= end)]
        df_fosfatos = df_fosfatos[(df_fosfatos.index >= start) & (df_fosfatos.index <= end)]
        df_no3_diario = df_no3_diario[(df_no3_diario.index >= start) & (df_no3_diario.index <= end)]
        df_po4_diario = df_po4_diario[(df_po4_diario.index >= start) & (df_po4_diario.index <= end)]

    apportion = compute_source_apportionment(df_no3_diario, df_po4_diario, id_nombre_n, id_nombre_f)
    np_res = compute_np_ratio(df_nitratos, df_fosfatos, id_nombre_n, id_nombre_f)

    return _clean_json({
        "tables": {**apportion["tables"], **np_res["tables"]},
        "plots": {
            "load_ranking": apportion["load_ranking_plot"],
            "np_boxplot": np_res["np_boxplot_plot"],
            "np_temporal": np_res["np_temporal_plot"],
        },
    })


@app.get("/api/section/02")
def api_section_02(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """Hydrological response: cross-correlation + C-Q analysis."""
    if not (CACHE_DIR / "saih_caudal.parquet").exists():
        raise HTTPException(status_code=503, detail="Cache not available.")

    caudal_df = get_cached_df("saih_caudal", CACHE_DIR)
    precip_df = get_cached_df("siam_precip", CACHE_DIR)
    df_nitratos = get_cached_df("nitratos", CACHE_DIR)
    df_fosfatos = get_cached_df("fosfatos", CACHE_DIR)
    df_caudal_xlsx = get_cached_df("caudal", CACHE_DIR)

    caudal_s = caudal_df.iloc[:, 0] if caudal_df.shape[1] == 1 else caudal_df["caudal_m3s"]
    precip_s = precip_df.iloc[:, 0] if precip_df.shape[1] == 1 else precip_df["precip_mm"]

    if start_date and end_date:
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        caudal_s = caudal_s[(caudal_s.index >= start) & (caudal_s.index <= end)]
        precip_s = precip_s[(precip_s.index >= start) & (precip_s.index <= end)]
        df_nitratos = df_nitratos[(df_nitratos.index >= start) & (df_nitratos.index <= end)]
        df_fosfatos = df_fosfatos[(df_fosfatos.index >= start) & (df_fosfatos.index <= end)]
        df_caudal_xlsx = df_caudal_xlsx[(df_caudal_xlsx.index >= start) & (df_caudal_xlsx.index <= end)]

    crosscorr = compute_crosscorr(precip_s, caudal_s)
    res_no3 = compute_cq_analysis(df_caudal_xlsx, df_nitratos, "2", "2", "NO3")
    res_po4 = compute_cq_analysis(df_caudal_xlsx, df_fosfatos, "2", "2", "PO4")

    tables = {
        "crosscorr": {
            "lag_optimo_dias": crosscorr["lag_optimo_dias"],
            "corr_maxima": crosscorr["corr_maxima"],
        },
        "cq_analysis": {
            "no3": {
                "slope_b": res_no3["slope_b"] if res_no3 else None,
                "r2": res_no3["r2"] if res_no3 else None,
                "p_value": res_no3["p_value"] if res_no3 else None,
                "behaviour": res_no3["behaviour"] if res_no3 else None,
                "n_samples": res_no3["n_samples"] if res_no3 else None,
            },
            "po4": {
                "slope_b": res_po4["slope_b"] if res_po4 else None,
                "r2": res_po4["r2"] if res_po4 else None,
                "p_value": res_po4["p_value"] if res_po4 else None,
                "behaviour": res_po4["behaviour"] if res_po4 else None,
                "n_samples": res_po4["n_samples"] if res_po4 else None,
            },
        },
    }

    return _clean_json({
        "tables": tables,
        "plots": {
            "crosscorr": {
                "lags": crosscorr["lags"],
                "correlations": crosscorr["correlations"],
                "lag_optimo": crosscorr["lag_optimo_dias"],
                "corr_maxima": crosscorr["corr_maxima"],
            },
            "cq_scatter": {
                "no3": res_no3 if res_no3 else None,
                "po4": res_po4 if res_po4 else None,
            },
        },
    })


# ---------------------------------------------------------------------------
# Latest records
# ---------------------------------------------------------------------------
@app.get("/api/latest-records")
def api_latest_records():
    if not (CACHE_DIR / "nitratos.parquet").exists():
        raise HTTPException(status_code=503, detail="Cache not available.")

    df_n = get_cached_df("nitratos", CACHE_DIR)
    df_f = get_cached_df("fosfatos", CACHE_DIR)
    df_c = get_cached_df("caudal", CACHE_DIR)

    s_n = df_n.get("2", pd.Series(dtype=float))
    s_f = df_f.get("2", pd.Series(dtype=float))
    s_c = df_c.get("2", pd.Series(dtype=float))

    s_n = s_n[~s_n.index.duplicated(keep="first")]
    s_f = s_f[~s_f.index.duplicated(keep="first")]
    s_c = s_c[~s_c.index.duplicated(keep="first")]

    df_aligned = pd.DataFrame({
        "no3": s_n,
        "po4": s_f,
        "caudal": s_c,
    }).sort_index()

    df_aligned = df_aligned.dropna(how="all").tail(5)
    records = []
    for idx, row in df_aligned.iterrows():
        records.append({
            "date": idx.strftime("%Y-%m-%d"),
            "no3": float(row["no3"]) if pd.notna(row["no3"]) else None,
            "po4": float(row["po4"]) if pd.notna(row["po4"]) else None,
            "caudal": float(row["caudal"]) if pd.notna(row["caudal"]) else None,
        })
    return {"records": list(reversed(records))}


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------
@app.get("/api/download/figures")
def api_download_figures():
    results_figs = []
    script_outputs = _script_dir / "conf_paper_scripts"
    for d in [RESULTS_DIR, script_outputs]:
        if d.exists():
            for ext in ['*.svg', '*.png']:
                results_figs.extend([f for f in d.glob(ext) if f.stat().st_size > 0])
    if not results_figs:
        raise HTTPException(status_code=404, detail="No figures found.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in results_figs:
            zf.write(f, f.name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=figures.zip"},
    )


@app.get("/api/download/metrics")
def api_download_metrics():
    if not MASTER_JSON.exists():
        raise HTTPException(status_code=503, detail="No results available yet.")
    with open(MASTER_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for script_key in ["03_lstm_gru_forecast"]:
        script_data = data.get("scripts", {}).get(script_key, {})
        metrics = script_data.get("metrics", [])
        for m in metrics:
            rows.append({
                "family": "LSTM/GRU",
                "model": m.get("Model", m.get("Modelo", "")),
                "MAE": m.get("MAE", ""),
                "RMSE": m.get("RMSE", ""),
                "MAPE_pct": m.get("MAPE", m.get("MAPE (%)", "")),
                "CVRMSE_pct": m.get("CVRMSE", m.get("CVRMSE (%)", "")),
            })
    if not rows:
        raise HTTPException(status_code=404, detail="Metrics not found.")
    df_metrics = pd.DataFrame(rows)
    csv_buf = io.StringIO()
    df_metrics.to_csv(csv_buf, index=False)
    return Response(
        csv_buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=forecast_metrics.csv"},
    )


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}
