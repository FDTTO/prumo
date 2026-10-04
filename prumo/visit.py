"""A scenario run inside any page, with no harness and no project setup.

The scenario, after Prumo's core and the adapters asked for, is injected at
the start of the page's document, so it can check a site exactly as it is
served: a static build, a deployed page, a reference opened from disk. With
`serve`, a folder is served on a free local port first, under `at`, the way a
host such as GitHub Pages serves a project under its name.
"""
import contextlib
import functools
import os
import shutil
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import browser, page, scenarios


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class _QuietServer(ThreadingHTTPServer):
    """A browser closing a connection mid-answer is not a failure of the site.

    A browser opens several connections per page at once; past the default
    queue of 5, the rest went unanswered and a page could hang loading."""
    request_queue_size = 64

    def handle_error(self, request, client_address):
        if not isinstance(sys.exc_info()[1], ConnectionError):
            super().handle_error(request, client_address)


@contextlib.contextmanager
def _served(folder, at):
    work = tempfile.mkdtemp(prefix="prumo-site-")
    try:
        mount = os.path.join(work, *[part for part in at.split("/") if part])
        shutil.copytree(folder, mount)
        server = _QuietServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=work))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            prefix = at.strip("/") + "/" if at.strip("/") else ""
            yield f"http://127.0.0.1:{server.server_address[1]}/{prefix}"
        finally:
            server.shutdown()
            server.server_close()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(scenario, url=None, serve=None, at="/", adapters=(), wait=30000, width=1280, verbose=True):
    if bool(url) == bool(serve):
        raise SystemExit("prumo visit needs a URL or a folder to serve, not both")
    os.makedirs(browser.OUT, exist_ok=True)
    probe = os.path.join(browser.OUT, "visit.inject.js")
    sources = [browser.script("core.js")] + [browser.script(f"adapters/{name}.js") for name in adapters]
    with open(probe, "w", encoding="utf-8") as target:
        target.write("\n".join(sources) + f"\n(function () {{\n{page.read(scenario)}\n}})();\n")
    try:
        with (_served(serve, at) if serve else contextlib.nullcontext(url)) as target_url:
            log = browser.run(target_url, os.path.join(browser.OUT, "visit"), wait=wait, width=width, inject=probe)
    finally:
        os.remove(probe)
    stem = os.path.splitext(os.path.basename(scenario))[0]
    return 0 if scenarios.report(stem, width, log, verbose) else 1
