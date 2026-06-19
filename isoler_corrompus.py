"""
Detecte les zips dont la/les couche(s) de zonage (ZONE_URBA / SECTEUR_CC) sont
illisibles a la fois par Python ET par PowerShell (Expand-Archive) -> corrompus
a la source (Geoportail). Ces fichiers ne sont pas recuperables par re-telechargement.

Action : les SUPPRIMER definitivement et ecrire un rapport CSV des communes effacees
(pour garder la trace de ce qui n'a pas de zonage exploitable).

A lancer de preference APRES la fin du telechargement complet.

Usage :
    python isoler_corrompus.py --dry-run   # liste sans rien supprimer
    python isoler_corrompus.py             # supprime + rapport CSV
"""

import argparse
import csv
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
REPORT = Path(__file__).parent / "rapport_corrompus.csv"
KEYWORDS = ("zone_urba", "secteur_cc")
SAFETY_AGE_SEC = 60


def zone_members(zf):
    return [i for i in zf.infolist()
            if not i.is_dir()
            and any(k in i.filename.lower() for k in KEYWORDS)]


def python_can_read_zoning(zip_path):
    """True si Python lit TOUS les membres de zonage sans erreur."""
    try:
        zf = zipfile.ZipFile(zip_path)
        members = zone_members(zf)
        if not members:
            return None  # pas de zonage du tout
        for i in members:
            zf.open(i).read()
        return True
    except Exception:
        return False


def powershell_can_extract(zip_path):
    """True si Expand-Archive recupere au moins un fichier de zonage."""
    tmp = Path(tempfile.mkdtemp(prefix="plu_chk_"))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Expand-Archive -LiteralPath '{zip_path}' -DestinationPath '{tmp}' -Force"],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            return False
        for f in tmp.rglob("*"):
            if f.is_file() and any(k in f.name.lower() for k in KEYWORDS):
                return True
        return False
    except Exception:
        return False
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    corrompus = []
    checked = 0
    for z in ROOT.rglob("*.zip"):
        if time.time() - z.stat().st_mtime < SAFETY_AGE_SEC:
            continue  # potentiellement en cours de telechargement
        checked += 1
        py = python_can_read_zoning(z)
        if py is True or py is None:
            continue  # zonage lisible, ou pas de zonage -> pas concerne ici
        # Python a echoue -> on tente PowerShell
        if powershell_can_extract(z):
            continue  # recuperable par PowerShell, on laisse la boucle s'en charger
        corrompus.append(z)
        print(f"  [CORROMPU source] {z.relative_to(ROOT)}")

    print(f"\n{checked} zip(s) verifie(s) — {len(corrompus)} corrompu(s) a la source")

    if not corrompus:
        return

    if not args.dry_run:
        # 1) rapport CSV AVANT suppression (sinon on perd les infos)
        with open(REPORT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fichier", "departement", "commune", "taille_Mo"])
            for z in corrompus:
                parts = z.relative_to(ROOT).parts
                dept = parts[0] if len(parts) > 0 else ""
                com = parts[1] if len(parts) > 1 else ""
                w.writerow([z.name, dept, com, f"{z.stat().st_size/1024/1024:.1f}"])
        # 2) suppression definitive
        deleted = 0
        for z in corrompus:
            try:
                z.unlink()
                deleted += 1
            except Exception as e:
                print(f"  [echec suppression] {z.name} : {e}")
        print(f"\n→ {deleted} fichier(s) corrompu(s) supprimé(s) définitivement")
        print(f"→ rapport des communes effacées : {REPORT}")
    else:
        print("[DRY-RUN] rien supprimé.")


if __name__ == "__main__":
    main()
