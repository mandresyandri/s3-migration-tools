# s3-migration-tools

Outil en ligne de commande pour migrer les objets d'un bucket S3 vers un autre,
y compris entre fournisseurs différents (AWS, Scaleway, OVH, Cellar Clever Cloud…).

- Copie en flux (pas de passage par le disque), en parallèle
- Relançable : ne recopie que les objets manquants ou de taille différente
- Conserve `Content-Type` et les métadonnées
- Compatible avec les S3 qui refusent les checksums ajoutés par défaut par boto3 (Ceph / Cellar)

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # puis remplir les accès source / destination
```

## Utilisation

```bash
uv run s3-migration-tools check              # accès aux deux buckets
uv run s3-migration-tools diff               # ce qui manque en destination
uv run s3-migration-tools sync --dry-run     # ce qui serait copié
uv run s3-migration-tools sync --workers 8   # copie
uv run s3-migration-tools verify             # contrôle final
```

Options communes : `--src-bucket`, `--dst-bucket`, `--prefix`.
Un rapport JSON de chaque `sync` est écrit dans `reports/`.

## Configuration

Variables lues dans `.env` (voir `.env.example`), préfixées `SRC_` pour la source et `DST_` pour la destination :

| Variable | Exemple |
|---|---|
| `*_ENDPOINT_URL` | `https://s3.fr-par.scw.cloud`, `https://cellar-c2.services.clever-cloud.com` |
| `*_ACCESS_KEY_ID` / `*_SECRET_ACCESS_KEY` | clés d'accès |
| `*_REGION` | `fr-par`, `us-east-1` |
| `*_BUCKET` | nom du bucket |
| `*_ADDRESSING_STYLE` | `auto` (défaut) ou `path` |

## Structure

| Module | Rôle |
|---|---|
| `config.py` | Endpoint S3 lu depuis l'environnement (`SRC_*`, `DST_*`) |
| `client.py` | Client boto3 compatible S3 non-AWS |
| `inventory.py` | Listing des objets et diff source / destination |
| `transfer.py` | Copie en flux et en parallèle |
| `cli.py` | Commandes `check`, `diff`, `sync`, `verify` |

## Développement

```bash
uv sync
uv run pre-commit install
uv run pytest
```
