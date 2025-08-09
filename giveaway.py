#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any

# Load .env if present, before importing instaloader
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    import instaloader
    from instaloader import Instaloader, Post
except Exception as exc:
    print("Error: Failed to import instaloader. Did you install requirements?", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    sys.exit(1)


JORBITES_RECIPE_REGEX = re.compile(
    r"https?://(?:www\.)?jorbites\.com/recipes/([A-Za-z0-9_-]+)", re.IGNORECASE)


@dataclass
class CommentEntry:
    comment_id: int
    created_at_utc: str
    text: str
    recipe_ids: List[str]


@dataclass
class Participant:
    username: str
    user_id: Optional[int]
    comments: List[CommentEntry]
    entry_count: int
    probability: float


def extract_shortcode_from_url(url: str) -> str:
    url = url.split("?")[0].rstrip("/")
    parts = url.split("/")
    if "p" in parts:
        idx = parts.index("p")
    elif "reel" in parts:
        idx = parts.index("reel")
    else:
        raise ValueError(
            "Unsupported Instagram URL format. Expected /p/{shortcode} or /reel/{shortcode}.")
    try:
        return parts[idx + 1]
    except Exception as exc:
        raise ValueError("Could not extract shortcode from URL") from exc


def create_loader(login_username: str, login_password: str) -> Instaloader:
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        compress_json=False,
    )
    loader.login(login_username, login_password)
    return loader


def fetch_post_and_comments(loader: Instaloader, shortcode: str) -> Tuple[Post, List[Any]]:
    context = loader.context
    post = Post.from_shortcode(context, shortcode)
    comments = list(post.get_comments())
    return post, comments


def parse_recipe_ids_from_text(text: str) -> List[str]:
    return list({match.group(1) for match in JORBITES_RECIPE_REGEX.finditer(text or "")})


def build_participants(
    comments: List[Any],
    count_multiple_links_per_comment: bool,
    dedupe_recipes_per_user: bool,
) -> Dict[str, Participant]:
    participants: Dict[str, Participant] = {}
    user_to_unique_recipes: Dict[str, Set[str]] = {}

    for c in comments:
        username = getattr(c.owner, "username", None) if hasattr(
            c, "owner") else None
        if username is None:
            username = getattr(c, "owner", None)
        user_id = getattr(c.owner, "userid", None) if hasattr(
            c, "owner") else None
        if not username:
            continue

        recipe_ids = parse_recipe_ids_from_text(getattr(c, "text", ""))
        if not recipe_ids:
            continue

        created_at_attr = getattr(c, "created_at_utc", None)
        if hasattr(created_at_attr, "timestamp"):
            created_at = datetime.utcfromtimestamp(
                created_at_attr.timestamp()).isoformat() + "Z"
        else:
            created_at = datetime.utcnow().isoformat() + "Z"

        comment_id = getattr(c, "id", 0)
        comment_entry = CommentEntry(
            comment_id=comment_id,
            created_at_utc=created_at,
            text=getattr(c, "text", ""),
            recipe_ids=recipe_ids,
        )

        if username not in participants:
            participants[username] = Participant(
                username=username,
                user_id=user_id,
                comments=[],
                entry_count=0,
                probability=0.0,
            )
            user_to_unique_recipes[username] = set()

        participants[username].comments.append(comment_entry)

        if dedupe_recipes_per_user:
            before_count = len(user_to_unique_recipes[username])
            user_to_unique_recipes[username].update(recipe_ids)
            added = len(user_to_unique_recipes[username]) - before_count
            participants[username].entry_count += max(0, added)
        else:
            if count_multiple_links_per_comment:
                participants[username].entry_count += len(recipe_ids)
            else:
                participants[username].entry_count += 1

    participants = {u: p for u, p in participants.items() if p.entry_count > 0}

    total_entries = sum(p.entry_count for p in participants.values())
    for p in participants.values():
        p.probability = (
            p.entry_count / total_entries) if total_entries > 0 else 0.0

    return participants


def write_json(output_json: str, participants: Dict[str, Participant]) -> None:
    serializable = [
        {
            **asdict(p),
            "comments": [asdict(c) for c in p.comments],
        }
        for p in sorted(participants.values(), key=lambda p: (-p.probability, p.username))
    ]
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def print_participants_table(participants: Dict[str, Participant]) -> None:
    sorted_participants = sorted(
        participants.values(), key=lambda x: (-x.probability, x.username))
    headers = ["#", "username", "entries", "probability"]
    rows: List[List[str]] = []
    for idx, p in enumerate(sorted_participants, start=1):
        rows.append([str(idx), p.username, str(
            p.entry_count), f"{p.probability:.2%}"])

    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]

    indent = "  "
    top = indent + "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    header_row = indent + "│" + \
        "│".join(f" {h.ljust(w)} " for h, w in zip(headers, widths)) + "│"
    sep = indent + "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bottom = indent + "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    print(top)
    print(header_row)
    print(sep)
    for row in rows:
        print(indent + "│" +
              "│".join(f" {cell.ljust(w)} " for cell, w in zip(row, widths)) + "│")
    print(bottom)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute participants and probabilities for a Jorbites Instagram giveaway by parsing recipe links in comments."
    )
    parser.add_argument("--post-url", required=True,
                        help="Instagram post URL of the giveaway (e.g., https://www.instagram.com/p/SHORTCODE/)")

    auth = parser.add_argument_group("Authentication")
    auth.add_argument("--login-username", default=os.getenv("IG_USERNAME"),
                      help="Instagram login username (or set IG_USERNAME in .env)")
    auth.add_argument("--login-password", default=os.getenv("IG_PASSWORD"),
                      help="Instagram login password (or set IG_PASSWORD in .env)")

    logic = parser.add_argument_group("Counting logic")
    logic.add_argument("--dedupe-recipes-per-user", action="store_true",
                       help="Count only unique recipe IDs per user across all comments.")
    logic.add_argument(
        "--count-multiple-links-per-comment",
        action="store_true",
        help="If a comment contains multiple recipe links, count each as an entry (ignored if --dedupe-recipes-per-user).",
    )

    output = parser.add_argument_group("Output")
    output.add_argument("--out-json", default="participants.json",
                        help="Path to write JSON details.")

    args = parser.parse_args(argv)

    if not args.login_username or not args.login_password:
        print("Error: IG_USERNAME and IG_PASSWORD must be provided (via flags or .env).", file=sys.stderr)
        return 2

    shortcode = extract_shortcode_from_url(args.post_url)

    loader = create_loader(
        login_username=args.login_username,
        login_password=args.login_password,
    )

    post, comments = fetch_post_and_comments(loader, shortcode)

    participants = build_participants(
        comments=comments,
        count_multiple_links_per_comment=args.count_multiple_links_per_comment,
        dedupe_recipes_per_user=args.dedupe_recipes_per_user,
    )

    write_json(args.out_json, participants)

    # Minimal, polished terminal output: only the formatted table
    print_participants_table(participants)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
