#!/usr/bin/env python3
import argparse
import os
import sys
import random
from typing import List, Tuple, Optional

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from giveaway import (
        create_loader,
        extract_shortcode_from_url,
        fetch_post_and_comments,
        build_participants,
        Participant,
        CommentEntry,
    )
except Exception as exc:
    print("Error: Failed to import from giveaway.py.", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    sys.exit(1)


def choose_weighted_winners(
    participants: List[Participant],
) -> List[Tuple[Participant, CommentEntry]]:
    rng = random.Random()
    eligible = [p for p in participants if p.entry_count > 0]
    if not eligible:
        return []
    weights = [p.entry_count for p in eligible]
    selected = rng.choices(eligible, weights=weights, k=1)[0]
    winning_comment = rng.choice(selected.comments)
    return [(selected, winning_comment)]


def print_winners_box(winners: List[Tuple[Participant, CommentEntry]]) -> None:
    if not winners:
        print("No eligible participants found.")
        return

    lines: List[str] = []
    for i, (p, c) in enumerate(winners, start=1):
        lines.append(f"winner: {p.username}")
        lines.append(f"  entries: {p.entry_count}")
        lines.append(f"  winning_comment_id: {c.comment_id}")

    indent = "  "
    width = max(len(s) for s in lines)
    top = indent + "┌" + "─" * (width + 2) + "┐"
    bottom = indent + "└" + "─" * (width + 2) + "┘"
    print(f"\n")
    print(top)
    for s in lines:
        print(indent + "│ " + s.ljust(width) + " │")
    print(bottom)
    print(f"\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pick a weighted random winner for a Jorbites Instagram giveaway (1 entry per valid comment)."
    )
    parser.add_argument("--post-url", required=True,
                        help="Instagram post URL, e.g. https://www.instagram.com/p/SHORTCODE/")

    auth = parser.add_argument_group("Authentication")
    auth.add_argument("--login-username", default=os.getenv("IG_USERNAME"),
                      help="Instagram login username (or set IG_USERNAME in .env)")
    auth.add_argument("--login-password", default=os.getenv("IG_PASSWORD"),
                      help="Instagram login password (or set IG_PASSWORD in .env)")

    args = parser.parse_args(argv)

    if not args.login_username or not args.login_password:
        print("Error: IG_USERNAME and IG_PASSWORD must be provided (via flags or .env).", file=sys.stderr)
        return 2

    shortcode = extract_shortcode_from_url(args.post_url)
    loader = create_loader(args.login_username, args.login_password)
    _, comments = fetch_post_and_comments(loader, shortcode)
    participants_map = build_participants(comments=comments)

    winners = choose_weighted_winners(list(participants_map.values()))
    print_winners_box(winners)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
