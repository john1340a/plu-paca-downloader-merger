"""
Boucle de nettoyage : relance clean_plu.py toutes les ~3 min pour extraire
donnees_geographiques/ et supprimer les zips, en parallele du telechargement.

S'arrete automatiquement quand :
  - le telechargement (plu.py) n'est plus en cours, ET
  - il ne reste plus aucun zip a traiter.

Usage : python clean_loop.py
"""

import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
ROOT = HERE / "PLU_PACA"
INTERVAL = 180  # secondes entre deux passages


def count_zips():
    return sum(1 for _ in ROOT.rglob("*.zip"))


def download_running():
    """Vrai si un process python execute plu.py (le downloader)."""
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='python.exe' or name='python3.12.exe'",
             "get", "CommandLine"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        # fallback : on considere qu'il tourne encore pour ne pas s'arreter trop tot
        return True
    return "plu.py" in out


def main():
    passe = 0
    prev_remaining = -1   # nb de zips au tour precedent (pour detecter l'absence de progres)
    while True:
        passe += 1
        zips = count_zips()
        dl = download_running()
        print(f"\n[boucle #{passe}] {time.strftime('%H:%M:%S')} — "
              f"{zips} zip(s) restant(s), téléchargement {'EN COURS' if dl else 'terminé'}",
              flush=True)

        if zips > 0:
            # 1) extraire donnees_geographiques/ et supprimer les zips
            subprocess.run([sys.executable, str(HERE / "clean_plu.py")],
                           cwd=str(HERE))

        # 2) ne garder que les couches de zonage (ZONE_URBA / SECTEUR_CC)
        #    a chaque tour, y compris sur les dossiers fraichement extraits
        subprocess.run([sys.executable, str(HERE / "keep_zone_urba.py")],
                       cwd=str(HERE))

        remaining = count_zips()

        # Fin : telechargement termine.
        if not dl:
            if remaining == 0:
                print("\n✅ Téléchargement terminé, plus aucun zip — nettoyage fini.",
                      flush=True)
                break
            # Il reste des zips alors que le DL est fini : soit ils viennent d'arriver
            # (un dernier tour les traitera), soit ils sont corrompus a la source et
            # ne partiront jamais. On detecte l'absence de progres.
            if remaining == prev_remaining:
                print(f"\n{remaining} zip(s) bloqué(s) (corrompus source ?) — "
                      f"suppression définitive via isoler_corrompus.py",
                      flush=True)
                subprocess.run([sys.executable, str(HERE / "isoler_corrompus.py")],
                               cwd=str(HERE))
                # dernier passage de filtre puis arret
                subprocess.run([sys.executable, str(HERE / "keep_zone_urba.py")],
                               cwd=str(HERE))
                print("\n✅ Corrompus supprimés, nettoyage terminé.", flush=True)
                break

        prev_remaining = remaining
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
