"""
Fusionne toutes les couches de zonage (ZONE_URBA / SECTEUR_CC) de la PACA en UNE
seule couche GeoPackage regionale.

Sources prises en compte :
  - shapefiles  (*.shp) dans donnees_geographiques/
  - MapInfo TAB (*.tab) dans donnees_geographiques/
  - GeoPackage  (*.gpkg) deja filtres

Traitement :
  - ne garde que les colonnes standard CNIG (schema fixe) + commune/dept/source/geom_type
  - reprojette tout en EPSG:2154 (RGF93 / Lambert 93)
  - empile dans PACA_ZONE_URBA.gpkg, couche 'zonage'

Usage : python fusionner.py
"""

import re
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
OUT = Path(__file__).parent / "PACA_ZONE_URBA.gpkg"
LAYER = "zonage"
TARGET_CRS = "EPSG:2154"

# Colonnes standard CNIG du standard ZONE_URBA / cartes communales (on garde
# l'intersection de ce qui existe ; les manquantes seront NULL).
STD_COLS = [
    "IDURBA", "LIBELLE", "LIBELONG", "TYPEZONE", "DESTDOMI",
    "NOMFIC", "URLFIC", "INSEE", "DATAPPRO", "DATVALID",
]


def is_zoning_name(name: str) -> bool:
    low = name.lower()
    return "zone_urba" in low or "secteur_cc" in low


def extract_date(path: Path, layer=None) -> str:
    """Extrait la date de version AAAAMMJJ depuis le chemin/nom (sinon '')."""
    candidates = [str(path)]
    if layer:
        candidates.append(layer)
    for c in candidates:
        m = re.search(r"(20\d{6}|19\d{6})", c)
        if m:
            return m.group(1)
    return ""


def read_any_encoding(path, layer=None):
    """
    Lit une couche en essayant plusieurs encodages (les vieux shapefiles/TAB
    francais sont souvent en Windows-1252, pas en UTF-8).
    """
    for enc in (None, "cp1252", "latin-1"):
        try:
            kwargs = {"layer": layer} if layer else {}
            if enc:
                kwargs["encoding"] = enc
            return gpd.read_file(path, **kwargs)
        except UnicodeDecodeError:
            continue
    # dernier recours : ignorer les octets invalides
    try:
        kwargs = {"layer": layer} if layer else {}
        return gpd.read_file(path, encoding="utf-8", **kwargs)
    except Exception:
        raise


def normalize(gdf, commune, dept, source, date_version):
    """Reduit au schema standard + colonnes d'identification, reprojette."""
    # uniformise les noms de colonnes en MAJUSCULES pour le matching
    gdf.columns = [c.upper() if c != gdf.geometry.name else c for c in gdf.columns]
    keep = {}
    for col in STD_COLS:
        keep[col] = gdf[col] if col in gdf.columns else pd.NA
    out = gpd.GeoDataFrame(keep, geometry=gdf.geometry, crs=gdf.crs)
    out["COMMUNE"] = commune
    out["DEPT"] = dept
    out["DATE_VERSION"] = date_version
    out["SOURCE"] = source
    # reprojection
    if out.crs is None:
        out.set_crs(TARGET_CRS, inplace=True, allow_override=True)
    elif out.crs.to_epsg() != 2154:
        out = out.to_crs(TARGET_CRS)
    return out


def collect_sources():
    """
    Retourne la liste des sources a fusionner, dedupliquees sur (commune, date) :
    si une meme version existe en plusieurs formats, on garde un seul format selon
    la priorite shapefile > mapinfo > gpkg. Toutes les DATES distinctes sont gardees.
    """
    import sqlite3
    PRIORITY = {"shapefile": 0, "mapinfo": 1, "gpkg": 2}
    raw = []

    for shp in ROOT.rglob("*.shp"):
        if is_zoning_name(shp.name):
            p = shp.relative_to(ROOT).parts
            raw.append((shp, None, p[1], p[0], "shapefile", extract_date(shp)))
    for tab in ROOT.rglob("*.tab"):
        if is_zoning_name(tab.name):
            p = tab.relative_to(ROOT).parts
            raw.append((tab, None, p[1], p[0], "mapinfo", extract_date(tab)))
    for g in ROOT.rglob("*.gpkg"):
        p = g.relative_to(ROOT).parts
        try:
            layers = [r[0] for r in sqlite3.connect(g).execute(
                "SELECT table_name FROM gpkg_contents")]
        except Exception:
            continue
        for lyr in layers:
            if is_zoning_name(lyr):
                raw.append((g, lyr, p[1], p[0], "gpkg", extract_date(g, lyr)))

    # deduplication sur (commune, date) en gardant le format prioritaire
    best = {}
    for src in raw:
        path, layer, commune, dept, kind, date = src
        key = (commune, date)
        if key not in best or PRIORITY[kind] < PRIORITY[best[key][4]]:
            best[key] = src
    return list(best.values())


def main():
    if OUT.exists():
        OUT.unlink()

    sources = collect_sources()
    print(f"{len(sources)} source(s) après déduplication (commune, date)\n")
    frames = []
    ok = err = 0
    for path, layer, commune, dept, kind, date in sources:
        try:
            gdf = read_any_encoding(path, layer)
            if gdf is None or gdf.empty:
                continue
            frames.append(normalize(gdf, commune, dept, f"{kind}:{path.name}", date))
            ok += 1
            if ok % 100 == 0:
                print(f"  ...{ok} couches lues", flush=True)
        except Exception as e:
            err += 1
            print(f"  [ERREUR] {path.name} ({layer or ''}): {e}")

    print(f"\n{ok} couche(s) lue(s), {err} erreur(s). Fusion...", flush=True)
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=TARGET_CRS)
    print(f"Total entites : {len(merged)}")

    merged.to_file(OUT, layer=LAYER, driver="GPKG")
    print(f"\n✅ Écrit : {OUT}  (couche '{LAYER}', {len(merged)} polygones, {TARGET_CRS})")
    print(f"   Taille : {OUT.stat().st_size/1024/1024:.1f} Mo")
    # recap par dept
    print("\nPolygones par département :")
    for d, n in merged["DEPT"].value_counts().sort_index().items():
        print(f"  {d}: {n}")


if __name__ == "__main__":
    main()
