"""
Nettoyage des PLU telecharges : pour chaque .zip, on extrait UNIQUEMENT le dossier
`donnees_geographiques/` (les shapefiles SIG) a cote du zip, puis on supprime le zip.

Securite :
- ignore tout zip modifie tres recemment (probablement en cours de telechargement) ;
- verifie l'integrite du zip avant d'y toucher ;
- ne supprime le zip QU'APRES extraction reussie ;
- idempotent : un zip deja traite (dossier extrait present) est saute.

Usage :
    python clean_plu.py            # nettoie tout PLU_PACA/
    python clean_plu.py --dry-run  # affiche ce qui serait fait, sans rien modifier
    python clean_plu.py --dept 04  # limite a un departement (DU_04)
"""

import argparse
import shutil
import sys
import time
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent / "PLU_PACA"
GEO_DIR = "donnees_geographiques"      # nom du dossier a conserver (insensible a la casse)
SAFETY_AGE_SEC = 60                    # on ignore les zips modifies depuis moins de 60 s


def geo_members(zf):
    """Retourne les entrees fichiers appartenant a donnees_geographiques/."""
    out = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = info.filename.split("/")
        # cherche le segment 'donnees_geographiques' n'importe ou dans le chemin
        if any(p.lower() == GEO_DIR for p in parts):
            out.append(info)
    return out


def extract_geo_powershell(zip_path: Path, geo_dest: Path) -> bool:
    """
    Fallback : certains zips (en-tetes non standard) sont illisibles par le module
    Python `zipfile` mais s'extraient sans probleme avec Expand-Archive (Windows).
    On decompresse dans un dossier temporaire, on copie le(s) dossier(s)
    'donnees_geographiques' (insensible a la casse) vers geo_dest, puis on nettoie.
    Retourne True si au moins un fichier de zonage a ete recupere.
    """
    import subprocess
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="plu_geo_"))
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Expand-Archive -LiteralPath '{zip_path}' "
             f"-DestinationPath '{tmp}' -Force"],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            return False

        found = False
        for src_geo in tmp.rglob("*"):
            if src_geo.is_dir() and src_geo.name.lower() == GEO_DIR:
                for f in src_geo.iterdir():
                    if f.is_file():
                        geo_dest.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, geo_dest / f.name)
                        found = True
        return found
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def safe_unlink(path: Path, retries: int = 5, delay: float = 1.0) -> bool:
    """
    Supprime un fichier en reessayant si Windows le verrouille temporairement
    (antivirus, handle residuel -> WinError 32). Retourne True si supprime.
    """
    for attempt in range(retries):
        try:
            path.unlink()
            return True
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                return False
        except FileNotFoundError:
            return True
    return False


def process_zip(zip_path: Path, dry_run: bool):
    # 1) zip recemment modifie => potentiellement en cours d'ecriture, on saute
    if time.time() - zip_path.stat().st_mtime < SAFETY_AGE_SEC:
        print(f"  [SKIP récent] {zip_path.name}")
        return 0

    dest_base = zip_path.with_suffix("")     # <dossier>/<nom_zip_sans_ext>/
    geo_dest = dest_base / GEO_DIR

    # 2) idempotence : deja extrait => on supprime juste le zip.
    #    IMPORTANT : on fait ce check AVANT d'ouvrir le zip — sous Windows on ne
    #    peut pas supprimer un fichier encore ouvert par zipfile.ZipFile (WinError 32).
    if geo_dest.is_dir() and any(geo_dest.iterdir()):
        freed = zip_path.stat().st_size
        if dry_run:
            print(f"  [DRY] supprimerait (déjà extrait) {zip_path.name}")
        elif safe_unlink(zip_path):
            print(f"  [OK déjà extrait] supprimé {zip_path.name}")
        else:
            print(f"  [verrouillé] {zip_path.name} -> réessai au prochain tour")
            return 0
        return freed

    # 3) ouverture du zip pour extraction
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # NB : on ne se fie pas a testzip() ici — il peut renvoyer un nom de
            # dossier (faux positif) et coute cher. Une vraie corruption sera
            # detectee a la lecture des membres (etape 4), ou le zip est conserve.
            members = geo_members(zf)
            if not members:
                print(f"  [SKIP pas de geo] {zip_path.name}")
                return 0

            if dry_run:
                total = sum(m.file_size for m in members)
                print(f"  [DRY] {zip_path.name} -> {len(members)} fichiers geo "
                      f"({total/1024:.0f} Ko), supprimerait le zip "
                      f"({zip_path.stat().st_size/1024/1024:.1f} Mo)")
                return zip_path.stat().st_size

            # 4) extraction des seuls membres geo, en repartant a 'donnees_geographiques/'
            #    (on ignore le dossier racine eventuel a l'interieur du zip).
            #    Si un membre est corrompu (CRC), .read() leve une exception : on
            #    supprime le dossier partiel et on CONSERVE le zip.
            try:
                for m in members:
                    parts = m.filename.split("/")
                    idx = next(i for i, p in enumerate(parts) if p.lower() == GEO_DIR)
                    rel = Path(*parts[idx:])          # donnees_geographiques/....
                    target = dest_base / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                via_powershell = False
            except Exception as e:
                # lecture Python impossible -> on tente le fallback PowerShell.
                # On ne supprime PAS le zip ici (il est encore ouvert par zf) :
                # la suppression se fait apres la sortie du bloc `with`.
                if dest_base.is_dir():
                    shutil.rmtree(dest_base, ignore_errors=True)
                if not extract_geo_powershell(zip_path, geo_dest):
                    print(f"  [SKIP illisible py+ps] {zip_path.name} : {e} -> zip conservé")
                    return 0
                via_powershell = True

            # 5) verification : le dossier extrait existe et n'est pas vide
            if not (geo_dest.is_dir() and any(geo_dest.iterdir())):
                print(f"  [ERREUR extraction vide] {zip_path.name} -> zip conservé")
                return 0

    except zipfile.BadZipFile:
        print(f"  [SKIP illisible] {zip_path.name}")
        return 0
    except Exception as e:
        print(f"  [ERREUR] {zip_path.name} : {e} -> zip conservé")
        return 0

    # 6) extraction OK (le zip est maintenant FERME) -> on peut le supprimer
    freed = zip_path.stat().st_size
    if not safe_unlink(zip_path):
        print(f"  [extrait, zip verrouillé] {zip_path.name} "
              f"-> suppression réessayée au prochain tour")
        return 0
    src = "PowerShell" if via_powershell else f"{len(members)} fichiers"
    print(f"  [OK] {zip_path.name} -> {GEO_DIR}/ ({src}), "
          f"zip supprimé ({freed/1024/1024:.1f} Mo libérés)")
    return freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="simulation, ne modifie rien")
    ap.add_argument("--dept", help="limiter a un departement, ex: 04")
    args = ap.parse_args()

    base = ROOT
    if args.dept:
        base = ROOT / f"DU_{args.dept}"
    if not base.exists():
        print(f"Dossier introuvable : {base}")
        return

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Parcours de {base}\n")

    total_freed = 0
    done = 0
    seen = 0
    for z in base.rglob("*.zip"):       # streaming : pas de tri/liste prealable
        seen += 1
        freed = process_zip(z, args.dry_run)
        if freed:
            total_freed += freed
            done += 1

    print(f"\n{'='*50}")
    print(f"Terminé : {done}/{seen} zip(s) traité(s)")
    print(f"Espace {'qui serait ' if args.dry_run else ''}libéré : "
          f"{total_freed/1024/1024/1024:.2f} Go")


if __name__ == "__main__":
    main()
