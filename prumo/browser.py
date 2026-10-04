"""One page in a headless Chromium, through browser/runner.js."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSER_DIR = os.path.join(os.path.dirname(HERE), "browser")
RUNNER = os.path.join(BROWSER_DIR, "runner.js")
OUT = os.path.join(tempfile.gettempdir(), "prumo")
# How long a profile may stay locked after its run. With a JVM and several
# browsers running, Windows was measured holding one past five seconds.
RECLAIM_SECONDS = 30
# The runner relies on the WebSocket and fetch that Node ships from 22 on.
NODE_MAJOR = 22
_node_checked = []


def script(name):
    """A file of browser/, e.g. "core.js" or "adapters/swagger-ui.js"."""
    with open(os.path.join(BROWSER_DIR, name), encoding="utf-8") as source:
        return source.read()


def ensure_node():
    """Stops with what to install, rather than a traceback, when Node is
    missing or older than the runner needs. Checked once per process."""
    if _node_checked:
        return
    if not shutil.which("node"):
        raise SystemExit(f"Prumo needs Node {NODE_MAJOR} or later on the PATH")
    version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
    if int(version.lstrip("v").split(".")[0]) < NODE_MAJOR:
        raise SystemExit(f"Prumo needs Node {NODE_MAJOR} or later; this is {version}")
    _node_checked.append(version)


def run(url, out, wait=30000, width=1280, height=1400, virtual=None, clips=(), inject=None, coverage=None):
    """Drives the page at `url` and returns what it logged, or an explanation
    in the same shape when there is no log to return.

    The browser profile is made here and handed to the runner, so it is
    removed even when the runner is killed or gives up on it; one that
    cannot be removed fails the run instead of filling the disk unnoticed."""
    ensure_node()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    profile = tempfile.mkdtemp(prefix="prumo-profile-")
    command = [
        "node",
        RUNNER,
        url,
        "--out",
        out,
        "--wait",
        str(wait),
        "--width",
        str(width),
        "--height",
        str(height),
        "--profile",
        profile,
    ]
    if virtual:
        command += ["--virtual", str(virtual)]
    if inject:
        command += ["--inject", inject]
    if coverage:
        command += ["--coverage", coverage]
    for clip in clips:
        command += ["--clip", clip]
    try:
        done = subprocess.run(command, capture_output=True, text=True)
    finally:
        leaked = reclaim(profile)
    if done.returncode != 0 or "error" in done.stdout:
        log = {"errors": ["runner failed: " + (done.stdout + done.stderr).strip()[:400]], "checks": []}
    else:
        with open(out + ".json", encoding="utf-8") as source:
            log = json.load(source) or {"errors": ["the page produced no log"], "checks": []}
    if leaked:
        log.setdefault("errors", []).append(leaked)
    return log


def reclaim(profile):
    """Removes a run's profile, waiting out the locks Windows keeps on it for
    a while after the browser exits; kills what still runs on it only after a
    few seconds. Returns an error when it is still there at the end."""
    start = time.monotonic()
    killed = False
    while os.path.exists(profile):
        shutil.rmtree(profile, ignore_errors=True)
        if not os.path.exists(profile):
            break
        elapsed = time.monotonic() - start
        if elapsed > RECLAIM_SECONDS:
            return "the browser profile was left behind: " + profile
        if elapsed > 5 and not killed:
            _kill_using(profile)
            killed = True
        time.sleep(0.5)
    return None


def _kill_using(profile):
    """Only the processes started on this profile, whatever the browser."""
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{profile}*' }} "
                "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }",
            ],
            capture_output=True,
        )
    else:
        subprocess.run(["pkill", "-KILL", "-f", profile], capture_output=True)
