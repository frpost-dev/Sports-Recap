#!/usr/bin/env python3
"""Daily scores CSV: collect candidate games, let Claude pick the notable ones, write a CSV.

  python daily_csv.py                   # today (ET)
  python daily_csv.py --date 2026-11-07
  python daily_csv.py --demo            # fake data, no network, rules-based picks

Picks come from Claude when ANTHROPIC_API_KEY is set; otherwise (or if the call fails) from a
transparent rules score. The CSV includes games in progress and not started yet, with a `state`
column (pre / in / post), so an 8 PM run is still useful while late games are going.

Team sports: side_a = AWAY team, side_b = HOME team.
UFC: one row per completed bout (side_a = winner, side_b = loser).
F1: one row per race (side_a = winner, details = rest of the podium).
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import re
from zoneinfo import ZoneInfo

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-sonnet-5-5"
COLUMNS = ["date", "league", "event", "side_a", "score_a", "side_b", "score_b",
           "state", "status", "winner", "details", "pick_reason"]
LEAGUE_WEIGHT = {"ucl": 3, "nfl": 3, "epl": 3, "ufc": 3, "f1": 3, "nba": 2, "cfb": 2,
                 "laliga": 2, "bundesliga": 2, "mlb": 1, "ligue1": 1, "seriea": 1}
CLOSE_MARGIN = {"football": 3, "basketball": 5, "baseball": 1, "soccer": 1}


def load_yaml(name, default):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return yaml.safe_load(f) or default


# ---------- matching (same rules as recap.py) ----------

def haystack(g):
    if g["kind"] == "team":
        parts = [g["home"]["name"], g["away"]["name"], g["home"]["abbr"], g["away"]["abbr"]]
    elif g["kind"] == "fight":
        parts = [g["name"]] + [b["winner"] for b in g["bouts"]] + [b["loser"] for b in g["bouts"]]
    else:
        parts = [g["name"]] + [p["driver"] for p in g.get("podium", [])]
    return " | ".join(parts).lower()


def matches(g, needles):
    h = haystack(g)
    return any(n.lower() in h for n in needles or [])


def passes_league_rule(g, lg):
    mode = lg.get("mode", "all")
    if mode == "ranked" and g["kind"] == "team":
        cap = lg.get("rank_max", 25)
        return any(s["rank"] and s["rank"] <= cap for s in (g["home"], g["away"]))
    if mode == "teams":
        return matches(g, lg.get("teams", []))
    return True


# ---------- rows + rule score ----------

def rule_score(lg, g, favs):
    s = LEAGUE_WEIGHT.get(lg["key"], 1)
    if g["kind"] == "team":
        a, h = g["away"], g["home"]
        ranked = [x["rank"] for x in (a, h) if x["rank"]]
        s += 4 if len(ranked) == 2 else 2 if ranked else 0
        if matches(g, favs):
            s += 3
        if g.get("state") in ("in", "post"):
            try:
                sport = lg["path"].split("/")[0]
                if abs(float(a["score"]) - float(h["score"])) <= CLOSE_MARGIN.get(sport, 1):
                    s += 1
            except (ValueError, TypeError):
                pass
        if any(t in g.get("status", "") for t in ("OT", "AET", "Pens")):
            s += 1
    else:
        s += 2
    return s


def to_rows(lg, g, day, favs):
    base = {"date": day.isoformat(), "league": lg["name"], "event": g.get("name", ""),
            "state": g.get("state", ""), "status": g.get("status", ""),
            "pick_reason": "", "_kind": g["kind"], "_lg": lg["key"], "_score": rule_score(lg, g, favs)}
    if g["kind"] == "team":
        a, h = g["away"], g["home"]
        started = g.get("state") in ("in", "post")
        sa, sh = (a["score"], h["score"]) if started else ("", "")
        winner = ""
        if g.get("state") == "post":
            try:
                fa, fh = float(sa), float(sh)
                winner = a["name"] if fa > fh else h["name"] if fh > fa else "Draw"
            except ValueError:
                pass

        def label(s):
            return f"#{s['rank']} {s['name']}" if s["rank"] else s["name"]
        return [dict(base, side_a=label(a), score_a=sa, side_b=label(h), score_b=sh, winner=winner,
                     details="; ".join((a["leaders"] + h["leaders"])[:4]))]
    if g["kind"] == "fight":
        rows = []
        for b in g["bouts"]:
            det = " · ".join(x for x in [b.get("weight"), b.get("method"),
                                         f"Rd {b['round']}" if b.get("round") else ""] if x)
            rows.append(dict(base, side_a=b["winner"], score_a="", side_b=b["loser"], score_b="",
                             winner=b["winner"], details=det))
        return rows
    pod = g.get("podium", [])
    return [dict(base, side_a=pod[0]["driver"] if pod else "", score_a="", side_b="", score_b="",
                 winner=pod[0]["driver"] if pod else "",
                 details=", ".join(f"P{p['pos']} {p['driver']}" for p in pod[1:]))]


def describe(r):
    if r["_kind"] == "team":
        if r["score_a"] != "":
            return f"{r['side_a']} {r['score_a']}, {r['side_b']} {r['score_b']} ({r['status']})"
        return f"{r['side_a']} at {r['side_b']} ({r['status']})"
    if r["_kind"] == "fight":
        return f"{r['event']}: {r['side_a']} def. {r['side_b']} {r['details']}"
    return f"{r['event']}: winner {r['side_a']} ({r['status']})"


# ---------- picking ----------

def claude_pick(rows, n, date_label):
    """Return [(index, reason)] or None."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    lines = "\n".join(f"{i}: [{r['league']}] {describe(r)} (rule_score {r['_score']})"
                      for i, r in enumerate(rows))
    prompt = (f"You pick games for a daily sports scores sheet. Date: {date_label}.\n"
              f"Candidates (rule_score is only a rough notability hint):\n{lines}\n\n"
              f"Choose up to {n}. Favor marquee teams and matchups, ranked-vs-ranked games or ranked upsets, "
              "close or overtime finishes, significant events, and variety across leagues. "
              "Games in progress or not started can be included if notable. Use only the facts shown.\n"
              'Return ONLY a JSON array like [{"id": 3, "reason": "under 12 words"}].')
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=1500, messages=[{"role": "user", "content": prompt}])
        m = re.search(r"\[.*\]", msg.content[0].text, re.S)
        picks, seen = [], set()
        for item in json.loads(m.group(0)):
            i = int(item["id"])
            if 0 <= i < len(rows) and i not in seen:
                seen.add(i)
                picks.append((i, str(item.get("reason", ""))[:120]))
        return picks[:n] or None
    except Exception as e:
        print(f"  ! Claude pick failed ({e}); using rules")
        return None


def rules_pick(rows, n, per_league=3):
    order = sorted(range(len(rows)), key=lambda i: -rows[i]["_score"])
    taken, counts = [], {}
    for i in order:
        k = rows[i]["_lg"]
        if counts.get(k, 0) >= per_league:
            continue
        counts[k] = counts.get(k, 0) + 1
        taken.append((i, f"rule score {rows[i]['_score']}"))
        if len(taken) == n:
            break
    return taken


# ---------- demo ----------

def demo_candidates(favs):
    def side(n, sc, rank=None, w=False):
        return {"name": n, "abbr": n[:3].upper(), "score": sc, "rank": rank, "winner": w, "leaders": []}

    def tg(a, h, state, st):
        return {"kind": "team", "final": state == "post", "state": state, "status": st,
                "home": h, "away": a, "name": ""}
    L = lambda k, n, p: {"key": k, "name": n, "path": p}
    return [
        (L("cfb", "College Football", "football/college-football"),
         tg(side("Sample State", "21", 7), side("Example Tech", "24", 3, True), "post", "Final")),
        (L("nfl", "NFL", "football/nfl"), tg(side("Demo Chiefs", "27", w=True), side("Mock Bills", "24"), "post", "Final/OT")),
        (L("nfl", "NFL", "football/nfl"), tg(side("Alpha Bears", "6"), side("Beta Lions", "34", w=True), "post", "Final")),
        (L("nba", "NBA", "basketball/nba"), tg(side("Sample Lakers", "88"), side("Test Celtics", "91"), "in", "Q4 3:12")),
        (L("epl", "Premier League", "soccer/eng.1"), tg(side("Demo FC", "2", w=True), side("Mock United", "2"), "post", "FT")),
        (L("mlb", "MLB", "baseball/mlb"), tg(side("Test Sox", ""), side("Demo Cubs", ""), "pre", "9:10 PM ET")),
    ]


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--max-picks", type=int)
    args = ap.parse_args()

    cfg = load_yaml("config.yaml", {})
    today = load_yaml("today.yaml", {})
    tz = ZoneInfo(cfg.get("timezone", "America/New_York"))
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(tz).date()
    date_label = f"{day.strftime('%a, %b')} {day.day}, {day.year}"
    n = args.max_picks or cfg.get("daily_csv_max_picks", 12)
    picks_cfg, skip = today.get("picks") or [], today.get("skip") or []
    favs = [t for lg in cfg.get("leagues", []) for t in lg.get("teams", [])] + picks_cfg

    pairs = []
    if args.demo:
        pairs = demo_candidates(favs)
    else:
        import espn
        for lg in cfg["leagues"]:
            try:
                games = espn.get_games(lg, day.strftime("%Y%m%d"))
            except Exception as e:
                print(f"  ! {lg['name']}: fetch failed ({e})")
                continue
            for g in games:
                if skip and matches(g, skip):
                    continue
                if (picks_cfg and matches(g, picks_cfg)) or passes_league_rule(g, lg):
                    pairs.append((lg, g))

    rows = [r for lg, g in pairs for r in to_rows(lg, g, day, favs)]
    if not rows:
        print("No candidate games found; no CSV written.")
        return

    chosen = None if args.demo else claude_pick(rows, n, date_label)
    source = "Claude" if chosen else "rules"
    chosen = chosen or rules_pick(rows, n)
    league_order = {lg["key"]: i for i, lg in enumerate(cfg.get("leagues", []))}
    out_rows = []
    for i, reason in chosen:
        r = dict(rows[i])
        r["pick_reason"] = reason
        out_rows.append(r)
    out_rows.sort(key=lambda r: (league_order.get(r["_lg"], 99), -r["_score"]))

    out_dir = os.path.join(HERE, "csv")
    os.makedirs(out_dir, exist_ok=True)
    for name in (f"{day.isoformat()}.csv", "latest.csv"):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(out_rows)
    states = {s: sum(1 for r in out_rows if r["state"] == s) for s in ("post", "in", "pre")}
    print(f"Wrote {len(out_rows)} of {len(rows)} candidates to csv/{day.isoformat()}.csv "
          f"(picked by {source}; final={states['post']}, live={states['in']}, upcoming={states['pre']})")


if __name__ == "__main__":
    main()
