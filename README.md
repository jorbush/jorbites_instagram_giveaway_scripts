# Jorbites Instagram Giveaway Helper

A small CLI that fetches comments from an Instagram giveaway post, extracts `jorbites.com/recipes/{id}` links, tallies valid entries per user, and computes each participant's probability of winning.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Optionally set credentials via env vars:

- `IG_SESSION_USERNAME` and `IG_SESSION_FILE` (recommended; a session is saved/loaded)
- `IG_USERNAME` and `IG_PASSWORD` (fallback if session not available)

## Usage

```bash
python giveaway.py \
  --post-url "https://www.instagram.com/p/DNDunraMPPb/" \
  --dedupe-recipes-per-user \
  --out-csv participants.csv \
  --out-json participants.json
```

Flags:
- `--dedupe-recipes-per-user`: Count unique recipe IDs per user (suggested to ensure "new recipes").
- `--count-multiple-links-per-comment`: If a comment has multiple recipe links, count each as an entry. Ignored when deduping per user.

Outputs:
- CSV summary to `participants.csv`
- JSON with detailed comments to `participants.json`
# jorbites_instagram_giveaway_scripts
