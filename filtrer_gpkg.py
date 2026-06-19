"""
Pour chaque GeoPackage (.gpkg), ne conserver que la/les couche(s) de zonage
(nom contenant ZONE_URBA ou SECTEUR_CC). Toutes les autres couches (PRESCRIPTION,
INFO, HABILLAGE...) sont supprimees, puis le fichier est compacte (VACUUM).

Un .gpkg est une base SQLite : supprimer une couche = supprimer sa table de donnees
+ ses references dans les tables de metadonnees gpkg_* + ses index spatiaux rtree_*.

Usage :
    python filtrer_gpkg.py --dry-run   # liste sans modifier
    python filtrer_gpkg.py             # applique
"""

import argparse
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
KEYWORDS = ("zone_urba", "secteur_cc")


def is_zoning(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in KEYWORDS)


def drop_layer(con, layer):
    """Supprime une couche feature et toutes ses references dans le gpkg."""
    cur = con.cursor()
    # index spatiaux R-Tree associes (si presents)
    for suffix in ("", "_node", "_parent", "_rowid"):
        cur.execute(f'DROP TABLE IF EXISTS "rtree_{layer}_geom{suffix}"')
    # triggers lies au rtree peuvent rester -> ignores (supprimes avec la table)
    # references dans les tables de metadonnees gpkg_*
    cur.execute("DELETE FROM gpkg_geometry_columns WHERE table_name = ?", (layer,))
    cur.execute("DELETE FROM gpkg_contents WHERE table_name = ?", (layer,))
    # table optionnelle (driver OGR)
    try:
        cur.execute("DELETE FROM gpkg_ogr_contents WHERE table_name = ?", (layer,))
    except sqlite3.OperationalError:
        pass
    # extensions eventuelles referencant la table
    try:
        cur.execute("DELETE FROM gpkg_extensions WHERE table_name = ?", (layer,))
    except sqlite3.OperationalError:
        pass
    # la table de donnees elle-meme
    cur.execute(f'DROP TABLE IF EXISTS "{layer}"')


def process_gpkg(path: Path, dry_run: bool):
    con = sqlite3.connect(path)
    try:
        layers = [r[0] for r in con.execute(
            "SELECT table_name FROM gpkg_contents").fetchall()]
        to_drop = [l for l in layers if not is_zoning(l)]
        to_keep = [l for l in layers if is_zoning(l)]

        if not to_keep:
            print(f"  [!] aucune couche de zonage : {path.name} (ignoré)")
            return 0
        if not to_drop:
            return 0  # deja propre

        if dry_run:
            print(f"  [DRY] {path.name} : garde {to_keep}, supprime {len(to_drop)} couche(s)")
            return 0

        before = path.stat().st_size
        for layer in to_drop:
            drop_layer(con, layer)
        con.commit()
        con.execute("VACUUM")
        con.commit()
    finally:
        con.close()

    after = path.stat().st_size
    freed = before - after
    print(f"  [OK] {path.name} : {len(to_keep)} couche(s) gardée(s), "
          f"{after/1024/1024:.1f} Mo ({freed/1024/1024:+.1f} Mo)")
    return freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gpkgs = sorted(ROOT.rglob("*.gpkg"))
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}{len(gpkgs)} GeoPackage(s)\n")

    total_freed = 0
    for g in gpkgs:
        try:
            total_freed += process_gpkg(g, args.dry_run)
        except Exception as e:
            print(f"  [ERREUR] {g.name} : {e}")

    print(f"\n{'='*50}")
    print(f"Espace {'qui serait ' if args.dry_run else ''}libéré : "
          f"{total_freed/1024/1024:.1f} Mo")


if __name__ == "__main__":
    main()
