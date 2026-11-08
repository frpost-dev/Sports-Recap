# Nightly Sports Recap (Level 2)

Pulls finished games for your leagues, renders an Instagram carousel (1080x1350), and drafts a caption.
You review it and upload through Meta Business Suite (or Buffer/Later).

## Setup (once)
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # optional; without it you get a plain template caption
```
Optional: drop `bold.ttf` and `regular.ttf` into a `fonts/` folder (any OFL font, e.g. Inter or
Montserrat from Google Fonts) for a nicer look. Otherwise it falls back to system fonts.

Edit `brand` and anything else you want in `config.yaml`.

## Daily flow
1. Morning: edit `today.yaml` (picks, skips, `only_picks`). Optional.
2. After the last game you care about ends (~11:30 PM ET works for most): `python recap.py`
3. Open `out/YYYY-MM-DD/`: check every score against the source, then upload `slide_*.png` + `caption.txt`.
4. Boxing title fights: add the result to `today.yaml` under `boxing:` before running.

Games not final yet are listed and skipped; re-run once they finish. `python recap.py --demo` renders fake
data to test the layout with no network.

## Daily 8 PM ET scores CSV (hands-off)
`daily_csv.py` collects the day's games across your leagues, has Claude pick the notable ones (up to
`daily_csv_max_picks`, default 12; falls back to a rules score if there's no API key), and writes
`csv/<date>.csv` plus `csv/latest.csv`. Each row has a `state` (pre / in / post) and a `pick_reason`, so
an 8 PM run still shows live and upcoming games. Team sports: `side_a` = away, `side_b` = home.

To schedule it free with GitHub Actions:
1. Make this folder the root of a new GitHub repo (the workflow lives in `.github/workflows/daily-csv.yml`).
2. Repo Settings > Secrets and variables > Actions > add `ANTHROPIC_API_KEY`.
3. Done. It runs at 8 PM Eastern (two crons, gated on the Eastern hour so DST doesn't matter) and commits the
   CSV to `csv/`. Open `csv/latest.csv` on github.com from your phone, or use the Actions tab > Run workflow
   to test it now.

Notes: GitHub cron can start several minutes late. GitHub disables scheduled workflows after 60 days of repo
inactivity (the daily commits keep it active). Test locally first: `python daily_csv.py --demo`.

## Known limits
- Data comes from ESPN's unofficial site API: free, but undocumented, unlicensed for commercial use,
  and liable to change. UFC and F1 parsing is best-effort; verify on your first real weekend.
- UFC/F1 events are matched by the ET date they're listed under; late-night results may land on the next date
  (use `--date`).
- Slides use team names as text only (no logos). Keep it that way unless you hold the rights.
- Always eyeball the numbers before posting. A wrong score is the main failure mode.
