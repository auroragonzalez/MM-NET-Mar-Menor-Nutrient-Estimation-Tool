#!/usr/bin/env python3
"""
analysis_core.py — Reusable analysis functions extracted from
01_source_apportionment.py and 02_hydrological_response.py.
"""

import numpy as np
import pandas as pd
from scipy import stats

MW_NO3 = 62.0
MW_PO4 = 95.0
REDFIELD = 16.0


# ---------------------------------------------------------------------------
# 01 — Source apportionment & N:P ratio
# ---------------------------------------------------------------------------
def compute_source_apportionment(df_no3_diario, df_po4_diario, id_nombre_n, id_nombre_f):
    """
    Compute cumulative load ranking for NO3 and PO4.
    Returns dict with top-5 tables and raw arrays for Plotly.
    """
    def _calc_totales(df_diario, id_nombre):
        totales = {}
        for col in df_diario.columns:
            serie = df_diario[col].dropna()
            if len(serie) >= 5:
                total_kg = serie.sum()
                nombre = id_nombre.get(str(col), str(col))
                totales[col] = {'nombre': nombre, 'total_kg': total_kg, 'n': len(serie)}
        return totales

    totales_no3 = _calc_totales(df_no3_diario, id_nombre_n)
    totales_po4 = _calc_totales(df_po4_diario, id_nombre_f)

    df_tot_no3 = pd.DataFrame(totales_no3).T
    df_tot_no3['total_kg'] = pd.to_numeric(df_tot_no3['total_kg'])
    df_tot_no3 = df_tot_no3[df_tot_no3['total_kg'] > 0].sort_values('total_kg', ascending=False)

    df_tot_po4 = pd.DataFrame(totales_po4).T
    df_tot_po4['total_kg'] = pd.to_numeric(df_tot_po4['total_kg'])
    df_tot_po4 = df_tot_po4[df_tot_po4['total_kg'] > 0].sort_values('total_kg', ascending=False)

    total_global_no3 = df_tot_no3['total_kg'].sum()
    total_global_po4 = df_tot_po4['total_kg'].sum()
    df_tot_no3['pct'] = 100 * df_tot_no3['total_kg'] / total_global_no3
    df_tot_po4['pct'] = 100 * df_tot_po4['total_kg'] / total_global_po4

    # Prepare Plotly-friendly arrays
    top5_no3 = df_tot_no3.head(5)
    top5_po4 = df_tot_po4.head(5)

    no3_labels = [f"Pto.{idx}\n{row['nombre'][:18]}" for idx, row in top5_no3.iterrows()]
    po4_labels = [f"Pto.{idx}\n{row['nombre'][:18]}" for idx, row in top5_po4.iterrows()]

    def _get_colors(pcts, thresholds=(20, 10, 5)):
        cmap = {
            'high': '#d32f2f',
            'mid': '#f57c00',
            'low': '#fdd835',
            'other': '#90caf9'
        }
        colors = []
        for p in pcts:
            if p >= thresholds[0]:
                colors.append(cmap['high'])
            elif p >= thresholds[1]:
                colors.append(cmap['mid'])
            elif p >= thresholds[2]:
                colors.append(cmap['low'])
            else:
                colors.append(cmap['other'])
        return colors

    load_ranking_plot = {
        'no3': {
            'y': no3_labels[::-1],
            'x': (top5_no3['total_kg'] / 1000).tolist()[::-1],
            'pct': top5_no3['pct'].tolist()[::-1],
            'colors': _get_colors(top5_no3['pct'].tolist())[::-1],
            'title': 'Cumulative Nitrate Contribution',
            'xlabel': 'Cumulative load (ton NO₃)',
        },
        'po4': {
            'y': po4_labels[::-1],
            'x': (top5_po4['total_kg'] / 1000).tolist()[::-1],
            'pct': top5_po4['pct'].tolist()[::-1],
            'colors': _get_colors(top5_po4['pct'].tolist(), (30, 15, 5))[::-1],
            'title': 'Cumulative Phosphate Contribution',
            'xlabel': 'Cumulative load (ton PO₄)',
        },
    }

    tables = {
        'totales_no3_top5': [
            {'pto': str(idx), 'nombre': str(row['nombre'])[:30],
             'total_tonnes': round(row['total_kg'] / 1000, 2), 'pct': round(row['pct'], 2)}
            for idx, row in top5_no3.iterrows()
        ],
        'totales_po4_top5': [
            {'pto': str(idx), 'nombre': str(row['nombre'])[:30],
             'total_tonnes': round(row['total_kg'] / 1000, 3), 'pct': round(row['pct'], 2)}
            for idx, row in top5_po4.iterrows()
        ],
    }

    return {'tables': tables, 'load_ranking_plot': load_ranking_plot}


def compute_np_ratio(df_nitratos, df_fosfatos, id_nombre_n, id_nombre_f):
    """
    Compute N:P molar ratio per point and temporal series for Point 2.
    Returns summary stats and Plotly-friendly arrays.
    """
    puntos_comunes = [col for col in df_nitratos.columns
                      if col in df_fosfatos.columns and col not in ['mes', 'año']
                      and df_nitratos[col].count() > 5 and df_fosfatos[col].count() > 5]

    ratio_np_stats = {}
    boxplot_series = []
    boxplot_labels = []

    for col in puntos_comunes:
        s_no3 = df_nitratos[col].dropna()
        s_po4 = df_fosfatos[col].dropna()
        s_no3 = s_no3[~s_no3.index.duplicated(keep='first')]
        s_po4 = s_po4[~s_po4.index.duplicated(keep='first')]
        df_al = pd.DataFrame({'no3': s_no3, 'po4': s_po4}).dropna()
        if len(df_al) >= 5:
            no3_mol = df_al['no3'] / MW_NO3
            po4_mol = df_al['po4'] / MW_PO4
            ratio = (no3_mol / po4_mol).replace([np.inf, -np.inf], np.nan).dropna()
            nombre = id_nombre_n.get(str(col), col)
            ratio_np_stats[col] = {
                'nombre': nombre[:40],
                'n_pares': len(df_al),
                'mediana': float(ratio.median()),
                'media': float(ratio.mean()),
                'p25': float(ratio.quantile(0.25)),
                'p75': float(ratio.quantile(0.75)),
                'pct_P_limitante': float((ratio > REDFIELD).mean() * 100),
                'serie': ratio,
            }
            # For boxplot
            clipped = ratio.clip(upper=ratio.quantile(0.99))
            boxplot_series.append(clipped.values.tolist())
            boxplot_labels.append(f"Pto.{col}\n{nombre[:14]}")

    # Temporal series for Point 2
    temporal = {}
    pt = '2'
    if pt in ratio_np_stats:
        ratio_t = ratio_np_stats[pt]['serie']
        ratio_smooth = ratio_t.rolling(8, min_periods=3).mean()
        temporal = {
            'dates': [d.strftime('%Y-%m-%d') for d in ratio_t.index],
            'values': ratio_t.clip(upper=1000).values.tolist(),
            'smooth': ratio_smooth.clip(upper=1000).values.tolist(),
            'mediana': ratio_np_stats[pt]['mediana'],
            'pct_P_limitante': ratio_np_stats[pt]['pct_P_limitante'],
        }

    summary = [
        {'pto': str(k), 'nombre': v['nombre'][:30], 'mediana': round(v['mediana'], 1),
         'pct_P_limitante': round(v['pct_P_limitante'], 1)}
        for k, v in ratio_np_stats.items()
    ]

    return {
        'tables': {'ratio_np_summary': summary},
        'np_boxplot_plot': {
            'data': boxplot_series,
            'labels': boxplot_labels,
            'redfield': REDFIELD,
        },
        'np_temporal_plot': temporal,
    }


# ---------------------------------------------------------------------------
# 02 — Hydrological response
# ---------------------------------------------------------------------------
def compute_crosscorr(precip_diaria, caudal_diario, max_lag=30):
    """
    Cross-correlation between daily precipitation and streamflow.
    Returns lags array, correlations array, optimal lag, and max correlation.
    """
    precip_alineada = precip_diaria.reindex(caudal_diario.index).interpolate()
    caudal_alineado = caudal_diario

    df_aligned = pd.DataFrame({'precip': precip_alineada, 'caudal': caudal_alineado}).dropna()
    if len(df_aligned) < max_lag * 2 + 2:
        max_lag = min(max_lag, len(df_aligned) // 4)

    p_norm = (df_aligned['precip'] - df_aligned['precip'].mean()) / (df_aligned['precip'].std() + 1e-10)
    c_norm = (df_aligned['caudal'] - df_aligned['caudal'].mean()) / (df_aligned['caudal'].std() + 1e-10)

    lags = list(range(-max_lag, max_lag + 1))
    correlaciones = []
    for lag in lags:
        if lag >= 0:
            corr = p_norm.values[:len(p_norm) - lag].dot(c_norm.values[lag:]) / len(p_norm)
        else:
            corr = p_norm.values[-lag:].dot(c_norm.values[:len(c_norm) + lag]) / len(p_norm)
        correlaciones.append(float(corr))

    lag_optimo = lags[np.argmax(correlaciones)]
    corr_max = max(correlaciones)

    return {
        'lags': lags,
        'correlations': correlaciones,
        'lag_optimo_dias': int(lag_optimo),
        'corr_maxima': round(float(corr_max), 3),
    }


def compute_cq_analysis(df_caudal, df_nutriente, pto_caudal, pto_nutriente, nombre_nutriente):
    """
    C-Q chemostatic analysis: power law C = a * Q^b.
    Weekly resampling + log-log regression, matching paper Fig. 3.
    """
    if pto_caudal not in df_caudal.columns or pto_nutriente not in df_nutriente.columns:
        return None

    # Weekly resampling (matches paper's 02_hydrological_response.py)
    w_conc = df_nutriente[pto_nutriente].dropna().resample('W').mean()
    w_q = df_caudal[pto_caudal].dropna().resample('W').mean()

    df = pd.DataFrame({'caudal': w_q, 'conc': w_conc}).dropna()
    df = df[(df['caudal'] > 0) & (df['conc'] > 0)]
    if len(df) < 10:
        return None

    log_Q = np.log10(df['caudal'])
    log_C = np.log10(df['conc'])
    slope, intercept, r_value, p_value, std_err = stats.linregress(log_Q, log_C)

    if abs(slope) < 0.05:
        comp = 'Chemostatic (b ≈ 0)'
    elif slope > 0:
        comp = 'Mobilization (b > 0)'
    else:
        comp = 'Dilution (b < 0)'

    # Generate fitted line points
    q_range = np.logspace(np.log10(df['caudal'].min()), np.log10(df['caudal'].max()), 100)
    c_fit = 10 ** (intercept + slope * np.log10(q_range))

    return {
        'slope_b': round(float(slope), 3),
        'intercept': round(float(intercept), 3),
        'r2': round(float(r_value ** 2), 3),
        'p_value': round(float(p_value), 4),
        'std_err': round(float(std_err), 3),
        'behaviour': comp,
        'n_samples': int(len(df)),
        'scatter': {
            'x': df['caudal'].values.tolist(),
            'y': df['conc'].values.tolist(),
        },
        'fit': {
            'x': q_range.tolist(),
            'y': c_fit.tolist(),
        },
    }
