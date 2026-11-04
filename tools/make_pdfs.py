#!/usr/bin/env python3
"""Save a PDF of every archived newsletter that doesn't have one yet.

Writes pdf/<same name as the page>.pdf for each entry in newsletters.json,
then rewrites index.html so each newsletter links to its PDF.

Needs Google Chrome or Chromium (set CHROME_BIN to point at it if it isn't
found automatically), and Ghostscript (gs) to compress the PDFs. Uses only
the Python standard library otherwise.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from build_archive import ARCHIVE, MANIFEST, PAGES, build_index

PDFS = ARCHIVE / "pdf"

# Print backgrounds and colours exactly as on screen, on A4 pages.
PRINT_STYLE = """<style>
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  @page { size: A4; margin: 10mm; }
</style>"""

CHROME_CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome():
    for candidate in [os.environ.get("CHROME_BIN")] + CHROME_CANDIDATES:
        if candidate and (shutil.which(candidate) or Path(candidate).exists()):
            return shutil.which(candidate) or candidate
    sys.exit("Chrome not found. Install Google Chrome or set CHROME_BIN.")


def render(chrome, page, pdf):
    # Print a copy of the page with the print style added. It sits next to the
    # original so the relative links to ../assets/ still work.
    html = page.read_text(encoding="utf-8")
    head_end = html.lower().find("</head>")
    html = html[:head_end] + PRINT_STYLE + html[head_end:] if head_end != -1 else PRINT_STYLE + html
    tmp = page.with_name(f".print-{page.name}")
    raw = pdf.with_name(f".raw-{pdf.name}")
    tmp.write_text(html, encoding="utf-8")
    try:
        subprocess.run(
            [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
             "--virtual-time-budget=10000", f"--print-to-pdf={raw}", tmp.as_uri()],
            check=True, capture_output=True, timeout=180,
        )
        compress(raw, pdf)
    finally:
        tmp.unlink(missing_ok=True)
        raw.unlink(missing_ok=True)


def compress(raw, pdf):
    """Shrink images to 150 dpi with Ghostscript; Chrome embeds them at full size (often 30x bigger)."""
    gs = shutil.which("gs")
    if not gs:
        print("    Ghostscript not found, saving uncompressed PDF")
        raw.replace(pdf)
        return
    subprocess.run(
        [gs, "-q", "-sDEVICE=pdfwrite", "-dPDFSETTINGS=/ebook", "-dNOPAUSE", "-dBATCH", "-o", str(pdf), str(raw)],
        check=True, capture_output=True, timeout=300,
    )


def main():
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    PDFS.mkdir(exist_ok=True)
    todo = [e for e in entries if not (PDFS / pdf_name(e)).exists()]
    if todo:
        chrome = find_chrome()
    failed = 0
    for e in todo:
        print(f"  {e['date'] or '----------'}  {e['subject']}")
        try:
            render(chrome, PAGES / e["file"], PDFS / pdf_name(e))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
            failed += 1
            print(f"    failed: {err}")

    (ARCHIVE / "index.html").write_text(build_index(entries), encoding="utf-8")
    print(f"\nDone: {len(todo) - failed} PDFs made, {failed} failed, "
          f"{len(list(PDFS.glob('*.pdf')))} in total in {PDFS}")
    if failed:
        sys.exit(1)


def pdf_name(entry):
    return Path(entry["file"]).with_suffix(".pdf").name


if __name__ == "__main__":
    main()
