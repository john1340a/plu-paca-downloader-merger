"""
Dans chaque dossier donnees_geographiques/, ne conserver QUE les fichiers dont le
nom contient 'ZONE_URBA' (insensible a la casse), comme un LIKE '%ZONE_URBA%' SQL.
Tout le reste (Habillage_*, Prescription_*, Info_*, etc.) est supprime.

Couvre toutes les variantes : ZONE_URBA.shp, 83009_ZONE_URBA_20250523.shp,
minuscules, fichiers .sr parasites, etc.

Usage :
    python keep_zone_urba.py --dry-run   # simulation, ne supprime rien
    python keep_zone_urba.py             # applique
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
# Couches de zonage a conserver (comparaison en minuscules) :
#  - 'zone_urba'  : zonage des PLU/POS
#  - 'secteur_cc' : zonage des Cartes Communales (equivalent ZONE_URBA pour les CC)
KEYWORDS = ("zone_urba", "secteur_cc")

# Extensions SIG legitimes : on ne garde un fichier de zonage que s'il porte
# l'une d'elles. Cela exclut les parasites (.sr, .lock, .tmp ...).
VALID_EXTS = {
    # Shapefile
    ".shp", ".shx", ".dbf", ".dbt", ".prj", ".cpg", ".qpj",
    ".sbn", ".sbx", ".qix", ".idx",
    # MapInfo TAB
    ".tab", ".map", ".dat", ".id", ".ind",
    # QGIS (style / metadonnees) + metadonnees XML
    ".qmd", ".qml", ".xml",
}


def is_keeper(name: str) -> bool:
    low = name.lower()
    if not any(k in low for k in KEYWORDS):
        return False
    return Path(low).suffix in VALID_EXTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="simulation, ne supprime rien")
    args = ap.parse_args()

    geo_dirs = [d for d in ROOT.rglob("donnees_geographiques") if d.is_dir()]
    print(f"{'[DRY-RUN] ' if args.dry_run else ''}{len(geo_dirs)} dossier(s) "
          f"donnees_geographiques\n")

    kept = removed = freed = 0
    empty_after = 0

    for d in geo_dirs:
        local_kept = 0
        for f in d.iterdir():
            if not f.is_file():
                continue
            if is_keeper(f.name):
                kept += 1
                local_kept += 1
            else:
                freed += f.stat().st_size
                removed += 1
                if not args.dry_run:
                    f.unlink()
        if local_kept == 0:
            empty_after += 1
            print(f"  [!] aucune couche de zonage (ZONE_URBA/SECTEUR_CC) dans : "
                  f"{d.relative_to(ROOT)}")

    print(f"\n{'='*50}")
    print(f"Fichiers ZONE_URBA conservés : {kept}")
    print(f"Fichiers {'qui seraient ' if args.dry_run else ''}supprimés : {removed} "
          f"({freed/1024/1024:.1f} Mo)")
    if empty_after:
        print(f"⚠️  {empty_after} dossier(s) sans aucun fichier ZONE_URBA "
              f"(voir [!] ci-dessus)")


if __name__ == "__main__":
    main()
