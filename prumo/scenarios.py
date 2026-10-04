"""Scenarios: one run with its full log, or the whole suite as a table.

A scenario is plain JavaScript run inside the project's harness after Prumo's
core and adapters. It acts on the page through V.*, records values with
L(key, value) and expectations with check(name, pass, detail), and calls
done() when it has finished. Its header, the comment lines at the top of the
file, sets how it runs:

    // @widths 320,1280       one run per width, default 1280
    // @wait 30000            ceiling in ms, default 30000; a run ends as
                              soon as the scenario calls done()
    // @virtual 40000         virtual time on this budget instead of the
                              real clock
    // @alone                 run after the parallel batch, by itself: for
                              real input (keys, the pointer), which a machine
                              busy with other browsers can drop

A run fails when a check fails, a console error is logged, or it never calls
done().
"""
import concurrent.futures
import glob
import json
import os
import re

from . import browser, coverage, page


def header(path):
    settings = {"widths": [1280], "wait": 30000, "virtual": None, "alone": False}
    with open(path, encoding="utf-8-sig") as source:
        for line in source:
            match = re.match(r"\s*//\s*@(\S+)(?:\s+(.+))?", line)
            if not match:
                if line.strip() and not line.strip().startswith("//"):
                    break
                continue
            key, value = match.group(1), (match.group(2) or "").strip()
            if key == "alone":
                settings["alone"] = True
            elif key == "widths":
                settings["widths"] = [int(width) for width in value.split(",")]
            elif key == "wait":
                settings["wait"] = int(value)
            elif key == "virtual":
                settings["virtual"] = int(value)
    return settings


def run_one(config, scenario, width=1280, wait=30000, virtual=None, clips=(), out=None, height=1400):
    """One scenario, one width; returns its log."""
    name = "prumo-run.html"
    out = out or os.path.join(config.out, "run")
    with page.published(config, {name: page.build(config, page.read(scenario))}):
        return browser.run(config.url(name), out, wait=wait, width=width, height=height, virtual=virtual, clips=clips)


def failed(log):
    checks = log.get("checks") or []
    return bool(log.get("errors")) or any(not c["pass"] for c in checks)


def suite(config, directory=None, only=None, jobs=3, verbose=False, with_coverage=False):
    """Every scenario at every width it declares; prints a line per run and
    returns 1 when any run failed."""
    directory = directory or config.scenarios
    if with_coverage:
        for stale in coverage.files(config.out):
            os.remove(stale)
    scenarios = sorted(glob.glob(os.path.join(directory, "*.js")))
    if only:
        wanted = [name.strip() for name in only.split(",") if name.strip()]
        scenarios = [s for s in scenarios if any(name in os.path.basename(s) for name in wanted)]
    if not scenarios:
        raise SystemExit(f"No scenarios in {directory}")

    runs, pages = [], {}
    for path in scenarios:
        settings = header(path)
        html = page.build(config, page.read(path))
        stem = os.path.splitext(os.path.basename(path))[0]
        for width in settings["widths"]:
            name = f"prumo-{stem}-{width}.html"
            pages[name] = html
            runs.append((stem, width, settings, name))

    def execute(run):
        stem, width, settings, name = run
        out = os.path.join(config.out, f"{stem}-{width}")
        return browser.run(config.url(name), out, wait=settings["wait"], width=width, virtual=settings["virtual"],
                           coverage=config.url() if with_coverage else None)

    with page.published(config, pages):
        shared = [run for run in runs if not run[2]["alone"]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            logs = dict(zip([run[3] for run in shared], pool.map(execute, shared), strict=True))
        for run in runs:
            if run[2]["alone"]:
                logs[run[3]] = execute(run)

    any_failed = False
    for stem, width, _, name in runs:
        ok = report(stem, width, logs[name], verbose)
        any_failed = any_failed or not ok
    if with_coverage:
        coverage.report(coverage.files(config.out), config.publish_dir)
    return 1 if any_failed else 0


def report(stem, width, log, verbose):
    checks = log.get("checks") or []
    passed = [c for c in checks if c["pass"]]
    errors = log.get("errors") or []
    if not log.get("done"):
        errors = errors + ["scenario did not finish within its wait (no done())"]
    ok = bool(checks) and len(passed) == len(checks) and not errors
    # A wait that ran out is shown even when the run passes: a condition that
    # never holds is a sleep in disguise, and the checks after it pass anyway.
    waited_out = log.get("timeouts") or []
    verdict = "PASS" if ok else "FAIL"
    errors_note = f"  {len(errors)} console errors" if errors else ""
    waits_note = f"  {len(waited_out)} wait{'' if len(waited_out) == 1 else 's'} ran out" if waited_out else ""
    print(f"{verdict} {stem:<22} {width:5d}px  {len(passed)}/{len(checks)} checks{errors_note}{waits_note}")
    for c in checks:
        if verbose or not c["pass"]:
            detail = "" if c["pass"] or c["detail"] is None else "  -> " + json.dumps(c["detail"], ensure_ascii=False)
            print("       {} {}{}".format("ok  " if c["pass"] else "FAIL", c["name"], detail))
    for error in errors:
        print("       error: " + error.splitlines()[0][:200])
    for waited in waited_out:
        print("       timed out waiting for: " + waited)
    if not checks and not errors:
        print("       (no checks recorded)")
    return ok
