# Jorbites Instagram Giveaway Helper

Fetch comments from an Instagram giveaway post, extract `jorbites.com/recipes/{id}` links, tally valid entries per user, and compute each participant's probability of winning.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Provide credentials via `.env` (auto-loaded):

```
IG_USERNAME=your_username
IG_PASSWORD=your_password
```

## Usage

```bash
python giveaway.py \
  --post-url "https://www.instagram.com/p/DNDunraMPPb/" \
  --dedupe-recipes-per-user \
  --out-json participants.json
```

Flags:
- `--dedupe-recipes-per-user`: Count unique recipe IDs per user (suggested for "new recipes").
- `--count-multiple-links-per-comment`: If a comment has multiple recipe links, count each as an entry. Ignored when deduping per user.

Output:
- JSON with detailed participants and comments to `participants.json`.

Notes:
- Script logs in using `IG_USERNAME`/`IG_PASSWORD`. No session files are used.
