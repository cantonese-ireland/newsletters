# Cantonese in Ireland Newsletter Archive

This repository is a permanent copy of every newsletter Cantonese in Ireland has sent through MailerLite, starting from August 2022.

**Browse the archive here:** https://cantonese-ireland.github.io/newsletters/

Every newsletter is kept in two forms:

- **A web page**, which looks just like the email did.
- **A PDF**, for printing, sharing or keeping offline.

The copies don't depend on MailerLite at all. All images are stored in this repository, so the archive keeps working even if a campaign is deleted from MailerLite or the MailerLite account is closed.

New newsletters are added automatically once a week. Nobody needs to do anything for this to happen.

---

## How it works

Every Monday, GitHub runs an automated job (a "workflow") that:

1. **Checks MailerLite** for newsletters that have been sent but aren't in the archive yet.
2. **Saves a copy of each new one** as a web page, along with all its images.
3. **Removes MailerLite-specific pieces** that wouldn't work in an archive: the "Sent by MailerLite" badge, unsubscribe and forward links, and invisible tracking images.
4. **Makes a PDF** of each new newsletter.
5. **Updates the list** of newsletters on the archive's home page.
6. **Saves everything to this repository**, and GitHub then republishes the website within a few minutes.

If there are no new newsletters, the job finishes in about a minute and changes nothing.

Newsletters already in the archive are **never changed or removed**, even if they are edited or deleted in MailerLite later.

Only newsletters that have actually been **sent** are archived. Drafts and scheduled campaigns are skipped.

### When it runs

- **Automatically:** every Monday at 06:00 UTC, which is 6am in Irish summer time and 7am in winter.
- **Whenever you like:** go to the **[Actions](https://github.com/cantonese-ireland/newsletters/actions)** tab, click **Update newsletter archive** on the left, then click **Run workflow** → **Run workflow**. This is handy right after sending a newsletter you want archived straight away.

### Changing when it runs

The schedule is set in [`.github/workflows/update-archive.yml`](.github/workflows/update-archive.yml), on this line:

```yaml
- cron: "0 6 * * 1" # every Monday at 06:00 UTC
```

The five values are *minute, hour, day of month, month, day of week*, and times are in UTC. Some examples:

| Schedule | Line to use |
|---|---|
| Every Monday at 06:00 (current) | `"0 6 * * 1"` |
| Every day at 06:00 | `"0 6 * * *"` |
| 1st of every month at 06:00 | `"0 6 1 * *"` |

[crontab.guru](https://crontab.guru) explains any schedule in plain English.

---

## Setting up the MailerLite token

The workflow needs permission to read your newsletters from MailerLite. That permission is an **API token**, a long secret code that works like a password. It's stored safely in GitHub as a **secret**: once saved, nobody can read it back, not even repository admins, and it never appears in the files or logs.

The token is already set up. Follow these steps only if it stops working (see Troubleshooting) or you need to replace it.

### Step 1: Get a token from MailerLite

1. Sign in to [MailerLite](https://dashboard.mailerlite.com) with the account that sends the newsletters.
2. Click **Integrations** in the left menu.
3. Find **MailerLite API** and click **Use** (or **Manage**).
4. Click **Generate new token**, give it a name you'll recognise (for example `GitHub newsletter archive`), and confirm.
5. **Copy the token now.** MailerLite only shows it once. If you lose it, just generate a new one.

### Step 2: Save it in GitHub

You need to be an admin of this repository.

1. Open this repository on GitHub and click **Settings** (top right of the repository page).
2. In the left menu, click **Secrets and variables** → **Actions**.
3. Do one of the following:
   - If `MAILERLITE_TOKEN` is already listed, click the **pencil icon** next to it to replace it.
   - Otherwise, click **New repository secret** and enter `MAILERLITE_TOKEN` as the **Name**, spelled exactly like that.
4. Paste the token into **Secret** and click **Add secret** (or **Update secret**).
5. Check it works by running the workflow by hand (see "When it runs" above). A green tick means it worked.

If you replace a token, you can delete the old one in MailerLite on the same Integrations page.

---

## Troubleshooting

**The workflow shows a red cross.** Click on the failed run in the **Actions** tab, then on the step with the red cross, to see the error.

- *"MailerLite rejected the token (401)"*: the token has expired or been deleted. Create a new one and save it in GitHub (see above).
- *"No token found"*: the `MAILERLITE_TOKEN` secret is missing or misspelled.
- Anything else: try running the workflow again. Most other failures are temporary network problems. If it keeps failing, see the technical notes below, or give them to a developer or an AI assistant.

**The weekly run has stopped happening.** GitHub pauses scheduled workflows in public repositories that have had no activity for 60 days, which can happen if no newsletters are sent for a while. GitHub emails the repository admins when this happens. To turn it back on, go to **Actions** → **Update newsletter archive** and click **Enable workflow**.

**A new newsletter isn't on the website yet.** The workflow only runs on Mondays, so run it by hand. After it finishes, allow a few minutes for the website to update.

**Some images are missing from older newsletters.** About 110 images had already been deleted from MailerLite before this archive was created, so they couldn't be saved. They were removed from the pages. All images that still existed were saved.

---

## Technical reference

This section is for developers and AI assistants maintaining the repository.

### Repository layout

| Path | What it is |
|---|---|
| `index.html` | Home page listing every newsletter, newest first, with a link to its page and PDF. **Generated: don't edit by hand.** |
| `newsletters/<date>-<subject-slug>-<campaign-id>.html` | One self-contained page per newsletter. |
| `pdf/<same name>.pdf` | One PDF per newsletter. |
| `assets/<sha1-of-url, 16 hex chars>.<ext>` | Every image, stylesheet and font used by the pages, named by a hash of the original URL. |
| `newsletters.json` | Manifest of what has been archived: `[{id, date, subject, status, file}]`, newest first. This is the source of truth for "already archived". |
| `tools/export_newsletters.py` | Downloads campaigns from the MailerLite API. |
| `tools/build_archive.py` | Turns downloaded campaigns into self-contained pages, then updates `newsletters.json` and `index.html`. |
| `tools/make_pdfs.py` | Makes PDFs for manifest entries that don't have one, then rewrites `index.html`. |
| `.github/workflows/update-archive.yml` | The scheduled workflow. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |
| `export/` | Raw MailerLite downloads when running locally. Git-ignored; in CI they go to `$RUNNER_TEMP`. |

GitHub Pages serves the `main` branch from the repository root.

### Pipeline (workflow steps in order)

1. `export_newsletters.py --only-new --out $RUNNER_TEMP/export`
   - Calls `GET https://connect.mailerlite.com/api/campaigns?filter[status]=sent|draft|ready` (paginated, `limit=100`), then `GET /api/campaigns/{id}` for each campaign whose ID isn't in `newsletters.json`.
   - The HTML is taken from `emails[0].content` / `html` / `html_content` if present. Otherwise it fetches `emails[0].preview_url`, which is what happens in practice.
   - Writes `<out>/<status>/<name>.html`, `<name>.json` (the full API response) and `<out>/index.csv`.
   - Auth: `Authorization: Bearer $MAILERLITE_TOKEN`. The script retries on HTTP 429, sleeps 0.5 s between campaigns (the API limit is 120 requests per minute) and exits with a clear message on 401.
2. `build_archive.py --export $RUNNER_TEMP/export`
   - Reads `index.csv`, keeps `status == sent` (or all statuses with `--include-drafts`), and skips IDs already in the manifest.
   - For each new page, it:
     - strips `<script>`, `<tr class="ml-hide-branding">` (the MailerLite badge) and 1×1 or MailerLite tracking pixels;
     - downloads every `src` / `background` / `poster` / `data-src` / `srcset`, `<link rel=stylesheet|icon>`, CSS `url()` and `@import` into `assets/`, recursing into CSS files;
     - removes preconnect and prefetch hints;
     - drops `<a>` elements whose `href` contains a MailerLite merge tag (`{$unsubscribe}`, `{$forward}`, `{$url}`, `{$share_url}`, …) or is a MailerLite unsubscribe/preferences/webview link;
     - unwraps click-tracking links only when the destination is in the query string. **Links are never visited**, so building can't unsubscribe anyone or register clicks;
     - removes images that return 404 or fail after 3 attempts.
   - Assets already in `assets/` are reused without downloading (looked up by hash), so an asset downloaded once survives later deletion from MailerLite.
   - Appends to `newsletters.json`, sorted by `(date, id)` descending, and regenerates `index.html`.
3. Install `fonts-noto-cjk`, `fonts-noto-color-emoji` and `ghostscript` with apt. Without the fonts, Chinese text renders as empty boxes in the PDFs.
4. `make_pdfs.py`
   - For each manifest entry without `pdf/<name>.pdf`, it writes a temporary copy of the page next to the original (so `../assets/` paths still resolve), with CSS for A4 pages, 10 mm margins and `print-color-adjust: exact`.
   - It prints that copy with `google-chrome --headless=new --print-to-pdf` (preinstalled on `ubuntu-latest`; override with `CHROME_BIN`).
   - It then compresses the result with `gs -dPDFSETTINGS=/ebook`, which downsamples images to 150 dpi. Chrome embeds images at full resolution, so uncompressed PDFs were 445 MB in total, with one at 53 MB. Compressed, they total about 52 MB, with none over about 2 MB.
   - Finally it rewrites `index.html` so each entry links to its PDF.
5. Commit with `git add -A` and push as `github-actions[bot]` if anything changed, then `POST /repos/{repo}/pages/builds`, because pushes made with `GITHUB_TOKEN` don't always trigger a Pages build.

### Invariants to keep

- **The archive is append-only.** Existing pages, PDFs and assets are never regenerated or deleted by the workflow. To regenerate something, delete it in a commit: a deleted PDF is rebuilt on the next run, and a page is rebuilt if its entry is also removed from `newsletters.json` and the campaign still exists in MailerLite.
- **Pages must not load anything from MailerLite or any other host.** To check, open a page and confirm `performance.getEntriesByType('resource')` lists only same-origin URLs, or run `grep -E 'mlcdn|mailerlite|mlsend' newsletters/*.html`. The only expected matches are a few links to MailerLite-hosted survey/sign-up forms (`dashboard.mailerlite.com/forms/...`), deliberately kept as content.
- **Re-running is idempotent.** With nothing new in MailerLite, a run must produce no diff.
- **Only the standard library.** The Python scripts use only the standard library (Python 3.12 in CI), and the external tools are Chrome and Ghostscript. Keep it that way so the workflow stays simple.
- **The token is only ever read from the environment** (`MAILERLITE_TOKEN`) or a git-ignored `.env`. Never commit it.

### Configuration

| Setting | Where | Notes |
|---|---|---|
| `MAILERLITE_TOKEN` | Repository secret (Settings → Secrets and variables → Actions) | MailerLite API token. Required. |
| Schedule | `cron` in `.github/workflows/update-archive.yml` | UTC. |
| Home page title | `TITLE` in `tools/build_archive.py` | |
| Drafts and scheduled campaigns | `--include-drafts` flag on `build_archive.py` | Off by default. |
| PDF page size and margins | `PRINT_STYLE` in `tools/make_pdfs.py` | |
| PDF image quality | `-dPDFSETTINGS=/ebook` in `tools/make_pdfs.py` | `/printer` gives 300 dpi and bigger files. |

### Running locally

You need Python 3, plus Chrome and Ghostscript for the PDFs (`brew install ghostscript` on macOS).

```bash
echo "MAILERLITE_TOKEN=your-token" > .env       # git-ignored
python3 tools/export_newsletters.py --only-new  # writes export/
python3 tools/build_archive.py                  # reads export/
python3 tools/make_pdfs.py
```

To test the "new newsletter" path without waiting for one, remove the newest entry from `newsletters.json` and delete its page in `newsletters/`, then run the three commands. The page should be recreated byte-identical. Afterwards, `git diff` should show nothing except the regenerated PDF.

### Known limitations

- About 110 images referenced by older campaigns already returned 404 from `storage.mlcdn.com` when the archive was created, so they were removed from those pages.
- The repository is about 300 MB, mostly images in `assets/`. GitHub Pages sites are limited to 1 GB, and individual files to 100 MB.
- Git history still contains a first, uncompressed set of PDFs (about 445 MB), which makes clones bigger. Rewriting history would remove them, but it needs a force-push.
- The page and PDF filename comes from the subject at archive time. Renaming a campaign in MailerLite later doesn't rename the archived files.
