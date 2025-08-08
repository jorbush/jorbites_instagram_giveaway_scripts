#!/usr/bin/env python3
import argparse
import csv
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


JORBITES_RECIPE_REGEX = re.compile(r"https?://(?:www\.)?jorbites\.com/recipes/([A-Za-z0-9_-]+)", re.IGNORECASE)


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
        raise ValueError("Unsupported Instagram URL format. Expected /p/{shortcode} or /reel/{shortcode}.")
    try:
        return parts[idx + 1]
    except Exception as exc:
        raise ValueError("Could not extract shortcode from URL") from exc


def create_loader(session_username: Optional[str], sessionfile: Optional[str], login_username: Optional[str], login_password: Optional[str]) -> Instaloader:
    loader = instaloader.Instaloader(download_pictures=False, download_videos=False, download_video_thumbnails=False, save_metadata=False, compress_json=False)

    # Attempt session load first if provided
    if session_username and sessionfile and os.path.exists(sessionfile):
        try:
            loader.load_session_from_file(session_username, filename=sessionfile)
            return loader
        except Exception:
            pass

    # Fallback to login if credentials provided
    if login_username and login_password:
        loader.login(login_username, login_password)
        # Save session if path provided
        if sessionfile:
            try:
                loader.save_session_to_file(filename=sessionfile)
            except Exception:
                pass
        return loader

    # If session username provided but no session file, try loading default filename
    if session_username and sessionfile and not os.path.exists(sessionfile):
        try:
            loader.load_session_from_file(session_username)
            return loader
        except Exception:
            pass

    # No session and no login; proceed unauthenticated (likely limited)
    return loader


def fetch_post_and_comments(loader: Instaloader, shortcode: str) -> Tuple[Post, List[Any]]:
    context = loader.context
    post = Post.from_shortcode(context, shortcode)
    # Ensure we are logged in for comments; raises if not
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
        username = getattr(c.owner, "username", None) if hasattr(c, "owner") else None
        if username is None:
            username = getattr(c, "owner", None)
        user_id = getattr(c.owner, "userid", None) if hasattr(c, "owner") else None
        if not username:
            continue

        recipe_ids = parse_recipe_ids_from_text(getattr(c, "text", ""))
        if not recipe_ids:
            continue

        created_at_attr = getattr(c, "created_at_utc", None)
        if hasattr(created_at_attr, "timestamp"):
            created_at = datetime.utcfromtimestamp(created_at_attr.timestamp()).isoformat() + "Z"
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
        p.probability = (p.entry_count / total_entries) if total_entries > 0 else 0.0

    return participants


def write_csv(output_csv: str, participants: Dict[str, Participant]) -> None:
    fieldnames = [
        "username",
        "user_id",
        "entry_count",
        "probability",
        "comment_ids",
        "recipe_ids_posted",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for participant in sorted(participants.values(), key=lambda p: (-p.probability, p.username)):
            all_comment_ids = [str(c.comment_id) for c in participant.comments]
            all_recipes = []
            for c in participant.comments:
                all_recipes.extend(c.recipe_ids)
            writer.writerow(
                {
                    "username": participant.username,
                    "user_id": participant.user_id or "",
                    "entry_count": participant.entry_count,
                    "probability": f"{participant.probability:.6f}",
                    "comment_ids": ",".join(all_comment_ids),
                    "recipe_ids_posted": ",".join(sorted(set(all_recipes))),
                }
            )


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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute participants and probabilities for a Jorbites Instagram giveaway by parsing recipe links in comments."
    )
    parser.add_argument("--post-url", required=True, help="Instagram post URL of the giveaway (e.g., https://www.instagram.com/p/SHORTCODE/)")

    auth = parser.add_argument_group("Authentication")
    auth.add_argument("--session-username", default=os.getenv("IG_SESSION_USERNAME"), help="Instagram username used to load/save session.")
    auth.add_argument("--session-file", default=os.getenv("IG_SESSION_FILE", ".insta_session"), help="Path to session file to load/save.")
    auth.add_argument("--login-username", default=os.getenv("IG_USERNAME"), help="Instagram login username (fallback if no valid session).")
    auth.add_argument("--login-password", default=os.getenv("IG_PASSWORD"), help="Instagram login password (fallback if no valid session).")

    logic = parser.add_argument_group("Counting logic")
    logic.add_argument("--dedupe-recipes-per-user", action="store_true", help="Count only unique recipe IDs per user across all comments.")
    logic.add_argument(
        "--count-multiple-links-per-comment",
        action="store_true",
        help="If a comment contains multiple recipe links, count each as an entry (ignored if --dedupe-recipes-per-user).",
    )

    output = parser.add_argument_group("Output")
    output.add_argument("--out-csv", default="participants.csv", help="Path to write CSV summary.")
    output.add_argument("--out-json", default="participants.json", help="Path to write JSON details.")

    args = parser.parse_args(argv)

    shortcode = extract_shortcode_from_url(args.post_url)

    loader = create_loader(
        session_username=args.session_username,
        sessionfile=args.session_file,
        login_username=args.login_username,
        login_password=args.login_password,
    )

    post, comments = fetch_post_and_comments(loader, shortcode)

    participants = build_participants(
        comments=comments,
        count_multiple_links_per_comment=args.count_multiple_links_per_comment,
        dedupe_recipes_per_user=args.dedupe_recipes_per_user,
    )

    # Write outputs
    write_csv(args.out_csv, participants)
    write_json(args.out_json, participants)

    # Human-readable console output
    total_entries = sum(p.entry_count for p in participants.values())
    print(f"Post: https://www.instagram.com/p/{shortcode}/  | Total valid entries: {total_entries}")
    print("")
    print("Participants (sorted by probability):")
    print("username, entries, probability")
    for p in sorted(participants.values(), key=lambda x: (-x.probability, x.username)):
        print(f"{p.username}, {p.entry_count}, {p.probability:.2%}")

    print("")
    print(f"Wrote CSV: {args.out_csv}")
    print(f"Wrote JSON: {args.out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
