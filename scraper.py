#!/usr/bin/env python3
"""
scraper.py

Attempts to detect and download the latest Excel nutrient registry from the
Canal Mar Menor monitoring portal. Falls back to a configurable direct URL.
"""

import os
import re
import json
import hashlib
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

MONITOR_URL = "https://canalmarmenor.carm.es/monitorizacion/monitorizacion-de-parametros/aforos/"
# Fallback direct URL if the scraper cannot locate the link automatically.
FALLBACK_EXCEL_URL = os.environ.get("FALLBACK_EXCEL_URL", "")

_script_dir = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("NEREIDAS_DATA_DIR", str(_script_dir / "data")))
EXCEL_PATH = DATA_DIR / "26.03.06-Registro_Ramblas_MARMENOR.xlsx"
META_PATH = DATA_DIR / "download_meta.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> bool:
    try:
        print(f"[scraper] Descargando {url} ...")
        r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[scraper] Guardado en {dest} ({dest.stat().st_size} bytes)")
        return True
    except Exception as e:
        print(f"[scraper] Error descargando: {e}")
        return False


def scrape_excel_link() -> str | None:
    """Try to locate an .xlsx link on the portal page."""
    try:
        r = requests.get(MONITOR_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if href.endswith(".xlsx") or "excel" in text or "registro" in text or "aforo" in text:
                full = urljoin(MONITOR_URL, href)
                candidates.append(full)
        if candidates:
            # Prefer link containing the known filename pattern
            for c in candidates:
                if "Registro_Ramblas" in c or "registro_ramblas" in c:
                    return c
            return candidates[0]
    except Exception as e:
        print(f"[scraper] Error parseando portal: {e}")
    return None


def download_latest() -> tuple[bool, str]:
    """
    Returns (updated: bool, message: str).
    updated=True means a new file was written (or first download).
    """
    url = scrape_excel_link()
    if not url:
        if FALLBACK_EXCEL_URL:
            print(f"[scraper] Usando FALLBACK_EXCEL_URL")
            url = FALLBACK_EXCEL_URL
        else:
            return False, "No .xlsx link found on portal and no fallback URL configured."

    # Download to a temporary path to compare hashes
    tmp_path = EXCEL_PATH.with_suffix(".tmp")
    ok = _download(url, tmp_path)
    if not ok:
        return False, f"Network error downloading {url}"

    old_hash = _file_hash(EXCEL_PATH)
    new_hash = _file_hash(tmp_path)

    # Always update metadata so the user can see what the portal offers
    import datetime as _dt
    meta = {
        "remote_url": url,
        "remote_filename": url.split('/')[-1],
        "downloaded_at": _dt.datetime.now().isoformat(),
        "local_path": str(EXCEL_PATH),
        "hash_sha256": new_hash,
        "size_bytes": tmp_path.stat().st_size if tmp_path.exists() else 0,
        "was_new": not (old_hash and old_hash == new_hash),
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if old_hash and old_hash == new_hash:
        tmp_path.unlink(missing_ok=True)
        return False, f"Excel unchanged (hash identical). Portal file: {meta['remote_filename']}"

    # Replace old file
    if EXCEL_PATH.exists():
        EXCEL_PATH.unlink()
    tmp_path.rename(EXCEL_PATH)
    return True, f"New Excel downloaded: {meta['remote_filename']} (hash {new_hash[:16]}...)."


if __name__ == "__main__":
    updated, msg = download_latest()
    print(f"[scraper] updated={updated} | {msg}")
