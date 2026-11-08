"""Fetch and normalize scoreboards from ESPN's public (unofficial, undocumented) site API.

Heads up: these endpoints are not an official product. They can change or break without
notice and aren't licensed for commercial use. If the account becomes a business, switch
this module to a licensed provider (Sportradar, SportsDataIO, API-Sports) and keep the
same normalized output shape.
"""
import requests

BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
HEADERS = {"User-Agent": "Mozilla/5.0 (nightly-recap)"}


def fetch_scoreboard(path, yyyymmdd):
    params = {"dates": yyyymmdd, "limit": 300}
    if path == "football/college-football":
        params["groups"] = 80  # FBS only
    r = requests.get(BASE.format(path=path), params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


# ---------- team sports (football, basketball, baseball, soccer) ----------

def _leaders(competitor):
    out = []
    for cat in competitor.get("leaders", []) or []:
        top = (cat.get("leaders") or [None])[0]
        if not top:
            continue
        name = (top.get("athlete") or {}).get("displayName")
        val = top.get("displayValue")
        label = cat.get("shortDisplayName") or cat.get("displayName") or ""
        if name and val:
            out.append(f"{name} ({label}: {val})")
    return out[:3]


def _team_side(c):
    team = c.get("team", {})
    rank = (c.get("curatedRank") or {}).get("current")
    if rank in (0, 99):
        rank = None
    return {
        "name": team.get("displayName", "?"),
        "abbr": team.get("abbreviation", ""),
        "score": c.get("score", ""),
        "rank": rank,
        "winner": bool(c.get("winner")),
        "leaders": _leaders(c),
    }


def parse_team_event(ev):
    comp = ev["competitions"][0]
    st = comp["status"]["type"]
    sides = {c["homeAway"]: _team_side(c) for c in comp["competitors"]}
    if "home" not in sides or "away" not in sides:
        return None
    return {
        "kind": "team",
        "final": bool(st.get("completed")),
        "state": st.get("state", ""),
        "status": st.get("shortDetail", ""),
        "home": sides["home"],
        "away": sides["away"],
        "name": ev.get("name", ""),
    }


# ---------- UFC ----------

def parse_fight_event(ev):
    bouts, pending = [], 0
    for comp in ev.get("competitions", []):
        st = comp.get("status", {})
        if not st.get("type", {}).get("completed"):
            pending += 1
            continue
        cs = comp.get("competitors", [])
        w = next((c for c in cs if c.get("winner")), None)
        l = next((c for c in cs if c is not w), None)
        if not w or not l:
            continue  # draw / no contest: add manually if you care
        bouts.append({
            "winner": (w.get("athlete") or {}).get("displayName", "?"),
            "loser": (l.get("athlete") or {}).get("displayName", "?"),
            "method": (st.get("result") or {}).get("displayName", ""),
            "round": st.get("period"),
            "weight": (comp.get("type") or {}).get("text", ""),
        })
    if not bouts:
        return None
    return {"kind": "fight", "final": pending == 0, "state": "post" if pending == 0 else "in",
            "status": "Final" if pending == 0 else "In progress",
            "name": ev.get("name", ""), "bouts": bouts}


# ---------- Formula 1 ----------

def parse_race_event(ev):
    for comp in ev.get("competitions", []):
        ctype = (comp.get("type") or {})
        if ctype.get("abbreviation") != "Race":
            continue
        if not comp.get("status", {}).get("type", {}).get("completed"):
            return {"kind": "race", "final": False, "state": "in", "status": "In progress", "name": ev.get("name", ""), "podium": []}
        cs = sorted(comp.get("competitors", []), key=lambda c: int(c.get("order", 99)))
        podium = [{"pos": i + 1,
                   "driver": (c.get("athlete") or {}).get("displayName", "?"),
                   "team": (c.get("team") or {}).get("displayName", "")}
                  for i, c in enumerate(cs[:3])]
        return {"kind": "race", "final": True, "state": "post", "status": "Final", "name": ev.get("name", ""), "podium": podium}
    return None


PARSERS = {"team": parse_team_event, "fight": parse_fight_event, "race": parse_race_event}


def get_games(league, yyyymmdd):
    data = fetch_scoreboard(league["path"], yyyymmdd)
    parse = PARSERS[league["kind"]]
    games = []
    for ev in data.get("events", []):
        try:
            g = parse(ev)
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        if g:
            games.append(g)
    return games
