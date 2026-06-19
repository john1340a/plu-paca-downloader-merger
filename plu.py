import requests
from bs4 import BeautifulSoup
import os
import sys
import time
from pathlib import Path

# Windows console (cp1252) ne sait pas encoder les emojis des print -> forcer UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEPTS_PACA = ["04", "05", "06", "13", "83", "84"]
BASE_URL = "https://files.opendatarchives.fr/geoportail-urbanisme.gouv.fr/"
OUTPUT_DIR = Path("PLU_PACA")

def get_links(url):
    """Liste tous les liens d'une page d'index (hors navigation parent)."""
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    return [
        a["href"] for a in soup.find_all("a", href=True)
        if not a["href"].startswith(("?", "/", ".."))
    ]

def download_file(url, dest_path):
    if dest_path.exists():
        print(f"  [SKIP] {dest_path.name}")
        return
    print(f"  [↓] {dest_path.name} ...", end=" ", flush=True)
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    f.write(chunk)
        print(f"OK ({dest_path.stat().st_size / 1024 / 1024:.1f} MB)")
    except Exception as e:
        print(f"ERREUR : {e}")
        if dest_path.exists():
            dest_path.unlink()

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dept in DEPTS_PACA:
        dept_folder = f"DU_{dept}"
        dept_url = f"{BASE_URL}{dept_folder}/"
        print(f"\n{'='*50}\n📂 {dept_folder} → {dept_url}\n{'='*50}")

        try:
            communes = get_links(dept_url)   # ex: ["DU_04001/", "DU_04002/", ...]
        except Exception as e:
            print(f"  [ERREUR] Département {dept} inaccessible : {e}")
            continue

        for commune in communes:
            if not commune.endswith("/"):
                continue  # ignorer les fichiers à ce niveau

            commune_url = dept_url + commune   # https://.../DU_04/DU_04001/
            print(f"\n  📁 {commune.rstrip('/')}")

            try:
                files = get_links(commune_url)  # ex: ["DU_04001_PLU_xxx.zip"]
            except Exception as e:
                print(f"    [ERREUR] {e}")
                continue

            for filename in files:
                if filename.endswith("/"):
                    continue  # pas de niveau supplémentaire
                file_url = commune_url + filename
                dest = OUTPUT_DIR / dept_folder / commune.rstrip("/") / filename
                download_file(file_url, dest)
                time.sleep(0.3)  # pause légère entre chaque fichier

if __name__ == "__main__":
    main()