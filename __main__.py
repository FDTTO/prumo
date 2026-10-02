"""Prumo: checks a web page in a real browser, against its design and its own claims.

    python PRUMO [--config FILE] [--base URL] COMMAND ...

    run SCENARIO        one scenario, its full log as JSON
    suite [DIR]         every scenario, a line per run; --coverage lists what none reached
    fidelity [STATE]    the page against its reference design, property by property
    mutate              break one function at a time and see whether the suite notices
    diff BEFORE AFTER   two screenshots, and what moved between them
    visit SCENARIO      a scenario inside any page: a URL, or a folder served locally

PRUMO is this folder. The project is described by the nearest prumo.json above
the working directory, or --config; `diff` and `visit` need none.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prumo import config, fidelity, mutate, pixdiff, scenarios, visit  # noqa: E402


def parse(argv):
    parser = argparse.ArgumentParser(prog="prumo", description=__doc__.split("\n")[0])
    parser.add_argument("--config", help="the project's prumo.json (default: the nearest above)")
    parser.add_argument("--base", help="the app to run against, overriding the configured one")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="one scenario, its full log as JSON")
    run.add_argument("scenario")
    run.add_argument("--width", type=int, default=1280)
    run.add_argument("--height", type=int, default=1400)
    run.add_argument("--wait", type=int, default=30000)
    run.add_argument("--virtual", type=int, metavar="MS")
    run.add_argument("--clip", action="append", default=[], help="JS returning {x, y, width, height}; repeatable")
    run.add_argument("--out", help="prefix of the log and screenshots (default: the project's output folder)")

    suite = commands.add_parser("suite", help="every scenario, a line per run")
    suite.add_argument("directory", nargs="?")
    suite.add_argument("--only", help="scenarios whose file name contains one of these, comma-separated")
    suite.add_argument("--jobs", type=int, default=3)
    suite.add_argument("--verbose", action="store_true")
    suite.add_argument("--coverage", action="store_true", help="list the rules and functions no scenario reached")

    fidelity_command = commands.add_parser("fidelity", help="the page against its reference design")
    fidelity_command.add_argument("state", nargs="?", help="one state; every state when left out")
    fidelity_command.add_argument("--only", help="roles to report, comma-separated prefixes")
    fidelity_command.add_argument("--all", action="store_true", help="every property, not only the differences")
    fidelity_command.add_argument("--shots", action="store_true", help="save both viewports")
    fidelity_command.add_argument("--exact", action="store_true", help="boxes to a hundredth of a pixel")

    mutate_command = commands.add_parser("mutate", help="break one function at a time")
    mutate_command.add_argument("--only", help="function names, comma-separated")
    mutate_command.add_argument("--sample", type=int, help="a random sample of this many covered functions")
    mutate_command.add_argument("--seed", type=int, default=1)

    diff = commands.add_parser("diff", help="two screenshots, and what moved")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--out", help="write a mask of the differing pixels here")
    diff.add_argument("--tolerance", type=int, default=0, help="per-channel difference to ignore")
    diff.add_argument("--ignore-from", help="a scenario log holding the regions to mask")
    diff.add_argument("--ignore-key", default="dynamic")
    diff.add_argument("--scale", type=float, default=2.0, help="screenshot scale (runs capture at 2x)")

    visit_command = commands.add_parser("visit", help="a scenario inside any page")
    visit_command.add_argument("scenario")
    visit_command.add_argument("--url")
    visit_command.add_argument("--serve", metavar="DIR", help="serve this folder locally and visit it")
    visit_command.add_argument("--at", default="/", help="the path the folder is served under")
    visit_command.add_argument("--adapter", action="append", default=[], help="an adapter to load; repeatable")
    visit_command.add_argument("--wait", type=int, default=30000)
    visit_command.add_argument("--width", type=int, default=1280)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    # The Windows console defaults to cp1252, which cannot print what a page writes.
    sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "diff":
        ignore = pixdiff.masked_boxes(args.ignore_from, args.ignore_key, args.scale) if args.ignore_from else ()
        return pixdiff.compare(args.before, args.after, args.out, args.tolerance, ignore)
    if args.command == "visit":
        return visit.main(args.scenario, url=args.url, serve=args.serve, at=args.at, adapters=args.adapter,
                          wait=args.wait, width=args.width)

    project = config.load(args.config, args.base)
    if args.command == "run":
        out = args.out or os.path.join(project.out, "shot")
        log = scenarios.run_one(project, args.scenario, width=args.width, height=args.height, wait=args.wait,
                                virtual=args.virtual, clips=args.clip, out=out)
        print(json.dumps(log, indent=1, ensure_ascii=False))
        if args.clip:
            print("screenshots: %s_<n>.png" % out)
        return 1 if scenarios.failed(log) else 0
    if args.command == "suite":
        return scenarios.suite(project, args.directory, args.only, args.jobs, args.verbose, args.coverage)
    if args.command == "fidelity":
        chosen = [args.state] if args.state else fidelity.states(project)
        results = [fidelity.main(project, state, args.only, args.all, args.shots, args.exact) for state in chosen]
        return 1 if any(results) else 0
    if args.command == "mutate":
        return mutate.main(project, args.only, args.sample, args.seed)


if __name__ == "__main__":
    sys.exit(main())
