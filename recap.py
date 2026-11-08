#!/usr/bin/env python3
"""Nightly sports recap: fetch finals -> render carousel slides -> draft caption.

Usage:
  python recap.py                 # tonight (ET), real data
  python recap.py --date 2026-11-07
  python recap.py --demo          # fake data, no network/API needed (tests layout)
"""
import argparse
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

import yaml

import cards
import captions

HERE = os.path.dirname(os.path.abspath(__file__))


def load_yaml(name, default):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return yaml.safe_load(f) or default


# ---------- matching helpers ----------

def _haystack(g):
    if g["kind"] == "team":
        parts = [g["home"]["name"], g["away"]["name"], g["home"]["abbr"], g["away"]["abbr"]]
    elif g["kind"] == "fight":
        parts = [g["name"]] + [b["winner"] for b in g["bouts"]] + [b["loser"] for b in g["bouts"]]
    else:
        parts = [g["name"]] + [p["driver"] for p in g.get("podium", [])]
    return " | ".join(parts).lower()


def matches(g, needles):
    h = _haystack(g)
    return any(n.lower() in h for n in needles or [])


def passes_league_rule(g, league):
    mode = league.get("mode", "all")
    if mode == "all":
        return True
    if mode == "ranked" and g["kind"] == "team":
        cap = league.get("rank_max", 25)
        return any(s["rank"] and s["rank"] <= cap for s in (g["home"], g["away"]))
    if mode == "teams":
        return matches(g, league.get("teams", []))
    return True


# ---------- row building ----------

def team_rows(games):
    rows = []
    for g in games:
        def label(s):
            return f"#{s['rank']} {s['name']}" if s["rank"] else s["name"]
        a, h = g["away"], g["home"]
        a_win = a["winner"] or (a["score"] and h["score"] and float(a["score"]) > float(h["score"]))
        h_win = h["winner"] or (a["score"] and h["score"] and float(h["score"]) > float(a["score"]))
        rows.append(cards.Row(top=label(a), top_right=str(a["score"]), bottom=label(h),
                              bottom_right=str(h["score"]), sub=g["status"],
                              top_win=bool(a_win), bottom_win=bool(h_win)))
    return rows


def fight_rows(g):
    rows = []
    for b in g["bouts"]:
        sub = " · ".join(x for x in [b.get("weight"), b.get("method"),
                                     f"Rd {b['round']}" if b.get("round") else ""] if x)
        rows.append(cards.Row(top=b["winner"], top_win=True, bottom=f"def. {b['loser']}", sub=sub))
    return rows


def race_rows(g):
    return [cards.Row(top=f"P{p['pos']}  {p['driver']}", top_win=(p["pos"] == 1), sub=p.get("team", ""))
            for p in g["podium"]]


def boxing_game(b):
    return {"kind": "fight", "final": True, "status": "Final", "name": b.get("belt", "Title fight"),
            "bouts": [{"winner": b["winner"], "loser": b["loser"], "weight": b.get("belt", ""),
                       "method": b.get("method", ""), "round": b.get("round")}]}


def build_slides(sections, per_slide):
    """sections: [{league, accent, games}] -> list of slide dicts."""
    slides = []
    for s in sections:
        kind = s["games"][0]["kind"]
        if kind == "team":
            for i in range(0, len(s["games"]), per_slide):
                chunk = s["games"][i:i + per_slide]
                slides.append({"title": s["league"], "accent": s["accent"], "rows": team_rows(chunk),
                               "n": len(chunk)})
        elif kind == "fight":
            for g in s["games"]:
                rows = fight_rows(g)
                for i in range(0, len(rows), per_slide):
                    slides.append({"title": s["league"], "subtitle": g["name"], "accent": s["accent"],
                                   "rows": rows[i:i + per_slide], "n": len(rows[i:i + per_slide])})
        else:
            for g in s["games"]:
                slides.append({"title": s["league"], "subtitle": g["name"], "accent": s["accent"],
                               "rows": race_rows(g), "n": 1})
    return slides


# ---------- digest for the caption ----------

def digest_for(sections):
    lines = []
    for s in sections:
        for g in s["games"]:
            if g["kind"] == "team":
                a, h = g["away"], g["home"]
                line = f"{s['league']}: {a['name']} {a['score']}, {h['name']} {h['score']} ({g['status']})"
                lead = (a["leaders"] + h["leaders"])[:4]
                if lead:
                    line += " | leaders: " + "; ".join(lead)
                lines.append(line)
            elif g["kind"] == "fight":
                for b in g["bouts"]:
                    lines.append(f"{s['league']} ({g['name']}): {b['winner']} def. {b['loser']}"
                                 f" {b.get('method', '')} {('Rd ' + str(b['round'])) if b.get('round') else ''}".strip())
            else:
                pod = ", ".join(f"P{p['pos']} {p['driver']}" for p in g["podium"])
                lines.append(f"{s['league']} ({g['name']}): {pod}")
    return "\n".join(lines)


# ---------- demo data ----------

def demo_sections():
    def side(n, sc, rank=None, w=False, lead=None):
        return {"name": n, "abbr": n[:3].upper(), "score": sc, "rank": rank, "winner": w, "leaders": lead or []}
    def tg(a, h, st="Final"):
        return {"kind": "team", "final": True, "status": st, "home": h, "away": a, "name": ""}
    return [
        {"league": "College Football", "accent": "#C8102E", "games": [
            tg(side("Sample State", "21", 7), side("Example Tech", "31", 3, True)),
            tg(side("Demo University", "17", None), side("Mock A&M", "20", 12, True), "Final/OT")]},
        {"league": "NFL", "accent": "#1E6FD9", "games": [
            tg(side("Sample Eagles", "24", None, True), side("Example Giants", "20")),
            tg(side("Demo Chiefs", "27", None, True), side("Mock Bills", "24"), "Final/OT"),
            tg(side("Test Jets", "10"), side("Sample Dolphins", "13", None, True)),
            tg(side("Alpha Bears", "6"), side("Beta Lions", "34", None, True))]},
        {"league": "UFC", "accent": "#D20A0A", "games": [
            {"kind": "fight", "final": True, "status": "Final", "name": "UFC Demo Night", "bouts": [
                {"winner": "Fighter One", "loser": "Fighter Two", "method": "KO/TKO", "round": 2, "weight": "Lightweight"},
                {"winner": "Fighter Three", "loser": "Fighter Four", "method": "Decision - Unanimous", "round": 5, "weight": "Bantamweight"}]}]},
        {"league": "Boxing", "accent": "#B8860B", "games": [boxing_game(
            {"belt": "Demo Heavyweight Title", "winner": "Boxer A", "loser": "Boxer B", "method": "KO", "round": 7})]},
        {"league": "Formula 1", "accent": "#E10600", "games": [
            {"kind": "race", "final": True, "status": "Final", "name": "Demo Grand Prix", "podium": [
                {"pos": 1, "driver": "Driver One", "team": "Team Alpha"},
                {"pos": 2, "driver": "Driver Two", "team": "Team Beta"},
                {"pos": 3, "driver": "Driver Three", "team": "Team Gamma"}]}]},
    ]


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: today in configured timezone)")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    cfg = load_yaml("config.yaml", {})
    today = load_yaml("today.yaml", {})
    tz = ZoneInfo(cfg.get("timezone", "America/New_York"))
    day = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(tz).date()
    date_label = f"{day.strftime('%a, %b')} {day.day}, {day.year}"
    picks, skip = today.get("picks") or [], today.get("skip") or []
    only_picks = bool(today.get("only_picks"))

    if args.demo:
        sections = demo_sections()
        date_label += "  ·  SAMPLE DATA"
    else:
        import espn
        sections, unfinished = [], []
        for lg in cfg["leagues"]:
            try:
                games = espn.get_games(lg, day.strftime("%Y%m%d"))
            except Exception as e:
                print(f"  ! {lg['name']}: fetch failed ({e})")
                continue
            keep = []
            for g in games:
                if skip and matches(g, skip):
                    continue
                if not g["final"]:
                    unfinished.append(f"{lg['name']}: {g.get('name') or _haystack(g)[:40]}")
                    continue
                forced = bool(picks) and matches(g, picks)
                ok = forced if only_picks else (forced or passes_league_rule(g, lg))
                if ok:
                    keep.append(g)
            if keep:
                sections.append({"league": lg["name"], "accent": lg["accent"], "games": keep})
        if unfinished:
            print("Not final yet (skipped, re-run later):")
            for u in unfinished:
                print("  -", u)
        boxing = [boxing_game(b) for b in (today.get("boxing") or [])]
        if boxing:
            sections.append({"league": "Boxing", "accent": cfg.get("boxing_accent", "#B8860B"), "games": boxing})

    if not sections:
        print("No qualifying finished games found. Nothing to render.")
        sys.exit(0)

    max_content = cfg.get("max_slides", 10) - 1
    slides = build_slides(sections, cfg.get("games_per_slide", 6))
    if len(slides) > max_content:
        dropped = slides[max_content:]
        slides = slides[:max_content]
        print(f"! Over the slide cap: dropped {len(dropped)} slide(s): "
              + ", ".join(sorted({s['title'] for s in dropped})) + ". Raise max_slides or tighten config.yaml.")

    out = os.path.join(HERE, "out", day.isoformat())
    os.makedirs(out, exist_ok=True)
    total = len(slides) + 1
    brand = cfg.get("brand", "")
    league_names = list(dict.fromkeys(s["title"] for s in slides))
    cards.render_cover(os.path.join(out, "slide_01.png"), brand, date_label, league_names,
                       sum(s["n"] for s in slides), total)
    for i, s in enumerate(slides, start=2):
        cards.render_card(os.path.join(out, f"slide_{i:02d}.png"), s["title"],
                          s.get("subtitle", date_label), s["rows"], s["accent"], brand, i, total)

    caption = captions.make_caption(digest_for(sections), date_label)
    with open(os.path.join(out, "caption.txt"), "w") as f:
        f.write(caption + "\n")
    print(f"Done: {total} slides + caption.txt in {out}")


if __name__ == "__main__":
    main()
