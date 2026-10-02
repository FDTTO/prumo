"""The page a scenario runs in, and its publication next to the app's files.

A scenario runs inside the project's harness, after Prumo's core and the
adapters the project names. Everything Prumo writes to the publish folder is
named prumo-*, is removed when the run ends, and is never counted as the
project's own code.
"""
import contextlib
import os
import re
import urllib.request

from . import browser

_SERVED = {}


def served(config):
    """The page the harness stands in for, as the app serves it now."""
    if config.mirror not in _SERVED:
        with urllib.request.urlopen(config.base + config.mirror) as response:
            _SERVED[config.mirror] = response.read().decode("utf-8")
    return _SERVED[config.mirror]


def _styling(page):
    """The stylesheets a document loads and the styles it inlines, in order."""
    links = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', page)
    inline = [re.sub(r"/\*.*?\*/|\s+", " ", block, flags=re.S).strip()
              for block in re.findall(r"<style>(.*?)</style>", page, flags=re.S)]
    return links, inline


def _harness(config):
    with open(config.harness, encoding="utf-8") as source:
        return source.read()


def ensure_same_styling(config):
    """A harness must style the page exactly as the served document does: a
    stylesheet only the harness loads changes the cascade every check runs
    against, and the suite then measures a page nobody is served."""
    if not config.mirror:
        return
    mirrored, harness = _styling(served(config)), _styling(_harness(config))
    if mirrored != harness:
        raise SystemExit("%s styles the page differently from %s:\n  served:  %s\n  harness: %s"
                         % (os.path.basename(config.harness), config.mirror, mirrored, harness))


def own_files(config):
    """Prumo's scripts as the page loads them: the core, then each adapter."""
    return [("prumo-core.js", "core.js")] + [("prumo-%s.js" % name, "adapters/%s.js" % name) for name in config.adapters]


def build(config, body):
    """The harness with the mirrored preloads, Prumo's scripts and `body`.

    Each scenario runs in its own function scope: at the top level of a
    classic script, `var name = function ...` would assign window.name, which
    stringifies whatever it is given."""
    page = _harness(config)
    if config.mirror:
        # Modules arrive as the served page asks for them, so the load a run
        # times is the load a reader gets.
        preloads = re.findall(r'<link rel="modulepreload"[^>]*>', served(config))
        page = page.replace("</head>", "\n".join(preloads) + "\n</head>", 1)
    scripts = "".join('<script src="%s%s"></script>\n' % (config.publish_url, name) for name, _ in own_files(config))
    if page.count("</body>") != 1:
        raise SystemExit("%s must close its body exactly once" % config.harness)
    return page.replace("</body>", "%s<script>\n(function () {\n%s\n})();\n</script>\n</body>" % (scripts, body), 1)


def read(path):
    with open(path, encoding="utf-8-sig") as source:
        return source.read()


@contextlib.contextmanager
def published(config, pages):
    """Writes Prumo's scripts and `pages` ({name: html}) to the publish folder
    for the duration of a run, and removes them whatever happens."""
    if not os.path.isdir(config.publish_dir):
        raise SystemExit("No %s: build the app first." % config.publish_dir)
    ensure_same_styling(config)
    written = []
    try:
        for name, source in own_files(config):
            written.append(_write(config, name, browser.script(source)))
        for name, html in pages.items():
            written.append(_write(config, name, html))
        yield
    finally:
        for path in written:
            if os.path.exists(path):
                os.remove(path)


def _write(config, name, text):
    path = config.published(name)
    with open(path, "w", encoding="utf-8", newline="\n") as target:
        target.write(text)
    return path
