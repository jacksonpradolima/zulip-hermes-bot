from __future__ import annotations

import argparse
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import zulip
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

ZULIP_SITE_URL = os.getenv("ZULIP_SITE_URL", "").rstrip("/")
ZULIP_BOT_EMAIL = os.getenv("ZULIP_BOT_EMAIL", "")
ZULIP_API_KEY = os.getenv("ZULIP_API_KEY", "")

TIMEZONE = ZoneInfo("America/Sao_Paulo")


def html_to_text(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def get_client() -> zulip.Client:
    if not ZULIP_SITE_URL or not ZULIP_BOT_EMAIL or not ZULIP_API_KEY:
        raise SystemExit("Missing ZULIP_SITE_URL, ZULIP_BOT_EMAIL, or ZULIP_API_KEY in .env")

    return zulip.Client(
        site=ZULIP_SITE_URL,
        email=ZULIP_BOT_EMAIL,
        api_key=ZULIP_API_KEY,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", required=True)
    parser.add_argument("--topic")
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--query")
    args = parser.parse_args()

    client = get_client()

    today = datetime.now(TIMEZONE).date()

    narrow = [
        {"operator": "stream", "operand": args.channel},
    ]

    if args.topic:
        narrow.append({"operator": "topic", "operand": args.topic})

    if args.query:
        narrow.append({"operator": "search", "operand": args.query})

    result = client.get_messages(
        {
            "anchor": "newest",
            "num_before": min(args.limit, 5000),
            "num_after": 0,
            "narrow": narrow,
        }
    )

    if result.get("result") != "success":
        raise SystemExit(f"Zulip API error: {result}")

    messages = result.get("messages", [])

    print("# Zulip context")
    print(f"Channel: {args.channel}")

    if args.topic:
        print(f"Topic: {args.topic}")

    if args.today:
        print(f"Date: {today.isoformat()}")

    if args.query:
        print(f"Search: {args.query}")

    print()

    count = 0

    for msg in messages:
        ts = datetime.fromtimestamp(msg["timestamp"], TIMEZONE)

        if args.today and ts.date() != today:
            continue

        sender = msg.get("sender_full_name") or msg.get("sender_email") or "Unknown"
        topic = msg.get("subject") or msg.get("topic") or ""
        content = html_to_text(msg.get("content", ""))

        if not content:
            continue

        print(f"- [{ts.strftime('%Y-%m-%d %H:%M')}] {sender} | {topic}: {content}")
        count += 1

    if count == 0:
        print("No messages matched this filter.")


if __name__ == "__main__":
    main()
