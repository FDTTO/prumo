"""Break the page one function at a time and see whether the suite notices.

Needs a `prumo suite --coverage` first, to know which scenarios run what.
Each mutant knocks one named function of the project's scripts out, with a
`return;` as its first statement, serves it in place of the original and
runs only the scenarios whose coverage shows that function running: a
scenario that never calls it cannot catch it. A failing run means the mutant
was killed, some check depends on that function. A green run means it
survived: the function could stop working and the suite would stay green.

The original is restored after every mutant, and on any exit.
"""

import json
import os
import random
import re
import subprocess
import sys

from . import coverage

NAMED = re.compile(r"^(?:export )?(function (\w+)\()", re.M)
PRUMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def functions(file, source):
    """Named top-level functions with the offset V8 reports for them."""
    return [(file, match.group(2), match.start(1)) for match in NAMED.finditer(source)]


def scenarios_running(coverage_files, file, offset):
    """Scenario stems where the function at this offset of this file ran at least once."""
    stems = set()
    for path in coverage_files:
        with open(path, encoding="utf-8") as source:
            data = json.load(source)
        if any(f == file and start == offset and count > 0 for f, _, start, _, count in data["functions"]):
            stems.add(os.path.basename(path).rsplit("-", 1)[0])
    return sorted(stems)


def knock_out(source, offset):
    brace = source.index("{", offset)
    return source[: brace + 1] + " return;" + source[brace + 1 :]


def run_suite(config, stems):
    done = subprocess.run(
        [sys.executable, PRUMO, "--config", config.path, "--base", config.base, "suite", "--only", ",".join(stems)],
        capture_output=True,
        text=True,
    )
    failed = [line for line in done.stdout.splitlines() if line.startswith("FAIL")]
    return done.returncode != 0, failed


def main(config, only=None, sample=None, seed=1):
    coverage_files = coverage.files(config.out)
    if not coverage_files:
        raise SystemExit("No coverage yet: run prumo suite --coverage first.")
    originals = {}
    for file in coverage.shipped(config.publish_dir, ".js"):
        with open(config.published(file), encoding="utf-8", newline="") as source:
            originals[file] = source.read()

    targets = [t for file, text in originals.items() for t in functions(file, text)]
    if only:
        wanted = set(only.split(","))
        targets = [t for t in targets if t[1] in wanted]
    covered = [(file, name, offset, scenarios_running(coverage_files, file, offset)) for file, name, offset in targets]
    uncovered = [file + ":" + name for file, name, _, stems in covered if not stems]
    covered = [entry for entry in covered if entry[3]]
    if sample and sample < len(covered):
        covered = random.Random(seed).sample(covered, sample)

    results = []
    try:
        for file, name, offset, stems in covered:
            _write(config, file, knock_out(originals[file], offset))
            try:
                killed, failed = run_suite(config, stems)
            finally:
                _write(config, file, originals[file])
            results.append((name, killed))
            print(
                f"{'KILLED  ' if killed else 'SURVIVED'} {file + ':' + name:<40} by {', '.join(stems)}"
                + (f"  ({failed[0].split()[1]} failed)" if failed else ""),
                flush=True,
            )
    finally:
        for file, text in originals.items():
            _write(config, file, text)

    killed = sum(1 for _, was_killed in results if was_killed)
    if results:
        print(f"\n{killed} of {len(results)} mutants killed ({100 * killed // len(results)}%)")
    survivors = [name for name, was_killed in results if not was_killed]
    if survivors:
        print("survived, so no check depends on them: " + ", ".join(survivors))
    if uncovered:
        print("not run by any scenario, so not mutated: " + ", ".join(uncovered))
    return 1 if survivors else 0


def _write(config, file, text):
    with open(config.published(file), "w", encoding="utf-8", newline="") as target:
        target.write(text)
