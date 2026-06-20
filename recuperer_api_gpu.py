"""
Recupere le zonage (ZONE_URBA) des communes manquantes directement via l'API
GPU (apicarto.ign.fr), qui sert le zonage en GeoJSON quel que soit le type de
document (PLU communal OU PLU intercommunal). Methode : POST du contour communal
sur /api/gpu/zone-urba, avec pagination.

Lit communes_manquantes.csv et ne traite que les communes 'DOCUMENT_NON_RECUPERE'.
Ecrit un GeoPackage par commune dans PLU_PACA/_api_gpu/DU_<insee>.gpkg
(couche 'zonage'), au meme schema que fusionner.py.

Usage : python recuperer_api_gpu.py
"""

import csv
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
OUT = ROOT / "_api_gpu"
CSV_IN = Path(__file__).parent / "communes_manquantes.csv"
ZONE_URBA_API = "https://apicarto.ign.fr/api/gpu/zone-urba"
CONTOUR_API = "https://geo.api.gouv.fr/communes/{insee}?fields=contour&format=json"
PAGE = 1000  # taille de page apicarto

# schema cible (identique a fusionner.py)
STD_COLS = ["IDURBA", "LIBELLE", "LIBELONG", "TYPEZONE", "DESTDOMI",
            "NOMFIC", "URLFIC", "INSEE", "DATAPPRO", "DATVALID"]


def get_contour(insee):
    r = requests.get(CONTOUR_API.format(insee=insee), timeout=30)
    r.raise_for_status()
    return r.json().get("contour")


def fetch_zonage(contour):
    """Recupere tous les polygones de zonage (avec pagination)."""
    feats = []
    start = 0
    while True:
        r = requests.post(ZONE_URBA_API, json={"geom": contour},
                          params={"_start": start, "_limit": PAGE}, timeout=120)
        r.raise_for_status()
        d = r.json()
        batch = d.get("features", [])
        feats.extend(batch)
        total = d.get("totalFeatures", len(feats))
        if len(feats) >= total or not batch:
            break
        start += PAGE
    return feats


def to_gdf(feats, insee, dept):
    gdf = gpd.GeoDataFrame.from_features(feats)
    if gdf.empty:
        return None
    # le GeoJSON apicarto est en WGS84 (EPSG:4326)
    gdf.set_crs("EPSG:4326", inplace=True, allow_override=True)
    gdf = gdf.to_crs("EPSG:2154")
    # normaliser colonnes (apicarto utilise des noms minuscules)
    gdf.columns = [c.upper() if c != gdf.geometry.name else c for c in gdf.columns]
    keep = {col: (gdf[col] if col in gdf.columns else pd.NA) for col in STD_COLS}
    out = gpd.GeoDataFrame(keep, geometry=gdf.geometry, crs="EPSG:2154")
    out["COMMUNE"] = f"DU_{insee}"
    out["DEPT"] = f"DU_{dept}"
    out["DATE_VERSION"] = ""
    out["SOURCE"] = "api_gpu"
    # reparer les geometries
    inv = ~out.geometry.is_valid
    if inv.any():
        out.loc[inv, "geometry"] = out.loc[inv, "geometry"].make_valid()
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    targets = []
    with open(CSV_IN, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["statut"] == "DOCUMENT_NON_RECUPERE":
                targets.append((row["insee"], row["dept"], row["nom"]))

    print(f"{len(targets)} commune(s) à récupérer via l'API GPU\n")
    ok = vide = err = 0
    for insee, dept, nom in targets:
        dst = OUT / f"DU_{insee}.gpkg"
        if dst.exists():
            print(f"  {insee} {nom}: déjà fait")
            ok += 1
            continue
        try:
            contour = get_contour(insee)
            if not contour:
                print(f"  {insee} {nom}: pas de contour")
                err += 1
                continue
            feats = fetch_zonage(contour)
            gdf = to_gdf(feats, insee, dept)
            if gdf is None or gdf.empty:
                print(f"  {insee} {nom}: 0 polygone (rien servi par l'API)")
                vide += 1
                continue
            gdf.to_file(dst, layer="zonage", driver="GPKG")
            print(f"  {insee} {nom}: {len(gdf)} polygones ✓")
            ok += 1
        except Exception as e:
            print(f"  {insee} {nom}: ERREUR {e}")
            err += 1
        time.sleep(0.2)

    print(f"\n{ok} récupérée(s), {vide} vide(s), {err} erreur(s) -> {OUT}")


if __name__ == "__main__":
    main()
