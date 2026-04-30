#!/usr/bin/env python3
"""
generate_map.py — Create a map of Mar Menor with sampling points.
"""

import json
import time
import requests
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from pathlib import Path

# Approximate coordinates from LineaE notebook for 11 points
# Exact coordinates from locCanalMarMenor.xlsx (Latitud/Longitud columns)
APPROX_COORDS = {
    "1":   (37.716728, -0.859306),  # Drenaje Los Alcázares
    "2":   (37.716254, -0.860976),  # Desembocadura rambla Albujón
    "2B":  (37.719807, -0.875554),  # Aguas arriba Barrio de la Fuensanta
    "2C":  (37.719829, -0.903496),  # Badén aguas abajo La Puebla
    "2D":  (37.722750, -0.931085),  # Pasaje la balsa
    "2E":  (37.724416, -0.935112),  # EDAR Torre-Pacheco
    "3":   (37.715822, -0.861045),  # Tuberías salmuera bajo N-332
    "4":   (37.721360, -0.881273),  # Canal D-7
    "5":   (37.716147, -0.861036),  # Azud CHS
    "6":   (37.720976, -0.882940),  # Tramo Medio Rambla Albujón
    "7":   (37.715732, -0.861524),  # Surgencia
    "8":   (37.716216, -0.859899),  # Aliviadero
    "10":  (37.713206, -0.857388),  # Obra de paso bajo carretera Los Urrutia
    "12":  (37.705939, -0.849817),  # Desembocadura rambla de Miranda
    "13":  (37.700939, -0.844937),  # Desembocadura rambla del Miedo
    "14":  (37.695849, -0.840117),  # El Carmolí
    "15A": (37.669523, -0.819396),  # Desembocadura rambla de las Matildes
    "15B": (37.669045, -0.818877),  # Rambla de las Matildes - corriente sur
    "16":  (37.660651, -0.808468),  # Lo Poyo
    "17":  (37.648926, -0.773813),  # Lengua de Vaca
    "18":  (37.721498, -0.859974),  # Valla Militar
    "19":  (37.719221, -0.860142),  # Freáticos Los Alcázares
    "20":  (37.720280, -0.860361),  # Venta Simón
}

# Point names from Excel
POINT_NAMES = {
    "1": "Drenaje Los Alcázares",
    "2": "Desembocadura rambla Albujón",
    "2B": "Aguas arriba Barrio de la Fuensanta",
    "2C": "Badén aguas abajo La Puebla",
    "2D": "Pasaje la balsa",
    "2E": "EDAR Torre-Pacheco",
    "3": "Tuberías salmuera bajo N-332",
    "4": "Canal D-7",
    "5": "Azud CHS",
    "6": "Tramo Medio Rambla Albujón",
    "7": "Surgencia",
    "8": "Aliviadero",
    "10": "Obra de paso bajo carretera Los Urrutia",
    "12": "Desembocadura rambla de Miranda",
    "13": "Desembocadura rambla del Miedo",
    "14": "El Carmolí",
    "15A": "Desembocadura rambla de las Matildes",
    "15B": "Rambla de las Matildes - corriente sur",
    "16": "Lo Poyo",
    "17": "Lengua de Vaca",
    "18": "Valla Militar",
    "19": "Freáticos Los Alcázares",
    "20": "Venta Simón",
}


def geocode_nominatim(query):
    """Simple Nominatim geocoding with rate limiting."""
    url = "https://nominatopenstreetmap.org/search"
    params = {
        "q": query + ", Mar Menor, Spain",
        "format": "json",
        "limit": 1,
    }
    try:
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "nereidas-map/1.0"})
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  geocode fail for '{query}': {e}")
    return None


def get_all_coords():
    """Build coordinate dictionary from all approximations."""
    coords = {}
    for pid, (lat, lon) in APPROX_COORDS.items():
        coords[pid] = {"lat": lat, "lon": lon, "method": "approx"}
    return coords


def plot_map(coords, output_path):
    fig, ax = plt.subplots(figsize=(10, 10))

    # Mar Menor approximate boundary (simplified polygon)
    # These are rough shoreline points for the lagoon
    mar_menor_lon = np.array([
        -0.86, -0.855, -0.84, -0.82, -0.80, -0.78, -0.76, -0.74, -0.72,
        -0.70, -0.68, -0.66, -0.65, -0.66, -0.68, -0.70, -0.72, -0.74,
        -0.76, -0.78, -0.80, -0.82, -0.84, -0.855, -0.86
    ])
    mar_menor_lat = np.array([
        37.63, 37.65, 37.67, 37.69, 37.71, 37.73, 37.75, 37.77, 37.78,
        37.79, 37.80, 37.81, 37.82, 37.83, 37.835, 37.84, 37.845, 37.845,
        37.84, 37.835, 37.83, 37.82, 37.80, 37.78, 37.63
    ])
    ax.fill(mar_menor_lon, mar_menor_lat, color="#a8d5e5", alpha=0.6, label="Mar Menor")
    ax.plot(mar_menor_lon, mar_menor_lat, color="#4a90a4", linewidth=1.5)

    # Plot points
    plotted = []
    for pid, c in coords.items():
        if c["lat"] is None:
            continue
        color = "#e74c3c" if c["method"] == "approx" else "#3498db"
        ax.scatter(c["lon"], c["lat"], c=color, s=80, zorder=5, edgecolors="white", linewidths=1)
        # Label
        name = POINT_NAMES.get(pid, pid)
        short = f"{pid}: {name[:25]}" if len(name) > 25 else f"{pid}: {name}"
        ax.annotate(
            short,
            (c["lon"], c["lat"]),
            textcoords="offset points",
            xytext=(8, 4),
            fontsize=7,
            path_effects=[pe.withStroke(linewidth=2.5, foreground="white")],
            zorder=6,
        )
        plotted.append(pid)

    ax.set_xlim(-0.92, -0.62)
    ax.set_ylim(37.60, 37.87)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    ax.set_title("Puntos de muestreo de nutrientes — Mar Menor", fontsize=12, fontweight="bold")

    # Legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=8, label="Coordenadas aproximadas"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db", markersize=8, label="Geocodificadas (Nominatim)"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    print(f"Map saved to {output_path}")
    print(f"Plotted {len(plotted)} points: {plotted}")
    return fig, ax


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "figs" / "mapa_muestreo_mar_menor.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Gathering coordinates...")
    coords = get_all_coords()

    # Save JSON for inspection
    json_path = out.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(coords, f, ensure_ascii=False, indent=2)
    print(f"Coordinates saved to {json_path}")

    print("\nGenerating map...")
    plot_map(coords, out)
