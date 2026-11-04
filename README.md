# Cantonese in Ireland Newsletter Archive

Every newsletter Cantonese in Ireland has sent since August 2022, saved as standalone web pages.

Open [`index.html`](index.html) for the full list. Each newsletter is in [`newsletters/`](newsletters/), and all of its images, stylesheets and fonts are in [`assets/`](assets/). The pages don't load anything from MailerLite or any other server, so they keep working even if the original campaigns are deleted.

Some images had already been deleted from MailerLite before this archive was made. Those images were removed from the pages.

Browse it online at https://cantonese-ireland.github.io/newsletters/

## Automatic updates

A GitHub Action ([`.github/workflows/update-archive.yml`](.github/workflows/update-archive.yml)) runs every Monday at 06:00 UTC. It asks MailerLite for any newsletters sent since the last run, adds them to the archive and pushes the change, and then GitHub Pages republishes the site. Newsletters already in the archive are never changed or removed, even if they're deleted from MailerLite later.

It needs a repository secret named `MAILERLITE_TOKEN` holding a MailerLite API token (**Settings → Secrets and variables → Actions**). To run it straight away, open the **Actions** tab, choose **Update newsletter archive** and click **Run workflow**.

## Running it locally

```bash
python3 tools/export_newsletters.py --only-new   # token from MAILERLITE_TOKEN or a .env file
python3 tools/build_archive.py
```

Both scripts use only the Python standard library. `newsletters.json` records what has been archived.
