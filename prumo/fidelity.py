"""Compare a page against its reference design, element by element.

Opens the reference page from disk and the real page through the harness, in
the same state and viewport, measures every role on both sides, and prints
each property that differs, reference value first. Boxes are relative to the
first role, the frame. A screenshot tells that two pages differ; this tells
which property of which element, so a change can be aimed at the difference
instead of at an impression of it.

A state is a scenario in the project's states folder, named for the state,
whose header names the reference page and the state it shows:

    // @reference design/mockup.html#idle

It brings the real page to that state and calls measure(). The project's
include files run first, for helpers its states share. Roles are
[role, reference selector, page selector]; `selector|n` picks the n-th match.
"""
import json
import os
import re
import urllib.parse

from . import browser, page

TEXT = {"fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "textTransform", "color", "textAlign"}
SRGB = re.compile(r"color\(srgb ([\d.e-]+) ([\d.e-]+) ([\d.e-]+)(?: / ([\d.e-]+))?\)")
# What the page needs to settle after the state is reached: an opened sheet's
# margin transition, a late paint.
SETTLE_MS = 1500


def states(config):
    folder = config.fidelity.states
    if not folder or not os.path.isdir(folder):
        raise SystemExit("No fidelity states folder configured (fidelity.states in prumo.json)")
    return sorted(os.path.splitext(name)[0] for name in os.listdir(folder) if name.endswith(".js"))


def reference(config, state):
    """The reference page of a state as a file URL, with its hash."""
    path = os.path.join(config.fidelity.states, state + ".js")
    with open(path, encoding="utf-8") as source:
        match = re.search(r"^\s*//\s*@reference\s+(\S+)", source.read(), re.M)
    if not match:
        raise SystemExit(f"{path}: no // @reference header")
    file, _, anchor = match.group(1).partition("#")
    url = "file:///" + urllib.parse.quote(os.path.join(config.root, file).replace("\\", "/"), safe="/:")
    return url + ("#" + anchor if anchor else "")


def _measuring(config, exact):
    return (("window.__fidelityExact = true;" if exact else "") + browser.script("fidelity-probe.js")
            + page.read(config.fidelity.roles))


def measure_reference(config, state, out, exact, shots):
    width, height = config.fidelity.viewport
    probe = out + ".inject.js"
    hide = "".join(f"document.querySelectorAll({json.dumps(s)}).forEach(function (n) {{ n.style.display = 'none'; }});"
                   for s in config.fidelity.hide)
    with open(probe, "w", encoding="utf-8") as target:
        target.write(_measuring(config, exact)
                     # What the reference page draws around the design (a state picker) is not the design.
                     + f"addEventListener('DOMContentLoaded', function () {{ {hide} }});"
                     + "addEventListener('load', function () { setTimeout(function () {"
                       " window.__log = { fidelity: window.__fidelity('mock', window.__fidelityRoles), done: true };"
                       f" }}, {SETTLE_MS}); }});")
    clips = [f"({{x:0,y:0,width:{width},height:{height}}})"] if shots else []
    try:
        # Webfonts come from the network, and a slow load can push the load
        # event past the wait; the log is then empty and the run is retried.
        for _ in range(3):
            log = browser.run(reference(config, state), out, wait=8000, width=width, height=height, clips=clips, inject=probe)
            if "fidelity" in log:
                return log["fidelity"]
    finally:
        os.remove(probe)
    raise SystemExit("the reference produced no measurement in three runs")


def measure_page(config, state, out, exact, shots):
    width, height = config.fidelity.viewport
    body = (_measuring(config, exact)
            + "".join(page.read(path) + "\n" for path in config.fidelity.include)
            + "var measure = function () { setTimeout(function () {"
              f" L('fidelity', window.__fidelity('real', window.__fidelityRoles)); done(); }}, {SETTLE_MS}); }};\n"
            + page.read(os.path.join(config.fidelity.states, state + ".js")))
    name = "prumo-fidelity.html"
    clips = [f"({{x:0,y:0,width:{width},height:{height}}})"] if shots else []
    with page.published(config, {name: page.build(config, body)}):
        log = browser.run(config.url(name), out, wait=30000, width=width, height=height, clips=clips)
    if "fidelity" not in log:
        raise SystemExit("the page produced no measurement: {} {}".format(log.get("errors"), log.get("timeouts") or ""))
    return log["fidelity"]


def canonical(value):
    """color-mix() computes to color(srgb ...), a literal to rgb(a)(...)."""
    if not isinstance(value, str):
        return value

    def rgba(m):
        r, g, b = (round(float(c) * 255) for c in m.groups()[:3])
        a = m.group(4)
        if a and float(a) < 1:
            return f"rgba({r}, {g}, {b}, {round(float(a), 3):g})"
        return f"rgb({r}, {g}, {b})"
    return re.sub(r"rgba\(([^)]*), ([\d.]+)\)", lambda m: f"rgba({m.group(1)}, {round(float(m.group(2)), 3):g})",
                  SRGB.sub(rgba, value))


def same(a, b, exact):
    try:
        return abs(float(a) - float(b)) <= (0.05 if exact else 1)
    except (TypeError, ValueError):
        return canonical(a) == canonical(b)


def compared(key, m, r):
    """Text properties only where text is drawn; a border colour only where a border is."""
    if key == "text":
        return False
    if key in TEXT and not (m.get("text") or r.get("text") or "stroke" in m):
        return False
    return not (key == "borderTopColor" and m.get("borderTopWidth") == "0px" and r.get("borderTopWidth") == "0px")


def differences(mock, real, only=None, every=False, exact=False):
    """(role, lines) for each role that differs. A role neither side draws in
    this state is not a difference; one side drawing it and the other not is."""
    found, absent = [], 0
    for role in mock:
        if only and not any(role.startswith(o) for o in only):
            continue
        m, r = mock[role], real.get(role)
        if m is None and r is None:
            absent += 1
            continue
        if m is None or r is None:
            found.append((role, ["    drawn only in the " + ("page" if m is None else "reference")]))
            continue
        lines = [f"    {k:<16} {m[k]}  ->  {r.get(k)}" for k in m
                 if every or (compared(k, m, r) and not same(m[k], r.get(k), exact))]
        if lines:
            found.append((role, lines))
    return found, absent


def main(config, state, only=None, every=False, shots=False, exact=False):
    if state not in states(config):
        raise SystemExit("No state {}; states: {}".format(state, ", ".join(states(config))))
    prefix = os.path.join(config.out, f"fidelity-{state}-")
    os.makedirs(config.out, exist_ok=True)
    mock = measure_reference(config, state, prefix + "mock", exact, shots)
    real = measure_page(config, state, prefix + "real", exact, shots)
    found, absent = differences(mock, real, only.split(",") if only else None, every, exact)
    for role, lines in found:
        print(role)
        print("\n".join(lines))
    drawn = len(mock) - absent
    print(f"\n{len(found)} of {drawn} roles drawn in this state differ")
    if shots:
        print(f"shots: {prefix}mock_0.png  {prefix}real_0.png")
    return 1 if found else 0
