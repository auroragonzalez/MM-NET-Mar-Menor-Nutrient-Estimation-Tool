#!/usr/bin/env python3
"""
pipeline.py

Orchestrates the 4 paper_results_scripts sequentially and collects their JSON
outputs into a single aggregated results file.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

_repo_root = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("NEREIDAS_DATA_DIR", str(_repo_root / "NEREIDAS+")))
RESULTS_DIR = Path(os.environ.get("RESULTS_OUTPUT_DIR", str(_repo_root / "web_service" / "data")))
REPO_ROOT = Path(__file__).resolve().parent.parent

# Scripts to run in order
SCRIPTS = [
    REPO_ROOT / "paper_results_scripts" / "01_source_apportionment.py",
    REPO_ROOT / "paper_results_scripts" / "02_hydrological_response.py",
    REPO_ROOT / "paper_results_scripts" / "03_lstm_gru_forecast.py",
    REPO_ROOT / "paper_results_scripts" / "04_gradient_boosting_benchmark.py",
]


def run_pipeline(force: bool = False) -> dict:
    start = time.time()
    logs = []
    errors = []

    print(f"[pipeline] Iniciando pipeline en {datetime.now().isoformat()}")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Build interactive cache (Parquet + JSON sidecars)
    try:
        import sys
        _repo = Path(__file__).resolve().parent.parent
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        from web_service.data_store import build_cache, invalidate_memory_cache
        from web_service.data_store import CACHE_DIR as _CACHE_DIR
        build_cache(DATA_DIR, _CACHE_DIR)
        invalidate_memory_cache()
        print("[pipeline] Cache built")
    except Exception as e:
        errors.append(f"Cache build failed: {e}")
        print(f"[pipeline] WARNING: cache build failed: {e}")

    for script in SCRIPTS:
        if not script.exists():
            errors.append(f"Script no encontrado: {script}")
            continue
        print(f"[pipeline] Ejecutando {script.name} ...")
        try:
            env = os.environ.copy()
            env["NEREIDAS_DATA_DIR"] = str(DATA_DIR)
            env["RESULTS_OUTPUT_DIR"] = str(RESULTS_DIR)
            # Ensure python uses the same interpreter
            proc = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True,
                text=True,
                timeout=1800,
                env=env,
                cwd=str(REPO_ROOT),
            )
            logs.append({"script": script.name, "rc": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-1000:]})
            if proc.returncode != 0:
                errors.append(f"{script.name} falló (rc={proc.returncode}): {proc.stderr[-500:]}")
            else:
                print(f"[pipeline] {script.name} OK")
        except Exception as e:
            errors.append(f"{script.name} excepción: {e}")

    # Collect individual JSONs
    aggregated = {
        "pipeline_timestamp": datetime.now().isoformat(),
        "duration_sec": round(time.time() - start, 1),
        "errors": errors,
        "scripts": {},
    }

    for script in SCRIPTS:
        result_file = RESULTS_DIR / f"results_{script.stem.split('_')[0]}.json"
        if result_file.exists():
            try:
                with open(result_file, "r", encoding="utf-8") as f:
                    aggregated["scripts"][script.stem] = json.load(f)
            except Exception as e:
                aggregated["errors"].append(f"Error leyendo {result_file}: {e}")
        else:
            aggregated["errors"].append(f"No se generó {result_file}")

    # Write master JSON
    master_path = RESULTS_DIR / "latest.json"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2, default=str)

    print(f"[pipeline] Completado en {aggregated['duration_sec']}s. Master: {master_path}")
    return aggregated


if __name__ == "__main__":
    run_pipeline(force=True)
