#!/usr/bin/env python3
"""
data_store.py — Build and maintain a Parquet cache of all raw time-series
so the backend can filter by date range without re-reading Excel/CSVs.
"""

import json
import os
from pathlib import Path
import pandas as pd

_script_dir = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NEREIDAS_DATA_DIR", str(_script_dir / "data")))
RESULTS_DIR = Path(os.environ.get("RESULTS_OUTPUT_DIR", str(_script_dir / "data")))
CACHE_DIR = RESULTS_DIR / "cache"
EXCEL_PATH = DATA_DIR / "26.03.06-Registro_Ramblas_MARMENOR.xlsx"

# In-memory cache: source_name -> DataFrame
_memory_cache = {}


def _leer_hoja_excel(path, hoja):
    """Same loader used by paper_results_scripts."""
    df_raw = pd.read_excel(path, sheet_name=hoja, header=None)
    ids = df_raw.iloc[5, 2:].tolist()
    nombres = df_raw.iloc[6, 2:].tolist()
    id_nombre = {str(pid): str(pn) for pid, pn in zip(ids, nombres)
                 if pd.notna(pid) and pd.notna(pn)}
    datos = df_raw.iloc[8:, 1:].copy()
    col_names = ['Fecha'] + [str(x) for x in df_raw.iloc[5, 2:].tolist()]
    datos.columns = col_names[:datos.shape[1]]
    datos = datos.loc[:, ~datos.columns.duplicated()]
    datos['Fecha'] = pd.to_datetime(datos['Fecha'], errors='coerce')
    datos = datos.dropna(subset=['Fecha']).set_index('Fecha')
    for col in datos.columns:
        try:
            datos[col] = pd.to_numeric(datos[col], errors='coerce')
        except Exception:
            pass
    return datos.dropna(axis=1, how='all'), id_nombre


def _load_saih_streamflow(fpath):
    """Load Albujón streamflow and resample to daily mean."""
    try:
        df = pd.read_csv(fpath, sep=';', header=5)
        df.columns = df.columns.str.strip()
        df['datetime'] = pd.to_datetime(
            df['Date'].astype(str) + ' ' + df['Time'].astype(str), errors='coerce')
        df = df.dropna(subset=['datetime']).set_index('datetime')
        val_col = [c for c in df.columns if 'streamflow' in c.lower() or 'caudal' in c.lower()]
        if not val_col:
            val_col = [c for c in df.columns if c not in ['Date', 'Time']]
        if not val_col:
            return pd.Series(dtype=float, name='caudal_m3s')
        s = pd.to_numeric(df[val_col[0]], errors='coerce')
        return s.resample('D').mean().rename('caudal_m3s')
    except Exception as e:
        print(f"  ⚠ Error SAIH {fpath}: {e}")
        return pd.Series(dtype=float, name='caudal_m3s')


def _load_siam_precip(siam_dir):
    """Load all SIAM stations and return regional daily mean precipitation."""
    stations = ['CA12', 'CA73', 'TP22', 'TP42', 'TP91']
    precip_list = []
    for code in stations:
        s_all = []
        for subdir in ['datosSIAM2016-2022', 'datosSIAM2023-']:
            if subdir == 'datosSIAM2016-2022':
                files = [
                    siam_dir / subdir / f'{code} 2016-2020.csv',
                    siam_dir / subdir / f'{code} 2021-2022.csv'
                ]
            else:
                files = [siam_dir / subdir / f'{code}.csv']
            for f in files:
                if not f.exists():
                    continue
                df = pd.read_csv(f, sep=';', decimal=',', low_memory=False)
                df['datetime'] = pd.to_datetime(df['FECHA'] + ' ' + df['HORA'],
                                                 format='%d/%m/%y %H:%M', errors='coerce')
                df = df.dropna(subset=['datetime'])
                df['PREC'] = pd.to_numeric(df['PREC'], errors='coerce').fillna(0)
                s_all.append(df[['datetime', 'PREC']])
        if not s_all:
            continue
        df_all = pd.concat(s_all).set_index('datetime').sort_index()
        df_all = df_all[~df_all.index.duplicated(keep='first')]
        precip_list.append(df_all['PREC'].resample('D').sum().rename(code))

    if not precip_list:
        return pd.Series(dtype=float, name='precip_mm')
    precip_df = pd.concat(precip_list, axis=1)
    return precip_df.mean(axis=1).rename('precip_mm')


def build_cache(data_dir=None, cache_dir=None):
    """Read all raw sources and write Parquet + JSON sidecars."""
    data_dir = Path(data_dir or DATA_DIR)
    cache_dir = Path(cache_dir or CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)

    excel_path = data_dir / "26.03.06-Registro_Ramblas_MARMENOR.xlsx"
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel not found: {excel_path}")

    # Excel sheets
    sheets = {
        'nitratos': 'Nitratos',
        'fosfatos': 'Fosfatos',
        'nitratos_diario': 'NitratosDiario',
        'fosfatos_diario': 'FosfatosDiario',
        'caudal': 'Caudal',
    }
    id_nombre_n = {}
    id_nombre_f = {}
    for key, hoja in sheets.items():
        df, id_nombre = _leer_hoja_excel(excel_path, hoja)
        df.to_parquet(cache_dir / f"{key}.parquet")
        if hoja == 'Nitratos':
            id_nombre_n = id_nombre
        if hoja == 'Fosfatos':
            id_nombre_f = id_nombre
        print(f"[cache] {key}: {df.shape}")

    with open(cache_dir / "id_nombre_n.json", "w", encoding="utf-8") as f:
        json.dump(id_nombre_n, f, ensure_ascii=False, indent=2)
    with open(cache_dir / "id_nombre_f.json", "w", encoding="utf-8") as f:
        json.dump(id_nombre_f, f, ensure_ascii=False, indent=2)

    # SAIH streamflow
    ramblas_dir = data_dir / "SAIH_Ramblas_clean"
    caudal_path = ramblas_dir / "06A18-Desembocadura Rambla Albujon" / "06A18Q01-Streamflow.csv"
    if caudal_path.exists():
        s_caudal = _load_saih_streamflow(caudal_path)
        s_caudal.to_frame().to_parquet(cache_dir / "saih_caudal.parquet")
        print(f"[cache] saih_caudal: {s_caudal.shape[0]} days")
    else:
        print(f"[cache] WARNING: SAIH caudal not found at {caudal_path}")

    # SIAM precipitation
    siam_dir = data_dir / "SIAM"
    if siam_dir.exists():
        s_precip = _load_siam_precip(siam_dir)
        s_precip.to_frame().to_parquet(cache_dir / "siam_precip.parquet")
        print(f"[cache] siam_precip: {s_precip.shape[0]} days")
    else:
        print(f"[cache] WARNING: SIAM directory not found at {siam_dir}")

    print(f"[cache] Done. Cache dir: {cache_dir}")


def get_cached_df(source_name, cache_dir=None):
    """Load a cached DataFrame (with in-memory memoization)."""
    global _memory_cache
    cache_dir = Path(cache_dir or CACHE_DIR)
    key = str(cache_dir / source_name)
    if key not in _memory_cache:
        path = cache_dir / f"{source_name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Cache miss: {path}")
        _memory_cache[key] = pd.read_parquet(path)
    return _memory_cache[key]


def get_available_date_range(cache_dir=None):
    """Return min/max dates across nutrient sources."""
    cache_dir = Path(cache_dir or CACHE_DIR)
    mins, maxs = [], []
    for source in ['nitratos', 'fosfatos']:
        try:
            df = get_cached_df(source, cache_dir)
            mins.append(df.index.min())
            maxs.append(df.index.max())
        except Exception:
            pass
    if not mins:
        raise FileNotFoundError("No nutrient cache available")
    return {"min": pd.Timestamp(min(mins)).date(), "max": pd.Timestamp(max(maxs)).date()}


def invalidate_memory_cache():
    """Clear in-memory cache so next request reloads from disk."""
    global _memory_cache
    _memory_cache.clear()
    print("[cache] Memory cache invalidated")


if __name__ == "__main__":
    build_cache()
