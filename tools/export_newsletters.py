#!/usr/bin/env python3
"""Export every MailerLite campaign (sent, draft, scheduled) to local files.

Output (in export/ next to the tools/ folder, or --out):
  index.csv                         one row per campaign
  <status>/<date>-<subject>.html    the newsletter's HTML
  <status>/<date>-<subject>.json    the full API response for that campaign

With --only-new, campaigns already listed in newsletters.json (the archive's
manifest) are skipped, so only new newsletters are downloaded.

Uses only the Python standard library. Reads the token from the
MAILERLITE_TOKEN environment variable, or from a .env file in the current
folder, the archive folder or the folder above it.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://connect.mailerlite.com/api"
STATUSES = ["sent", "draft", "ready"]  # "ready" = scheduled / ready to send
ARCHIVE = Path(__file__).resolve().parent.parent
MANIFEST = ARCHIVE / "newsletters.json"


def load_token():
    token = os.environ.get("MAILERLITE_TOKEN", "").strip()
    env_files = [Path.cwd() / ".env", ARCHIVE / ".env", ARCHIVE.parent / ".env"]
    for env_file in env_files:
        if token:
            break
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "MAILERLITE_TOKEN":
                    token = value.strip().strip('"').strip("'")
    if not token:
        sys.exit("No token found. Set MAILERLITE_TOKEN or put MAILERLITE_TOKEN=... in a .env file.")
    return token


def request(url, token=None):
    """GET a URL, retrying on rate limits. Returns the response body as text."""
    headers = {"Accept": "application/json", "User-Agent": "mailerlite-export"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 10)
                print(f"  rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            if e.code == 401:
                sys.exit("MailerLite rejected the token (401). Check the value in .env.")
            raise
    raise RuntimeError(f"Gave up after repeated rate limits: {url}")


def api_get(path, token, **params):
    query = urllib.parse.urlencode(params)
    return json.loads(request(f"{API}{path}?{query}" if query else f"{API}{path}", token))


def list_campaigns(token, status):
    page = 1
    while True:
        data = api_get("/campaigns", token, **{"filter[status]": status, "limit": 100, "page": page})
        yield from data.get("data", [])
        if page >= (data.get("meta") or {}).get("last_page", 1):
            break
        page += 1


def slugify(text, max_len=60):
    text = re.sub(r"[^\w\s-]", "", text or "untitled").strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:max_len].strip("-") or "untitled"


def campaign_html(campaign):
    """Get the HTML from the API response, or fall back to the preview page."""
    for email in campaign.get("emails") or []:
        for key in ("content", "html", "html_content"):
            if email.get(key):
                return email[key]
    for email in campaign.get("emails") or []:
        if email.get("preview_url"):
            return request(email["preview_url"])
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ARCHIVE / "export", help="output folder")
    parser.add_argument("--only-new", action="store_true", help="skip campaigns already in newsletters.json")
    args = parser.parse_args()

    token = load_token()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    skip = set()
    if args.only_new and MANIFEST.exists():
        skip = {e["id"] for e in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    rows = []

    for status in STATUSES:
        print(f"Fetching {status} campaigns...")
        for summary in list_campaigns(token, status):
            if summary["id"] in skip:
                continue
            campaign = api_get(f"/campaigns/{summary['id']}", token).get("data", summary)
            email = (campaign.get("emails") or [{}])[0]
            subject = email.get("subject") or campaign.get("name") or "untitled"
            date = (campaign.get("finished_at") or campaign.get("scheduled_for")
                    or campaign.get("created_at") or "")[:10]
            base = f"{date}-{slugify(subject)}-{campaign['id']}" if date else f"{slugify(subject)}-{campaign['id']}"

            folder = out / status
            folder.mkdir(exist_ok=True)
            (folder / f"{base}.json").write_text(json.dumps(campaign, indent=2, ensure_ascii=False))

            html = campaign_html(campaign)
            html_file = ""
            if html:
                (folder / f"{base}.html").write_text(html)
                html_file = f"{status}/{base}.html"
            print(f"  {date or '----------'}  {subject}" + ("" if html else "  (no HTML found)"))

            rows.append({
                "id": campaign.get("id"),
                "status": status,
                "date": date,
                "name": campaign.get("name"),
                "subject": subject,
                "from": email.get("from"),
                "preview_url": email.get("preview_url"),
                "html_file": html_file,
            })
            time.sleep(0.5)  # stay well under MailerLite's 120 requests/minute limit

    with open(out / "index.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "status", "date", "name", "subject", "from", "preview_url", "html_file"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone: {len(rows)} campaigns exported to {out}")


if __name__ == "__main__":
    main()
