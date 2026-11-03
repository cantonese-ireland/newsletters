#!/usr/bin/env python3
"""Turn exported MailerLite newsletters into a self-contained static archive.

Reads export/index.csv (made by export_newsletters.py) and adds any newsletters
not yet archived to the archive folder (the parent of this tools/ folder):
  index.html                       list of all newsletters, newest first
  newsletters.json                 what's been archived (id, date, subject, file)
  newsletters/<date>-<subject>.html
  assets/<hash>.<ext>              every image, stylesheet and font, stored locally

Each page is rewritten so it loads nothing from MailerLite (or anywhere else):
  - images, CSS and fonts are downloaded and linked by relative path
  - <script> tags, tracking pixels and unsubscribe/preference links are removed
  - click-tracking links are unwrapped to their real destination when the
    destination is embedded in the URL (links are never visited, so nothing
    is clicked or unsubscribed by running this)

Usage:
  python3 tools/build_archive.py                 # sent newsletters only
  python3 tools/build_archive.py --include-drafts
"""

import argparse
import csv
import hashlib
import html
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# This script lives in <archive>/tools/; the archive is the folder above it.
ARCHIVE = Path(__file__).resolve().parent.parent
EXPORT = ARCHIVE / "export"
ASSETS = ARCHIVE / "assets"
PAGES = ARCHIVE / "newsletters"
MANIFEST = ARCHIVE / "newsletters.json"
TITLE = "Cantonese in Ireland Newsletter Archive"

MAILERLITE_HOSTS = ("mailerlite.com", "mlsend.com", "mlcdn.com", "mlsend2.com", "mailerlite.io")
DEAD_LINK_WORDS = ("unsubscribe", "preferences", "forget", "webview", "/preview/")

# Attributes that load a resource (as opposed to links the reader clicks).
RESOURCE_ATTR = re.compile(r"""(\s(?:src|background|poster|data-src)\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
SRCSET_ATTR = re.compile(r"""(\ssrcset\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
HREF_ATTR = re.compile(r"""(\shref\s*=\s*)(["'])(.*?)\2""", re.I | re.S)
CSS_URL = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""@import\s+(["'])(.*?)\1""", re.I)
SCRIPT = re.compile(r"<script\b.*?</script\s*>", re.I | re.S)
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.I | re.S)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ML_PLACEHOLDER = re.compile(r"\{\$[a-z_]+\}", re.I)
BRANDING_ROW = re.compile(r"""<tr\b[^>]*class=["'][^"']*ml-hide-branding[^"']*["'][^>]*>.*?</tr\s*>""", re.I | re.S)


def is_mailerlite(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in MAILERLITE_HOSTS)


class AssetStore:
    """Downloads each external resource once and returns its local path."""

    def __init__(self):
        self.cache = {}
        self.failed = set()

    def fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (archive builder)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return resp.read(), resp.headers.get_content_type()
            except (TimeoutError, urllib.error.URLError) as e:
                if isinstance(e, urllib.error.HTTPError) or attempt == 2:
                    raise

    def local(self, url, base_url=None):
        """Return the archive-relative path ('assets/x.png') for url, or None."""
        url = html.unescape(url.strip())
        if base_url:
            url = urllib.parse.urljoin(base_url, url)
        if url.startswith("//"):
            url = "https:" + url
        if not url.lower().startswith(("http://", "https://")):
            return None
        if url in self.cache:
            return self.cache[url]
        if url in self.failed:
            return None

        stem = hashlib.sha1(url.encode()).hexdigest()[:16]
        existing = next(ASSETS.glob(stem + ".*"), None)
        if existing:  # downloaded on an earlier run; keeps working even if the original is deleted
            self.cache[url] = f"assets/{existing.name}"
            return self.cache[url]
        try:
            data, ctype = self.fetch(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            print(f"    could not download {url}: {e}")
            self.failed.add(url)
            return None

        ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext):
            ext = mimetypes.guess_extension(ctype or "") or ".bin"
        path = f"assets/{stem}{ext}"
        self.cache[url] = path  # set before recursing so CSS cycles terminate

        if ctype == "text/css" or ext == ".css":
            css = data.decode("utf-8", errors="replace")
            # Paths inside a stylesheet are relative to the stylesheet (same folder).
            css = rewrite_css(css, self, base_url=url, prefix="")
            data = css.encode("utf-8")
        (ARCHIVE / path).write_bytes(data)
        return path


def rewrite_css(css, store, base_url=None, prefix="../"):
    def repl_url(m):
        local = store.local(m.group(2), base_url)
        if local:
            return f'url("{prefix}{local}")'
        url = urllib.parse.urljoin(base_url or "", html.unescape(m.group(2).strip()))
        return "none" if url in store.failed else m.group(0)

    def repl_import(m):
        local = store.local(m.group(2), base_url)
        return f'@import "{prefix}{local}"' if local else m.group(0)

    css = CSS_IMPORT.sub(repl_import, css)
    return CSS_URL.sub(repl_url, css)


def unwrap_tracking(url):
    """Pull the real destination out of a click-tracking URL, if it's in there."""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    for key in ("url", "u", "redirect", "target", "destination", "link"):
        for value in query.get(key, []):
            if value.lower().startswith(("http://", "https://")) and not is_mailerlite(value):
                return value
    return None


def clean_links(page, report):
    def repl(m):
        attrs, inner = m.group(1), m.group(2)
        href_m = HREF_ATTR.search(attrs)
        if not href_m:
            return m.group(0)
        href = html.unescape(href_m.group(3).strip())
        if ML_PLACEHOLDER.search(href) or (is_mailerlite(href) and any(w in href.lower() for w in DEAD_LINK_WORDS)):
            return ""  # unsubscribe / view-in-browser / preferences: meaningless in an archive
        if is_mailerlite(href):
            real = unwrap_tracking(href)
            if real:
                new = f'{href_m.group(1)}{href_m.group(2)}{html.escape(real, quote=True)}{href_m.group(2)}'
                return f"<a{attrs[:href_m.start()]}{new}{attrs[href_m.end():]}>{inner}</a>"
            report.append(href)
        return m.group(0)

    return ANCHOR.sub(repl, page)


def remove_tracking_pixels(page):
    def repl(m):
        tag = m.group(0)
        tiny = re.search(r"""width\s*=\s*["']?1["'\s>]""", tag, re.I) and re.search(r"""height\s*=\s*["']?1["'\s>]""", tag, re.I)
        src = re.search(r"""src\s*=\s*["']([^"']*)""", tag, re.I)
        tracker = src and is_mailerlite(src.group(1)) and re.search(r"open|track|pixel", src.group(1), re.I)
        return "" if tiny or tracker else tag

    return IMG_TAG.sub(repl, page)


def remove_dead_images(page, store):
    """Drop <img> tags whose image no longer exists (e.g. deleted from MailerLite)."""
    def repl(m):
        src = re.search(r"""src\s*=\s*["']([^"']*)""", m.group(0), re.I)
        return "" if src and html.unescape(src.group(1).strip()) in store.failed else m.group(0)

    return IMG_TAG.sub(repl, page)


def localise(page, store):
    page = SCRIPT.sub("", page)
    page = BRANDING_ROW.sub("", page)  # "Sent by MailerLite" badge
    page = remove_tracking_pixels(page)

    def repl_attr(m):
        local = store.local(m.group(3))
        if local:
            return f"{m.group(1)}{m.group(2)}../{local}{m.group(2)}"
        if "background" in m.group(1).lower() and html.unescape(m.group(3).strip()) in store.failed:
            return ""  # dead background image; the bgcolor fallback still applies
        return m.group(0)

    def repl_srcset(m):
        parts = []
        for item in m.group(3).split(","):
            bits = item.strip().split()
            if bits:
                local = store.local(bits[0])
                parts.append(" ".join([f"../{local}" if local else bits[0]] + bits[1:]))
        return f"{m.group(1)}{m.group(2)}{', '.join(parts)}{m.group(2)}"

    def repl_link(m):
        tag = m.group(0)
        if not re.search(r"""rel\s*=\s*["']?[^"'>]*\b(stylesheet|icon|shortcut)\b""", tag, re.I):
            if re.search(r"""rel\s*=\s*["']?[^"'>]*\b(preconnect|dns-prefetch|preload|prefetch)\b""", tag, re.I):
                return ""  # just a hint to contact a server; not needed offline
            return tag
        return HREF_ATTR.sub(repl_attr, tag)

    page = RESOURCE_ATTR.sub(repl_attr, page)
    page = SRCSET_ATTR.sub(repl_srcset, page)
    page = LINK_TAG.sub(repl_link, page)
    # Inline <style> blocks and style="" attributes both use url(...)
    page = CSS_URL.sub(lambda m: rewrite_css(m.group(0), store), page)
    page = CSS_IMPORT.sub(lambda m: rewrite_css(m.group(0), store), page)
    return remove_dead_images(page, store)


def build_index(entries):
    rows = "\n".join(
        f'    <li><time>{html.escape(e["date"] or "")}</time> '
        f'<a href="newsletters/{html.escape(e["file"])}">{html.escape(e["subject"])}</a>'
        + (f' <span class="tag">{html.escape(e["status"])}</span>' if e["status"] != "sent" else "")
        + "</li>"
        for e in entries
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.5 system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 16px; }}
  h1 {{ font-size: 1.6rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ padding: .5rem 0; border-bottom: 1px solid #8884; display: flex; gap: 1rem; align-items: baseline; }}
  time {{ font-variant-numeric: tabular-nums; opacity: .7; white-space: nowrap; }}
  .tag {{ font-size: .75rem; opacity: .7; border: 1px solid currentColor; border-radius: 4px; padding: 0 .3rem; }}
</style>
</head>
<body>
<h1>{TITLE}</h1>
<p>{len(entries)} newsletters</p>
<ul>
{rows}
</ul>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--include-drafts", action="store_true", help="also archive draft and scheduled campaigns")
    parser.add_argument("--export", type=Path, default=EXPORT, help=f"folder made by export_newsletters.py (default: {EXPORT})")
    args = parser.parse_args()

    index_csv = args.export / "index.csv"
    if not index_csv.exists():
        sys.exit(f"{index_csv} not found. Run export_newsletters.py first.")

    statuses = {"sent", "draft", "ready"} if args.include_drafts else {"sent"}
    with open(index_csv, newline="", encoding="utf-8") as f:
        campaigns = [r for r in csv.DictReader(f) if r["status"] in statuses and r["html_file"]]

    # The archive only grows: newsletters already in the manifest are kept as they are,
    # even if they've since been deleted from MailerLite.
    entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    archived = {e["id"] for e in entries}
    new = [c for c in campaigns if c["id"] not in archived]
    PAGES.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    store = AssetStore()
    leftover = {}
    for c in sorted(new, key=lambda r: r["date"]):
        src = args.export / c["html_file"]
        print(f"  {c['date'] or '----------'}  {c['subject']}")
        report = []
        page = localise(src.read_text(encoding="utf-8", errors="replace"), store)
        page = clean_links(page, report)
        name = Path(c["html_file"]).name
        (PAGES / name).write_text(page, encoding="utf-8")
        entries.append({"id": c["id"], "date": c["date"], "subject": c["subject"], "status": c["status"], "file": name})
        if report:
            leftover[name] = report

    entries.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ARCHIVE / "index.html").write_text(build_index(entries), encoding="utf-8")
    (ARCHIVE / ".nojekyll").write_text("")  # serve as-is on GitHub Pages

    print(f"\nDone: {len(new)} new, {len(entries)} newsletters in total in {ARCHIVE}")
    if store.failed:
        print(f"{len(store.failed)} assets could not be downloaded (removed from the pages).")
    if leftover:
        print("\nLinks still pointing at MailerLite (tracking links whose destination isn't visible in the URL):")
        for name, links in leftover.items():
            for link in links:
                print(f"  {name}: {link}")


if __name__ == "__main__":
    main()
