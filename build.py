#!/usr/bin/env python3
"""Draws the profile's toys into assets/ from the contribution calendar. Stdlib only.

    GH_TOKEN=$(gh auth token) python3 build.py

rooftops.svg  a cat runs the year as a platformer: one building per week, taller = busier, five fish to catch
scores.svg    arcade high-score board
pet.svg       virtual pet that is fed by contributions
tank.svg      aquarium: the four biggest languages swim as fish
mixtape.svg   cassette whose equaliser is the last two weeks and whose tape winds through the year
year.svg      the cat naps on a progress bar for the year
neon.svg      neon sign: open if there was a contribution today or yesterday, plus the live streak
ridges.svg    ridgeline drawing, one line per week for the last 30 weeks
chalk.svg     chalkboard sketch of contributions by weekday
poster.svg    Bauhaus-style print, one tile per month, bigger shape = busier month
"""
import datetime
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
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:.! %+#", """
010101111101101 110101110101110 011100100100011 110101101101110 111100110100111 111100110100100
011100101101011 101101111101101 111010010010111 001001001101010 101101110101101 100100100100111
101111111101101 110101101101101 111101101101111 110101110100100 010101101110011 110101110101101
011100010001110 111010010010010 101101101101111 101101101101010 101101111111101 101101010101101
101101010010010 111001010100111 111101101101111 010110010010111 110001010100111 110001010001110
101101111001001 111100110001110 011100111101111 111001010010010 111101111101111 111101111001110
000000111000000 000010000010000 000000000000010 010010010000010 000000000000000 101001010100101 000010111010000
101111101111101""".split()))

CAT_RUN = ["#.......#.#.", "#.......####", ".#..#####.##", ".###########", "..#########.", "..########.."]
LEGS = ([".#..#..#..#.", ".#........#."], ["...#.##.#...", "...#....#..."])
FISH = ["#...##.", "##.####", "#######", "##.####", "#...##."]
HEART = ["##.##", "#####", ".###.", "..#.."]
SWIMMER = ["#...###..", "##.#####.", "######.##", "##.#####.", "#...###.."]
LOAF = ["#.#........", "###.......#", "##########.", "##########.", ".########.."]
INK, CREAM = "#2b2d42", "#fff3d6"
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
    rows = [" ".join(FONT.get(ch, FONT[" "])[r * 3:r * 3 + 3] for ch in s) for r in range(5)]
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


def tank(langs):
    """langs: [(name, share of all code)], biggest first."""
    rnd = random.Random(3)
    box = 'x="28" y="44" width="344" height="204" rx="10"'
    b = ['<defs><linearGradient id="w" x2="0" y2="1"><stop offset="0" stop-color="#4fd8d2"/><stop offset="1" stop-color="#1a5fb0"/></linearGradient>'
         f'<clipPath id="t"><rect {box}/></clipPath></defs>',
         '<rect width="400" height="300" rx="14" fill="#2c2250"/>',
         bitmap(PET[:3] + [FACES["happy"][0]], 290, 18, 4, CREAM, cls="peek"),  # ears stay up, eyes pop over the lid now and then
         f'<rect {box} fill="url(#w)"/><g clip-path="url(#t)">']
    b += [f'<path d="M{x} 44h{w}l-{w + 30} 204h-{w}z" fill="#fff" opacity=".07"/>' for x, w in ((110, 46), (210, 26), (318, 54))]
    b.append('<path d="M28 232Q80 220 140 230T260 228T372 224V248H28Z" fill="#f2d9a0"/>'
             '<circle cx="96" cy="238" r="4" fill="#d9b978"/><circle cx="238" cy="240" r="5" fill="#d9b978"/><circle cx="330" cy="236" r="3" fill="#d9b978"/>')
    for x, hgt, color, delay in ((58, 76, "#1fa77a", 0), (72, 52, "#39c88f", 1.2), (300, 92, "#1fa77a", .6), (316, 60, "#39c88f", 2), (342, 40, "#1fa77a", 1.5)):
        b.append(f'<path class="weed" d="M{x} 238q-9 -{hgt / 4:.0f} 0 -{hgt / 2:.0f}t0 -{hgt / 2:.0f}" fill="none" stroke="{color}" stroke-width="6" '
                 f'stroke-linecap="round" style="animation-delay:-{delay}s"/>')
    for _ in range(8):
        b.append(f'<circle class="bub" cx="{rnd.randrange(44, 356)}" cy="240" r="{rnd.choice((2, 3, 4))}" fill="none" stroke="#fff" stroke-opacity=".75" '
                 f'style="animation-duration:{rnd.uniform(5, 9):.1f}s;animation-delay:-{rnd.uniform(0, 9):.1f}s"/>')
    for i, ((name, share), y, s, color) in enumerate(zip(langs, (60, 104, 146, 186), (5, 4, 3, 3), ("#ff7a59", "#ffd23f", "#ff8fc7", "#c8f76a"))):
        label = f"{name.upper()[:10]} {round(share * 100)}%"
        clock = f"animation-duration:{11 + i * 3}s;animation-delay:-{i * 2.7}s"
        travel = 328 - max(9 * s, (len(label) * 4 - 1) * 2)
        b.append(f'<g class="swim" style="--d:{travel}px;{clock}">' + bitmap(SWIMMER, 36, y, s, color, attrs=f'style="{clock}"', cls="flip")
                 + text(label, 36, y + 5 * s + 4, 2, "#fff", 'opacity=".9"') + "</g>")
    b.append(f'</g><path d="M42 58h16l-12 44h-16z" fill="#fff" opacity=".13"/><rect {box} fill="none" stroke="#dff6ff" stroke-opacity=".8" stroke-width="4"/>'
             '<rect x="22" y="36" width="356" height="12" rx="4" fill="#15102e"/><rect y="250" width="400" height="6" fill="#4a3d7a"/>'
             '<path d="M0 256h400v30a14 14 0 0 1-14 14H14a14 14 0 0 1-14-14z" fill="#211a3f"/>')
    css = """@keyframes swim{0%,100%{transform:translateX(0)}50%{transform:translateX(var(--d))}}
@keyframes flip{0%,49.99%{transform:scaleX(1)}50%,100%{transform:scaleX(-1)}}
@keyframes sway{0%,100%{transform:rotate(-5deg)}50%{transform:rotate(5deg)}}
@keyframes bub{0%{transform:translateY(0);opacity:0}12%{opacity:1}100%{transform:translateY(-190px);opacity:0}}
@keyframes peek{0%,62%,100%{transform:translateY(13px)}70%,92%{transform:translateY(0)}}
.swim{animation:swim ease-in-out infinite}
.flip{transform-box:fill-box;transform-origin:center;animation:flip linear infinite}
.weed{transform-box:fill-box;transform-origin:50% 100%;animation:sway 5s ease-in-out infinite}
.bub{animation:bub linear infinite}
.peek{animation:peek 9s ease-in-out infinite}"""
    return svg(400, 300, "\n".join(b), css)


def mixtape(counts, today):
    wound = today.timetuple().tm_yday / 366  # the tape moves from the left reel to the right over the year
    top = max(max(counts), 1)
    b = [f'<rect x="24" y="40" width="352" height="224" rx="14" fill="#f6ecd4" stroke="{INK}" stroke-width="4"/>',
         f'<rect x="44" y="56" width="312" height="134" rx="8" fill="#fffaf0" stroke="{INK}" stroke-width="2"/>']
    b += [f'<rect x="45" y="{172 + k * 6}" width="310" height="6" fill="{c}"/>' for k, c in enumerate(("#ff5d73", "#ffd23f", "#2ec4b6"))]
    b.append(centered(f"COMMIT MIX {today:%b %Y}".upper(), 200, 67, 3, INK))
    b.append(f'<rect x="118" y="96" width="164" height="62" rx="31" fill="{INK}"/>')
    teeth = "".join(f'<rect x="-2" y="-10" width="4" height="5" fill="{INK}" transform="rotate({a})"/>' for a in range(0, 360, 60))
    for cx, share in ((154, 1 - wound), (246, wound)):
        b.append(f'<g transform="translate({cx} 127)"><circle r="{12 + 15 * share:.1f}" fill="#6b4630"/>'
                 f'<g class="reel"><circle r="10" fill="#fffaf0"/>{teeth}</g></g>')
    # Equaliser: one bar per day, last week on the left and this week on the right.
    for i, c in enumerate(counts[-14:]):
        hgt = 6 + 9 * min(4, math.ceil(4 * math.log1p(c) / math.log1p(top)))
        x = (56 if i < 7 else 290 - 56) + i * 8
        b.append(f'<rect class="eq" x="{x}" y="{158 - hgt}" width="6" height="{hgt}" fill="{("#ff5d73", "#2ec4b6")[i >= 7]}" '
                 f'style="animation-delay:-{(i * 7 % 10) / 10}s"/>')
    b.append(f'<path d="M96 262L112 212H288L304 262Z" fill="#eadfc0" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>'
             f'<circle cx="150" cy="240" r="6" fill="{INK}"/><circle cx="250" cy="240" r="6" fill="{INK}"/>'
             f'<rect x="188" y="234" width="24" height="12" rx="2" fill="none" stroke="{INK}" stroke-width="2"/>')
    b += [f'<circle cx="{x}" cy="{y}" r="4" fill="none" stroke="{INK}" stroke-width="2"/>' for x in (38, 362) for y in (54, 250)]
    css = """@keyframes spin{to{transform:rotate(360deg)}}
@keyframes eq{0%,100%{transform:scaleY(1)}50%{transform:scaleY(.5)}}
.reel{transform-box:fill-box;transform-origin:center;animation:spin 3s linear infinite}
.eq{transform-box:fill-box;transform-origin:50% 100%;animation:eq 1s ease-in-out infinite}"""
    return svg(400, 300, "\n".join(b), css)


def year(today):
    start, end = datetime.date(today.year, 1, 1), datetime.date(today.year + 1, 1, 1)
    done = (today - start).days / (end - start).days
    rnd, cells, pct = random.Random(11), 50, f"{round(done * 100)}%"
    full = round(done * cells)
    b = ['<defs><linearGradient id="dusk" x2="0" y2="1"><stop offset="0" stop-color="#2a1b6b"/><stop offset="1" stop-color="#6a2c91"/></linearGradient></defs>',
         '<rect width="800" height="84" rx="14" fill="url(#dusk)"/>']
    b += [f'<rect class="st" x="{rnd.randrange(12, 788)}" y="{rnd.randrange(8, 44)}" width="2" height="2" fill="#fff" style="animation-delay:-{rnd.random() * 4:.1f}s"/>' for _ in range(22)]
    b += [text(f"LOADING {today.year + 1}", 26, 16, 3, CREAM), text(pct, 774 - (len(pct) * 4 - 1) * 3, 16, 3, "#ffd23f")]
    b += [f'<rect x="{26 + i * 15}" y="52" width="13" height="16" rx="2" fill="#ffd23f"/>' if i < full else
          f'<rect x="{26 + i * 15}" y="52" width="13" height="16" rx="2" fill="#fff" opacity=".16"/>' for i in range(cells)]
    cat = max(26, 26 + full * 15 - 35)  # asleep on the newest filled cell
    b += [bitmap(LOAF, cat, 37, 3, CREAM), text("Z", cat + 2, 24, 2, CREAM, cls="up")]
    css = """@keyframes tw{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes up{0%{opacity:0;transform:none}25%{opacity:1}100%{opacity:0;transform:translateY(-10px)}}
.st{animation:tw 4s infinite}
.up{animation:up 2.4s infinite}"""
    return svg(800, 84, "\n".join(b), css)


def current_run(counts):
    """Length of the streak that is still alive: a quiet today doesn't break it yet."""
    run = 0
    for c in reversed(counts[:-1] if counts and not counts[-1] else counts):
        if not c:
            break
        run += 1
    return run


assert current_run([1, 1, 0]) == 2 and current_run([1, 0, 0]) == 0 and current_run([0, 3, 2]) == 2 and current_run([]) == 0


def neon(counts):
    is_open = mood(counts)[0] == "happy"
    word, size, pink = ("OPEN", 78, "#ff4fa3") if is_open else ("CLOSED", 58, "#ff6b5e")
    tube = 'fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"'
    face = "font-family=\"'Arial Rounded MT Bold','Helvetica Neue',Arial,sans-serif\" font-weight=\"700\" text-anchor=\"middle\""
    b = ['<defs><pattern id="brick" width="40" height="20" patternUnits="userSpaceOnUse"><rect width="40" height="20" fill="#1d1626"/>'
         '<path d="M0 .5H40M0 10.5H40M20 0V10M.5 10V20" stroke="#2b2137" stroke-width="1.5"/></pattern>'
         '<filter id="glow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="5" result="b"/>'
         '<feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>',
         '<rect width="400" height="300" rx="14" fill="url(#brick)"/>',
         '<path d="M120 0V98M280 0V98" stroke="#0e0a14" stroke-width="2"/>',
         f'<path {tube} stroke="#ffe066" stroke-width="3" d="M177 72L172 38L190 52Q200 47 210 52L228 38L223 72Q222 88 200 88Q178 88 177 72ZM189 68q3 -4 6 0M205 68q3 -4 6 0M197 77h6"/>',
         f'<rect {tube} class="hum" x="48" y="100" width="304" height="152" rx="22" stroke="#4de1ff" stroke-width="3"/>',
         f'<text {tube} {face} class="flick" x="200" y="{188 if is_open else 180}" font-size="{size}" letter-spacing="6" stroke="{pink}" stroke-width="3">{word}</text>',
         f'<text {face} x="200" y="230" font-size="19" letter-spacing="3" fill="#ffe066" filter="url(#glow)">{current_run(counts)} DAY STREAK</text>']
    css = """@keyframes flick{0%,18%,22%,25%,53%,57%,100%{opacity:1}20%,24%,55%{opacity:.3}}
@keyframes hum{0%,100%{opacity:1}50%{opacity:.8}}
.flick{animation:flick 4.5s infinite}
.hum{animation:hum 3s ease-in-out infinite}"""
    return svg(400, 300, "\n".join(b), css)


def ridges(weeks):
    recent = weeks[-30:]
    top = max(max(d["contributionCount"] for wk in recent for d in wk["contributionDays"]), 1)
    b = ['<rect width="400" height="300" rx="14" fill="#101426"/>']
    for i, wk in enumerate(recent):  # oldest first, so newer weeks are drawn in front
        base, days = 64 + i * 7.3, [d["contributionCount"] for d in wk["contributionDays"]]
        vals = [0, 0] + days + [0] * (9 - len(days))
        pts = [(70 + k * 26, base - 46 * math.log1p(v) / math.log1p(top)) for k, v in enumerate(vals)]
        d = f"M30 {base:.1f}L{pts[0][0]} {pts[0][1]:.1f}"
        for (x1, y1), (x2, y2) in zip(pts[1:], pts[2:]):  # smooth: curve through each point to the next midpoint
            d += f"Q{x1} {y1:.1f} {(x1 + x2) / 2} {(y1 + y2) / 2:.1f}"
        d += f"L{pts[-1][0]} {base:.1f}L370 {base:.1f}"
        newest = i == len(recent) - 1
        b.append(f'<path class="rg" d="{d}" fill="#101426" stroke="{"#ffb26b" if newest else "#eef2ff"}" stroke-width="{2 if newest else 1.4}" '
                 f'stroke-opacity="{.3 + .7 * i / len(recent):.2f}" stroke-linejoin="round" style="animation-delay:{i * .12:.2f}s"/>')
    css = """@keyframes rg{5%{stroke:#ff8fc7;stroke-opacity:1}}
.rg{animation:rg 7s ease-out infinite}"""
    return svg(400, 300, "\n".join(b), css)


def chalk(days):
    totals = [0] * 7
    for d in days:
        totals[d["weekday"]] += d["contributionCount"]
    totals = totals[1:] + totals[:1]  # Monday first
    top, white = max(max(totals), 1), "#f4f1e8"
    hand = "font-family=\"'Chalkboard SE','Marker Felt','Comic Sans MS','Segoe Print',cursive\" stroke=\"none\""
    b = ['<defs><filter id="rough"><feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="2" seed="4"/>'
         '<feDisplacementMap in="SourceGraphic" scale="2.4"/></filter></defs>',
         '<rect width="400" height="300" rx="14" fill="#8a5a2b"/><rect x="12" y="12" width="376" height="276" rx="6" fill="#2f4f43"/>',
         '<ellipse cx="130" cy="150" rx="120" ry="50" fill="#fff" opacity=".035"/><ellipse cx="290" cy="90" rx="80" ry="34" fill="#fff" opacity=".03"/>',
         '<g filter="url(#rough)" fill="none" stroke-linecap="round" stroke-linejoin="round">',
         f'<text {hand} x="34" y="52" font-size="21" fill="{white}">commits by weekday</text>',
         f'<path d="M36 238H364" stroke="{white}" stroke-width="3"/>',
         f'<path d="M330 40l-4 -16l10 8q6 -3 12 0l10 -8l-4 16q0 12 -12 12t-12 -12zM336 42h.5M348 42h.5" stroke="{white}" stroke-width="2.5"/>']
    for k, (tot, letter) in enumerate(zip(totals, "MTWTFSS")):
        x, hgt = 50 + k * 44, max(7, 140 * tot / top)
        color = "#ffe27a" if tot == top else white
        zig = f"M{x} 234" + "".join(f"L{x + (28 if n % 2 else 0)} {234 - n * 7}" for n in range(1, int(hgt / 7) + 1))
        b.append(f'<path class="sc" pathLength="1" d="{zig}" stroke="{color}" stroke-width="4.5" style="animation-delay:{k * .22:.2f}s"/>'
                 f'<text {hand} x="{x + 14}" y="262" font-size="17" text-anchor="middle" fill="{white}">{letter}</text>')
        if tot == top:
            b.append(f'<text {hand} x="{x + 14}" y="{222 - hgt:.0f}" font-size="15" text-anchor="middle" fill="#ff9ec4">busiest!</text>')
    b.append("</g>")
    css = """@keyframes sc{from{stroke-dashoffset:1}}
.sc{stroke-dasharray:1;animation:sc .9s ease-out backwards}"""
    return svg(400, 300, "\n".join(b), css)


def poster(days):
    months = {}
    for d in days:
        months[d["date"][:7]] = months.get(d["date"][:7], 0) + d["contributionCount"]
    last = list(months.values())[-12:]
    top = max(max(last), 1)
    paper, red, blue, yellow, black = "#f3ead8", "#d9412b", "#23479a", "#f2b632", "#1c1c1c"
    pairs = [(paper, red), (blue, yellow), (yellow, black), (black, paper), (red, paper), (paper, blue),
             (black, yellow), (yellow, blue), (blue, paper), (paper, black), (red, black), (yellow, red)]
    face = "font-family=\"Futura,'Century Gothic','Avenir Next',Helvetica,Arial,sans-serif\" font-weight=\"700\" font-size=\"11\" letter-spacing=\"3\""
    b = [f'<rect width="400" height="300" rx="14" fill="{paper}"/>']
    for i, (tot, (bg, fg)) in enumerate(zip(last, pairs)):
        r = 34 * (.3 + .7 * math.log1p(tot) / math.log1p(top))
        shape = (f'<circle class="br" cx="44" cy="40" r="{r:.1f}" fill="{fg}"/>',
                 f'<path d="M0 80V{80 - 2 * r:.1f}A{2 * r:.1f} {2 * r:.1f} 0 0 1 {2 * r:.1f} 80Z" fill="{fg}"/>',
                 f'<rect class="tn" x="{44 - r * .8:.1f}" y="{40 - r * .8:.1f}" width="{r * 1.6:.1f}" height="{r * 1.6:.1f}" fill="{fg}"/>',
                 f'<path d="M{44 - 1.2 * r:.1f} 80A{1.2 * r:.1f} {1.2 * r:.1f} 0 0 1 {44 + 1.2 * r:.1f} 80Z" fill="{fg}"/>',
                 f'<path class="tn" d="M44 {40 - r:.1f}L{44 + r:.1f} {40 + r * .8:.1f}H{44 - r:.1f}Z" fill="{fg}"/>',
                 f'<circle class="br" cx="44" cy="40" r="{r * .75:.1f}" fill="none" stroke="{fg}" stroke-width="{r * .45:.1f}"/>')[i % 6]
        shape = shape.replace('class="', f'style="animation-delay:-{i * .7:.1f}s" class="')
        b.append(f'<svg x="{24 + i % 4 * 88}" y="{18 + i // 4 * 80}" width="88" height="80"><rect width="88" height="80" fill="{bg}"/>{shape}</svg>')
    b.append(f'<rect x="24" y="18" width="352" height="240" fill="none" stroke="{black}" stroke-width="2"/>'
             f'<text {face} x="24" y="281" fill="{black}">TWELVE MONTHS</text>'
             f'<text {face} x="376" y="281" text-anchor="end" fill="{red}">{days[-1]["date"][:4]}</text>')
    css = """@keyframes br{0%,100%{transform:scale(1)}50%{transform:scale(.84)}}
@keyframes turn{to{transform:rotate(360deg)}}
.br,.tn{transform-box:fill-box;transform-origin:center}
.br{animation:br 5s ease-in-out infinite}
.tn{animation:turn 36s linear infinite}"""
    return svg(400, 300, "\n".join(b), css)


def fetch():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("No token. Run: GH_TOKEN=$(gh auth token) python3 build.py")
    query = ("query($u:String!){user(login:$u){repositories(first:100,ownerAffiliations:OWNER,isFork:false){nodes{stargazerCount languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}}}"
             "contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{contributionCount date weekday}}}}}}")
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
    sizes = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            sizes[edge["node"]["name"]] = sizes.get(edge["node"]["name"], 0) + edge["size"]
    biggest = sorted(sizes.items(), key=lambda kv: -kv[1])[:4]
    (OUT / "tank.svg").write_text(tank([(name, size / sum(sizes.values())) for name, size in biggest]))
    # ponytail: the day rolls over on Japan time; make it an env var if that ever needs to change
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()
    (OUT / "mixtape.svg").write_text(mixtape(counts, today))
    (OUT / "year.svg").write_text(year(today))
    days = [d for wk in cal["weeks"] for d in wk["contributionDays"]]
    (OUT / "neon.svg").write_text(neon(counts))
    (OUT / "ridges.svg").write_text(ridges(cal["weeks"]))
    (OUT / "chalk.svg").write_text(chalk(days))
    (OUT / "poster.svg").write_text(poster(days))


if __name__ == "__main__":
    main()
