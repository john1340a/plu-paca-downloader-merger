"""
Recupere des communes via le flux ATOM officiel du Geoportail de l'Urbanisme,
en complement de plu.py (qui aspire le miroir opendatarchives). Utile pour les
communes absentes ou corrompues sur le miroir : le flux ATOM est la source de
reference, souvent avec des versions plus recentes.

Le flux d'une commune :
  https://www.geoportail-urbanisme.gouv.fr/atom/dataset-feed/DU_<INSEE>
contient un <link rel="alternate"> pointant vers le .zip telechargeable.

Usage :
    python recuperer_atom.py DU_83065 DU_05147 ...   # communes explicites
    python recuperer_atom.py --from-file communes.txt # une commune par ligne

Les zips sont deposes dans PLU_PACA/_manuel/ ; ensuite, passez-les dans le
pipeline habituel (clean_plu.py -> keep_zone_urba.py -> reclassement -> fusionner.py).
"""

import argparse
import sys
import zipfile
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

FEED = "https://www.geoportail-urbanisme.gouv.fr/atom/dataset-feed/"
OUT = Path(__file__).parent / "PLU_PACA" / "_manuel"
KEYWORDS = ("zone_urba", "secteur_cc")


def download_url(commune: str):
    """Resout le flux ATOM d'une commune -> URL de l'archive (.zip), ou None."""
    r = requests.get(FEED + commune, timeout=30)
    r.encoding = "utf-8"
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "xml")
    for link in soup.find_all("link"):
        if link.get("rel") == "alternate" and link.get("href"):
            return link.get("href")
    return None


def zoning_ok(zip_path: Path) -> bool:
    """True si l'archive contient une couche de zonage lisible."""
    try:
        zf = zipfile.ZipFile(zip_path)
        members = [i for i in zf.infolist()
                   if not i.is_dir()
                   and any(k in i.filename.lower() for k in KEYWORDS)]
        if not members:
            return False
        for i in members:
            zf.open(i).read()
        return True
    except Exception:
        return False


def fetch(commune: str):
    url = download_url(commune)
    if not url:
        print(f"  {commune}: aucun téléchargement disponible")
        return False
    fn = url.rsplit("/", 1)[-1]
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / fn
    if dst.exists():
        print(f"  {commune}: déjà présent ({fn})")
        return True
    try:
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_content(512 * 1024):
                    f.write(chunk)
    except Exception as e:
        print(f"  {commune}: ERREUR téléchargement : {e}")
        if dst.exists():
            dst.unlink()
        return False
    ok = zoning_ok(dst)
    size = dst.stat().st_size / 1024 / 1024
    print(f"  {commune}: {fn} ({size:.0f} Mo) — zonage {'OK' if ok else 'absent/illisible'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("communes", nargs="*", help="codes commune, ex: DU_83065")
    ap.add_argument("--from-file", help="fichier texte, une commune par ligne")
    args = ap.parse_args()

    communes = list(args.communes)
    if args.from_file:
        communes += [l.strip() for l in Path(args.from_file).read_text().splitlines()
                     if l.strip()]
    if not communes:
        ap.error("indiquer au moins une commune (ou --from-file)")

    ok = 0
    for c in communes:
        if not c.startswith("DU_"):
            c = "DU_" + c
        if fetch(c):
            ok += 1
    print(f"\n{ok}/{len(communes)} commune(s) récupérée(s) dans {OUT}")


if __name__ == "__main__":
    main()
