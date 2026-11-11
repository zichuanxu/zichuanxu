#!/usr/bin/env python3
"""Draws the profile's toys into assets/ from the contribution calendar. Stdlib only.

    GH_TOKEN=$(gh auth token) python3 build.py

rooftops.svg  a cat runs the year as a platformer: one building per week, taller = busier, five fish to catch
scores.svg    arcade high-score board
pet.svg       virtual pet that is fed by contributions
"""
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "assets"
LOGIN = os.environ.get("GITHUB_REPOSITORY_OWNER", "zichuanxu")

# 3x5 pixel font, each glyph is 5 rows of 3 bits.
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:.! ", """
010101111101101 110101110101110 011100100100011 110101101101110 111100110100111 111100110100100
011100101101011 101101111101101 111010010010111 001001001101010 101101110101101 100100100100111
101111111101101 110101101101101 111101101101111 110101110100100 010101101110011 110101110101101
011100010001110 111010010010010 101101101101111 101101101101010 101101111111101 101101010101101
101101010010010 111001010100111 111101101101111 010110010010111 110001010100111 110001010001110
101101111001001 111100110001110 011100111101111 111001010010010 111101111101111 111101111001110
000000111000000 000010000010000 000000000000010 010010010000010 000000000000000""".split()))

CAT_RUN = ["#.......#.#.", "#.......####", ".#..#####.##", ".###########", "..#########.", "..########.."]
LEGS = ([".#..#..#..#.", ".#........#."], ["...#.##.#...", "...#....#..."])
FISH = ["#...##.", "##.####", "#######", "##.####", "#...##."]
HEART = ["##.##", "#####", ".###.", "..#.."]
# Front-facing pet; rows 3 and 5 (eyes, mouth) are swapped per mood.
PET = [".#.......#.", ".##.....##.", ".#########.", None, "###########", None,
       ".#########.", "..#######..", ".#########.", ".##.###.##."]
FACES = {"happy": ("###.###.###", "####.#.####"), "hungry": ("###.###.###", "#####.#####"), "asleep": ("##..###..##", "###########")}


def bitmap(rows, x, y, s, fill, on="#", attrs="", cls=""):
    """One path for a bitmap: an s-tall strip per horizontal run of `on` cells."""
    d = "".join(f"M{x + m.start() * s} {y + r * s}h{len(m[0]) * s}v{s}h-{len(m[0]) * s}z"
                for r, row in enumerate(rows) for m in re.finditer(f"[{on}]+", row))
    return f'<path class="px {cls}" d="{d}" fill="{fill}" {attrs}/>'


def text(s, x, y, size, fill, attrs="", cls=""):
    rows = [" ".join(FONT[ch][r * 3:r * 3 + 3] for ch in s) for r in range(5)]
    return bitmap(rows, x, y, size, fill, "1", attrs, cls)


def centered(s, cx, y, size, fill, attrs=""):
    return text(s, round(cx - (len(s) * 4 - 1) * size / 2), y, size, fill, attrs)


def svg(w, h, body, css=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n'
            f'<style>.px{{shape-rendering:crispEdges}}\n@keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}\n{css}\n'
            f'@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}</style>\n{body}\n</svg>\n')


def longest_run(counts):
    best = run = 0
    for c in counts:
        run = run + 1 if c else 0
        best = max(best, run)
    return best


def mood(counts):
    """(mood, days since the last contribution). Fed within a day is happy, within four is hungry."""
    idle = next((i for i, c in enumerate(reversed(counts)) if c), len(counts))
    return ("happy" if idle <= 1 else "hungry" if idle <= 4 else "asleep"), idle


assert longest_run([0, 1, 2, 0, 3]) == 2 and longest_run([]) == 0
assert mood([5, 0]) == ("happy", 1) and mood([5, 0, 0, 0, 0]) == ("hungry", 4) and mood([5] + [0] * 5) == ("asleep", 5)


def during(a, b, dur):
    """SMIL that shows an element only between fractions a and b of the loop."""
    vals, times = ["1"], [f"{a:.4f}" if a > 0 else "0"]
    if a > 0:
        vals, times = ["0"] + vals, ["0"] + times
    if b < 1:
        vals, times = vals + ["0"], times + [f"{b:.4f}"]
    return (f'<animate attributeName="opacity" calcMode="discrete" values="{";".join(vals)}" '
            f'keyTimes="{";".join(times)}" dur="{dur}s" repeatCount="indefinite"/>')


def curve_length(p0, c, p1, n=24):
    pts = [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]) for t in (i / n for i in range(n + 1))]
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def rooftops(weeks):
    w, h, ground = 800, 280, 262
    rnd = random.Random(7)  # fixed seed: stars and windows stay put between daily rebuilds
    totals = [sum(d["contributionCount"] for d in wk["contributionDays"]) for wk in weeks]
    pitch = (w - 24) / len(weeks)
    bw = pitch - 2
    b = ['<defs><linearGradient id="sky" x2="0" y2="1"><stop offset="0" stop-color="#2a1b6b"/><stop offset=".5" stop-color="#6a2c91"/>'
         '<stop offset=".85" stop-color="#e0527a"/><stop offset="1" stop-color="#ffb26b"/></linearGradient>'
         f'<clipPath id="c"><rect width="{w}" height="{h}" rx="14"/></clipPath></defs>',
         f'<g clip-path="url(#c)"><rect width="{w}" height="{h}" fill="url(#sky)"/>']
    for _ in range(46):
        b.append(f'<rect class="st" x="{rnd.randrange(8, w - 8)}" y="{rnd.randrange(8, 130)}" width="2" height="2" fill="#fff" '
                 f'style="animation-delay:-{rnd.random() * 4:.1f}s"/>')
    b.append('<circle cx="704" cy="54" r="21" fill="#fff3d6"/><circle cx="697" cy="48" r="4" fill="#ecdcb4"/>'
             '<circle cx="711" cy="61" r="3" fill="#ecdcb4"/><circle cx="709" cy="45" r="2" fill="#ecdcb4"/>')

    roofs, lit = [], ""
    for i, (wk, tot) in enumerate(zip(weeks, totals)):
        x = 12 + i * pitch
        bh = 14 + 150 * math.log1p(tot) / math.log1p(max(max(totals), 1))
        y = ground - bh
        roofs.append((x + bw / 2, y))
        b.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh + 20:.1f}" fill="{("#120e2e", "#1a1542")[i % 2]}"/>')
        share = sum(1 for d in wk["contributionDays"] if d["contributionCount"]) / 7  # active days light the windows
        for wy in range(int(y) + 5, ground - 6, 9):
            for wx in (x + 2.5, x + bw - 5.5):
                if rnd.random() < share * .8:
                    if rnd.random() < .06:
                        b.append(f'<rect class="st" x="{wx:.1f}" y="{wy}" width="3" height="4" fill="#ffd76a" style="animation-delay:-{rnd.random() * 4:.1f}s"/>')
                    else:
                        lit += f"M{wx:.1f} {wy}h3v4h-3z"
    b.append(f'<path d="{lit}" fill="#ffd76a"/><rect y="{ground}" width="{w}" height="{h - ground}" fill="#0c0920"/>')
    tx, ty = roofs[max(range(len(totals)), key=totals.__getitem__)]
    b.append(f'<rect x="{tx - .5:.1f}" y="{ty - 14:.1f}" width="1" height="14" fill="#120e2e"/>'
             f'<circle cx="{tx:.1f}" cy="{ty - 15:.1f}" r="1.8" fill="#ff5d73" style="animation:blink 1.2s infinite"/>')

    # The run: walk across level roofs, jump between uneven ones, in from the left and out to the right.
    pts = [(-24, ground)] + roofs + [(w + 24, ground)]
    d, lens = f"M{pts[0][0]} {pts[0][1]}", [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(y0 - y1) < 1:
            d += f"L{x1:.1f} {y1:.1f}"
            lens.append(lens[-1] + x1 - x0)
        else:
            c = ((x0 + x1) / 2, min(y0, y1) - 16)
            d += f"Q{c[0]:.1f} {c[1]:.1f} {x1:.1f} {y1:.1f}"
            lens.append(lens[-1] + curve_length((x0, y0), c, (x1, y1)))
    dur = round(max(20, lens[-1] / 75), 1)

    # The year is cut into five stretches; a fish waits on each one's busiest week
    # and is eaten the moment the cat lands there.
    n = len(totals)
    busiest = [max(range(k * n // 5, (k + 1) * n // 5), key=totals.__getitem__) for k in range(5)]
    eaten = [lens[i + 1] / lens[-1] for i in busiest]
    for i, at in zip(busiest, eaten):
        fx, fy = roofs[i]
        b.append(bitmap(FISH, round(fx) - 7, round(fy) - 16, 2, "#7fe7ff").replace("/>", f">{during(0, at, dur)}</path>"))
    for n, (a, z) in enumerate(zip([0] + eaten, eaten + [1])):
        b.append(text(f"FISH {n}", 24, 22, 3, "#fff3d6").replace("/>", f">{during(a, z, dur)}</path>"))

    legs = "".join(bitmap(CAT_RUN + rows, 0, 0, 3, "#fff3d6", attrs=f'style="animation-delay:-{k * .15}s"', cls="leg") for k, rows in enumerate(LEGS))
    b.append(f'<g><animateMotion dur="{dur}s" repeatCount="indefinite" path="{d}"/><g transform="translate(-18 -24)">{legs}</g></g></g>')
    css = """@keyframes tw{0%,100%{opacity:1}50%{opacity:.2}}
.st{animation:tw 4s infinite}
.leg{animation:blink .3s infinite}"""
    return svg(w, h, "\n".join(b), css)


def scores(rows):
    b = ['<defs><pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity=".22"/></pattern></defs>',
         '<rect x="1" y="1" width="398" height="298" rx="14" fill="#14122e" stroke="#3a3570" stroke-width="2"/>', centered("HIGH SCORES", 200, 30, 5, "#ffd23f")]
    colors = ("#ff5d73", "#ff9f43", "#ffd23f", "#5ee6a8", "#62c8ff")
    for i, (label, value) in enumerate(sorted(rows, key=lambda r: -r[1])):
        line = f'{("1ST", "2ND", "3RD", "4TH", "5TH")[i]} {label:<12}{value:>6}'
        b.append(centered(line, 200, 84 + i * 34, 4, colors[i], f'style="animation:in 1ms {(i + 1) * .35:.2f}s backwards"'))
    b.append(centered("PRESS START", 200, 264, 3, "#fff3d6", 'style="animation:blink 1.1s infinite"'))
    b.append('<rect width="400" height="300" rx="14" fill="url(#scan)"/>')
    return svg(400, 300, "\n".join(b), "@keyframes in{from{opacity:0}}")


def pet(counts):
    state, idle = mood(counts)
    ink, days = "#2a3324", "DAY" if idle == 1 else "DAYS"
    line = {"happy": "FED TODAY" if idle == 0 else "FED YESTERDAY", "hungry": f"HUNGRY {idle} {days}", "asleep": f"ASLEEP {idle} {days}"}[state]
    eyes, mouth = FACES[state]
    sprite = [eyes if i == 3 else mouth if i == 5 else row for i, row in enumerate(PET)]
    b = ['<circle cx="200" cy="20" r="10" fill="none" stroke="#9aa0a6" stroke-width="3"/>',
         '<path d="M200 30C268 30 312 118 312 186C312 250 262 290 200 290C138 290 88 250 88 186C88 118 132 30 200 30Z" fill="#ffcc33" stroke="#e0a800" stroke-width="4"/>',
         '<ellipse cx="160" cy="84" rx="22" ry="12" fill="#fff" opacity=".4" transform="rotate(-38 160 84)"/>',
         '<rect x="126" y="92" width="148" height="122" rx="20" fill="#6b4de6"/><rect x="140" y="104" width="120" height="98" rx="6" fill="#c9d6b8"/>']
    b += [f'<circle cx="{x}" cy="248" r="9" fill="#6b4de6"/>' for x in (164, 200, 236)]
    # One heart per day of the last week, solid if that day had a contribution.
    b += [bitmap(HEART, 147 + i * 16, 110, 2, ink, attrs="" if c else 'opacity=".22"') for i, c in enumerate(counts[-7:])]
    b.append(bitmap(sprite, 173, 127, 5, ink, cls="hop" if state == "happy" else ""))
    if state == "happy":
        b.append(bitmap(HEART, 236, 130, 2, ink, cls="up"))
    if state == "asleep":
        b.append(text("Z", 236, 138, 2, ink, cls="up") + text("Z", 246, 126, 3, ink, 'style="animation-delay:-1s"', "up"))
    b.append(centered(line, 200, 185, 2, ink, 'style="animation:blink 1.4s infinite"' if state == "hungry" else ""))
    css = """@keyframes hop{0%,49%{transform:none}50%,100%{transform:translateY(-5px)}}
@keyframes up{0%{opacity:0;transform:none}25%{opacity:1}100%{opacity:0;transform:translateY(-12px)}}
.hop{animation:hop .9s infinite}
.up{animation:up 2s infinite}"""
    return svg(400, 300, "\n".join(b), css)


def fetch():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("No token. Run: GH_TOKEN=$(gh auth token) python3 build.py")
    query = ("query($u:String!){user(login:$u){repositories(first:100,ownerAffiliations:OWNER,isFork:false){nodes{stargazerCount}}"
             "contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{contributionCount}}}}}}")
    req = urllib.request.Request("https://api.github.com/graphql",
                                 json.dumps({"query": query, "variables": {"u": LOGIN}}).encode(),
                                 {"Authorization": f"bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["user"]


def main():
    user = fetch()
    cal = user["contributionsCollection"]["contributionCalendar"]
    counts = [d["contributionCount"] for wk in cal["weeks"] for d in wk["contributionDays"]]
    OUT.mkdir(exist_ok=True)
    (OUT / "rooftops.svg").write_text(rooftops(cal["weeks"]))
    (OUT / "scores.svg").write_text(scores([
        ("YEAR TOTAL", cal["totalContributions"]),
        ("STARS", sum(r["stargazerCount"] for r in user["repositories"]["nodes"])),
        ("BEST DAY", max(counts)),
        ("ACTIVE DAYS", sum(1 for c in counts if c)),
        ("BEST STREAK", longest_run(counts)),
    ]))
    (OUT / "pet.svg").write_text(pet(counts))


if __name__ == "__main__":
    main()
