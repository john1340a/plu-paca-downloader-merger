# 🗺️ PLU PACA — Téléchargement & fusion des zonages d'urbanisme

Pipeline Python complet pour **télécharger, nettoyer et fusionner les zonages
réglementaires (ZONE_URBA) de tous les PLU/POS/Cartes Communales de la région
Provence-Alpes-Côte d'Azur** en **une seule couche GeoPackage régionale**.

Part de l'archive publique du **Géoportail de l'Urbanisme** (données ouvertes,
Licence Ouverte Etalab 2.0) et produit `PACA_ZONE_URBA.gpkg` : une couche unique,
reprojetée en Lambert 93, prête à l'emploi dans QGIS, ArcGIS ou PostGIS.

> **Résultat** : **685 communes**, **104 690 polygones** de zonage, **~400 Mo**,
> EPSG:2154. Couverture quasi totale des communes PACA disposant d'un document
> d'urbanisme numérisé.

---

## 🎯 À quoi ça sert

Récupérer le zonage d'urbanisme d'une région entière est étonnamment pénible :
- les données sont éparpillées en **un fichier par commune** (des milliers) ;
- chaque archive contient **bien plus que le zonage** (pièces écrites PDF,
  prescriptions, habillage…) — souvent **>99 % de poids inutile** si on ne veut
  que le ZONE_URBA ;
- les formats sont **hétérogènes** (shapefile, MapInfo TAB, GeoPackage) ;
- les **projections varient** d'une commune à l'autre ;
- certaines archives sont **corrompues** sur un miroir mais saines sur un autre.

Ce projet automatise tout ça et livre une couche unique, homogène et légère.

---

## 📦 Sortie produite

`PACA_ZONE_URBA.gpkg` — couche `zonage` :

| Colonne | Description |
|---|---|
| `IDURBA`, `LIBELLE`, `LIBELONG`, `TYPEZONE`, `DESTDOMI`, `NOMFIC`, `URLFIC`, `INSEE`, `DATAPPRO`, `DATVALID` | Attributs standard CNIG du zonage |
| `COMMUNE` | Identifiant commune (`DU_XXXXX`) |
| `DEPT` | Département (`DU_04` … `DU_84`) |
| `DATE_VERSION` | Date de version du PLU (AAAAMMJJ) — **toutes les versions sont conservées** |
| `SOURCE` | Fichier d'origine (format + nom) |

Projection : **RGF93 / Lambert 93 (EPSG:2154)**. Géométries réparées (valides).

---

## ⚙️ Installation

```bash
python -m pip install -r requirements.txt
```

Dépendances : `requests`, `beautifulsoup4`, `geopandas`, `pandas`, `shapely`,
`pyogrio`. Python 3.10+ recommandé.

> Sous Windows, certains vieux zips du Géoportail ont des en-têtes que le module
> Python `zipfile` ne décode pas. Le pipeline bascule alors automatiquement sur
> **PowerShell `Expand-Archive`** comme moteur d'extraction de secours.

---

## 🚀 Utilisation

Le pipeline s'exécute en plusieurs étapes (chaque script est autonome et
idempotent — on peut relancer sans tout refaire) :

```bash
# 1. Télécharger toutes les archives PLU de la PACA (peut faire des dizaines de Go)
python plu.py

# 2. Extraire UNIQUEMENT le dossier donnees_geographiques/ de chaque zip,
#    puis supprimer le zip (libère ~99 % de l'espace)
python clean_plu.py

# 3. Ne conserver que les fichiers de zonage (ZONE_URBA / SECTEUR_CC)
python keep_zone_urba.py

# 4. Filtrer aussi les GeoPackage téléchargés (ne garder que la couche ZONE_URBA)
python filtrer_gpkg.py

# 5. (optionnel) Détecter et écarter les archives corrompues à la source
python isoler_corrompus.py

# 6. Fusionner toutes les couches en une seule (reprojection EPSG:2154)
python fusionner.py   # -> PACA_ZONE_URBA.gpkg
```

### Mode automatique

`clean_loop.py` orchestre les étapes 2→5 en boucle, ce qui permet de **nettoyer
au fil de l'eau pendant que le téléchargement (`plu.py`) tourne encore**, en
gardant l'espace disque bas. Il s'arrête tout seul à la fin du téléchargement.

```bash
python plu.py &          # téléchargement en arrière-plan
python clean_loop.py     # nettoyage continu jusqu'à la fin
```

---

## 🧩 Les scripts

| Script | Rôle |
|---|---|
| [`plu.py`](plu.py) | Télécharge récursivement les archives PLU depuis l'archive ouverte (région → département → commune → `.zip`). Reprise automatique, throttle de politesse. |
| [`clean_plu.py`](clean_plu.py) | Extrait `donnees_geographiques/` de chaque zip et supprime l'archive. Fallback PowerShell pour les zips illisibles par Python, suppression robuste (retries antivirus). |
| [`keep_zone_urba.py`](keep_zone_urba.py) | Ne conserve que les fichiers dont le nom contient `ZONE_URBA` ou `SECTEUR_CC`, avec une liste blanche d'extensions SIG (élimine les parasites `.lock`/`.tmp`). |
| [`filtrer_gpkg.py`](filtrer_gpkg.py) | Réécrit chaque GeoPackage en ne gardant que la couche de zonage (suppression des tables + `VACUUM`). |
| [`isoler_corrompus.py`](isoler_corrompus.py) | Détecte les archives dont le zonage est illisible (Python **et** PowerShell), les supprime, et écrit un rapport CSV. |
| [`clean_loop.py`](clean_loop.py) | Orchestre le nettoyage en boucle jusqu'à la fin du téléchargement. |
| [`recuperer_atom.py`](recuperer_atom.py) | Récupère des communes via le **flux ATOM officiel** (complément de `plu.py` pour les communes manquantes/corrompues sur le miroir). |
| [`fusionner.py`](fusionner.py) | Fusionne shapefiles + MapInfo + GeoPackage en une couche unique : déduplication `(commune, date)`, schéma normalisé, reprojection EPSG:2154, gestion multi-encodage. |

---

## 🛰️ Deux sources de données

Le Géoportail expose les mêmes données via deux canaux ; ce projet les utilise
de façon complémentaire :

1. **Archive miroir** (`files.opendatarchives.fr`) — utilisée par `plu.py` pour
   le téléchargement de masse (navigation par répertoires, pratique pour tout
   aspirer d'un coup). **Mais** elle peut être **incomplète** (PLU récents
   manquants) ou contenir des **fichiers corrompus**.
2. **Flux ATOM officiel** (`geoportail-urbanisme.gouv.fr/atom/dataset-feed/DU_XXXXX`)
   — source de référence, à jour. Idéale pour **récupérer au cas par cas** les
   communes manquantes ou corrompues sur le miroir, souvent avec des **versions
   plus récentes**.

Dans la pratique, le gros du volume vient du miroir, et le flux ATOM comble les
trous (dans ce run : 39 communes récupérées via ATOM, dont 33 absentes du miroir
et 6 corrompues).

---

## 📐 Notes techniques

- **Idempotence** : tous les scripts peuvent être relancés ; ce qui est déjà
  traité est sauté.
- **Sécurité données** : aucune suppression d'archive avant extraction vérifiée ;
  en cas de doute (verrou, illisibilité partielle), l'archive est conservée.
- **Formats de zonage rencontrés** : shapefile (`.shp/.shx/.dbf/.prj/.cpg/.qpj`),
  MapInfo TAB (`.tab/.map/.dat/.id/.ind`), GeoPackage (`.gpkg`).
- **Encodages** : les anciens shapefiles français sont souvent en Windows-1252 ;
  la fusion essaie UTF-8 → cp1252 → latin-1.

---

## 📄 Données & licence

- **Source des données** : Géoportail de l'Urbanisme (Ministère chargé de
  l'Urbanisme / IGN).
- **Licence des données** : Licence Ouverte / Open Licence Etalab 2.0.
- **Licence du code** : [MIT](LICENSE).

Les données téléchargées et la couche fusionnée **ne sont pas incluses** dans ce
dépôt (volumineuses, régénérables) — voir `.gitignore`. Lancez le pipeline pour
les produire.

---

## ⚠️ Bon usage

Le téléchargement de masse représente plusieurs dizaines de Go. `plu.py` applique
une pause entre chaque fichier pour ne pas surcharger le serveur — **merci de ne
pas retirer ce throttle**. Adaptez la liste des départements (`DEPTS_PACA`) ou
l'URL de base si vous ciblez une autre région.
