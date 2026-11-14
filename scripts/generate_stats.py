#!/usr/bin/env python3
"""Generate the GitHub analytics SVGs from the real GitHub GraphQL API.

No third-party image service is involved: numbers come straight from GitHub and are
rendered into static SVGs under assets/stats/. Nothing is invented or estimated.

Usage:  GITHUB_TOKEN=... python scripts/generate_stats.py <login> [output_dir]
Only PUBLIC data is used (public repositories, public contribution counts).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "Abdullahzahoor755"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "assets" / "stats")

PANEL, BORDER, TEXT, DIM = "#0d1416", "#1d2c2e", "#c9d6d6", "#6f8788"
GREEN, CYAN, PURPLE = "#00ff9c", "#00e5ff", "#8b5cf6"
MONO = "'JetBrains Mono','Fira Code','SF Mono',Consolas,'Courier New',monospace"
PALETTE = [GREEN, CYAN, PURPLE, "#34d399", "#22d3ee", "#a78bfa", "#6ee7b7", "#67e8f9"]

QUERY = """
query($login:String!){
  user(login:$login){
    followers{totalCount}
    repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false, first:100){
      totalCount
      nodes{ name stargazerCount forkCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } }
    }
    contributionsCollection{
      totalCommitContributions totalPullRequestContributions
      totalIssueContributions totalPullRequestReviewContributions
      contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
    }
  }
}"""


def fetch() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats-generator"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def svg(w: int, h: int, body: str, title: str, desc: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
        f'aria-labelledby="t d"><title id="t">{escape(title)}</title><desc id="d">{escape(desc)}</desc>'
        f"<style>text{{font-family:{MONO}}}@media (prefers-reduced-motion: reduce){{*{{animation:none!important}}}}</style>"
        f'<rect width="{w}" height="{h}" rx="8" fill="{PANEL}"/>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="8" fill="none" stroke="{BORDER}"/>{body}</svg>\n'
    )


def streaks(days: list[tuple[date, int]]) -> tuple[int, int]:
    longest = run = 0
    for _, c in days:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    # current streak: count back from today (allow today to be empty)
    cur, i = 0, len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    return cur, longest


def build(u: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cc = u["contributionsCollection"]
    cal = cc["contributionCalendar"]
    days = [(date.fromisoformat(d["date"]), d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"]]
    cur, longest = streaks(days)
    repos = u["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ---------- overview tiles
    tiles = [
        ("CONTRIBUTIONS", cal["totalContributions"], "last 12 months", GREEN),
        ("COMMITS", cc["totalCommitContributions"], "last 12 months", CYAN),
        ("PULL REQUESTS", cc["totalPullRequestContributions"], "last 12 months", PURPLE),
        ("PUBLIC REPOS", u["repositories"]["totalCount"], "non-fork", GREEN),
        ("CURRENT STREAK", f"{cur}d", "consecutive days", CYAN),
        ("LONGEST STREAK", f"{longest}d", "within last 12 months", PURPLE),
        ("STARS", stars, "across public repos", GREEN),
        ("FOLLOWERS", u["followers"]["totalCount"], "on GitHub", CYAN),
    ]
    w, cols = 1000, 4
    tw, th, gap = (w - 48 - gap_total(cols, 14)) / cols, 96, 14
    body = [f'<text x="24" y="34" font-size="13" letter-spacing="3" fill="{DIM}">// GITHUB.OVERVIEW — @{escape(LOGIN)}</text>',
            f'<text x="{w-24}" y="34" text-anchor="end" font-size="11" fill="{DIM}">source: GitHub GraphQL API · {stamp}</text>']
    for i, (lab, val, sub, col) in enumerate(tiles):
        x = 24 + (i % cols) * (tw + gap)
        y = 52 + (i // cols) * (th + gap)
        body.append(
            f'<rect x="{x:.0f}" y="{y}" width="{tw:.0f}" height="{th}" rx="6" fill="{col}" fill-opacity=".05" stroke="{col}" stroke-opacity=".35"/>'
            f'<text x="{x+16:.0f}" y="{y+26}" font-size="11" letter-spacing="2" fill="{DIM}">{lab}</text>'
            f'<text x="{x+16:.0f}" y="{y+62}" font-size="32" font-weight="700" fill="{col}">{val}</text>'
            f'<text x="{x+16:.0f}" y="{y+84}" font-size="11" fill="{DIM}">{sub}</text>'
        )
    h = 52 + 2 * (th + gap) + 8
    (OUT / "overview.svg").write_text(
        svg(w, h, "".join(body), "GitHub overview",
            f"Contributions {cal['totalContributions']}, commits {cc['totalCommitContributions']}, pull requests {cc['totalPullRequestContributions']}, "
            f"public repos {u['repositories']['totalCount']}, current streak {cur} days, longest streak {longest} days, stars {stars}, followers {u['followers']['totalCount']}."))

    # ---------- languages (by bytes across public non-fork repos)
    totals: dict[str, int] = defaultdict(int)
    for r in repos:
        for e in r["languages"]["edges"]:
            totals[e["node"]["name"]] += e["size"]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:8]
    total = sum(v for _, v in ranked) or 1
    w2, bx, bw = 490, 24, 442
    body = [f'<text x="24" y="34" font-size="13" letter-spacing="3" fill="{DIM}">// TOP LANGUAGES</text>']
    x = bx
    for i, (n, v) in enumerate(ranked):
        seg = bw * v / total
        body.append(f'<rect x="{x:.1f}" y="50" width="{max(seg - 2, 1):.1f}" height="12" rx="2" fill="{PALETTE[i % len(PALETTE)]}"/>')
        x += seg
    for i, (n, v) in enumerate(ranked):
        y = 96 + i * 26
        body.append(
            f'<rect x="24" y="{y-10}" width="10" height="10" rx="2" fill="{PALETTE[i % len(PALETTE)]}"/>'
            f'<text x="44" y="{y}" font-size="14" fill="{TEXT}">{escape(n)}</text>'
            f'<text x="{w2-24}" y="{y}" text-anchor="end" font-size="14" fill="{DIM}">{100*v/total:.1f}%</text>')
    h2 = 96 + len(ranked) * 26 + 10
    body.append(f'<text x="24" y="{h2-4}" font-size="10" fill="{DIM}">by code size · public non-fork repos · {stamp}</text>')
    (OUT / "languages.svg").write_text(
        svg(w2, 330, "".join(body), "Most used languages",
            "Language share by code size: " + ", ".join(f"{n} {100*v/total:.1f}%" for n, v in ranked)))

    # ---------- weekly activity bars (last 52 weeks)
    weeks = cal["weeks"][-52:]
    wk = [sum(d["contributionCount"] for d in wkk["contributionDays"]) for wkk in weeks]
    peak = max(wk) or 1
    w3, h3 = 490, 330
    ch_top, ch_h = 70, 190
    bar = (w3 - 48) / len(wk)
    body = [f'<text x="24" y="34" font-size="13" letter-spacing="3" fill="{DIM}">// CONTRIBUTION ACTIVITY</text>',
            f'<text x="{w3-24}" y="34" text-anchor="end" font-size="11" fill="{DIM}">weekly · 52 weeks</text>']
    for i, v in enumerate(wk):
        bh = 0 if v == 0 else max(3, ch_h * v / peak)
        col = GREEN if v > 0 else BORDER
        body.append(f'<rect x="{24 + i*bar:.1f}" y="{ch_top + ch_h - max(bh, 2):.1f}" width="{max(bar-2, 1):.1f}" height="{max(bh, 2):.1f}" rx="1" fill="{col}" opacity="{0.35 + 0.65*(v/peak) if v else 1:.2f}"/>')
    body.append(f'<line x1="24" y1="{ch_top+ch_h+4}" x2="{w3-24}" y2="{ch_top+ch_h+4}" stroke="{BORDER}"/>')
    first, last = weeks[0]["contributionDays"][0]["date"], weeks[-1]["contributionDays"][-1]["date"]
    body.append(f'<text x="24" y="{ch_top+ch_h+24}" font-size="11" fill="{DIM}">{first}</text><text x="{w3-24}" y="{ch_top+ch_h+24}" text-anchor="end" font-size="11" fill="{DIM}">{last}</text>')
    active = sum(1 for _, c in days if c > 0)
    body.append(f'<text x="24" y="{h3-22}" font-size="13" fill="{TEXT}">{active} active days · busiest week: {peak} contributions</text>')
    (OUT / "activity.svg").write_text(
        svg(w3, h3, "".join(body), "Contribution activity",
            f"Weekly contributions over the last 52 weeks, from {first} to {last}. {active} active days; busiest week {peak} contributions."))

    print(f"overview: contributions={cal['totalContributions']} streak={cur}/{longest} repos={u['repositories']['totalCount']} langs={[n for n,_ in ranked]}")


def gap_total(cols: int, gap: int) -> int:
    return gap * (cols - 1)


if __name__ == "__main__":
    build(fetch())
