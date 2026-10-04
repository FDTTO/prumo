"""A project's prumo.json: everything Prumo needs to know about the page it checks.

    {
      "base": "http://localhost:8080",
      "publish": {"dir": "target/classes/static/app", "url": "/app/"},
      "harness": "test/harness.html",
      "mirror": "/index.html",
      "adapters": ["swagger-ui"],
      "scenarios": "test/scenarios",
      "fidelity": {
        "states": "test/fidelity/states",
        "roles": "test/fidelity/roles.js",
        "include": ["test/fidelity/shared.js"],
        "hide": [".picker"],
        "viewport": [1440, 900]
      }
    }

`publish` is a folder the running app serves and the URL it serves it under:
Prumo writes its pages there for a run and removes them after, and coverage
and mutation work on the files found there. `harness` is the project's page
that boots what is checked. `mirror` is the served page the harness stands in
for: its module preloads are copied in, and a harness styled differently from
it is refused. Paths are relative to the folder holding prumo.json.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field

FILE = "prumo.json"


@dataclass(frozen=True)
class Fidelity:
    states: str = None
    roles: str = None
    include: tuple = ()
    hide: tuple = ()
    viewport: tuple = (1440, 900)


@dataclass(frozen=True)
class Config:
    root: str
    base: str
    publish_dir: str
    publish_url: str
    harness: str
    mirror: str = None
    adapters: tuple = ()
    scenarios: str = None
    fidelity: Fidelity = field(default_factory=Fidelity)
    path: str = None

    def url(self, name=""):
        """Where the app serves a file of the publish folder."""
        return self.base + self.publish_url + name

    def published(self, name):
        return os.path.join(self.publish_dir, name)

    @property
    def out(self):
        """Where this project's logs, screenshots and coverage go: one folder
        per project, so a run of one never reads or clears another's."""
        return os.path.join(tempfile.gettempdir(), "prumo", hashlib.sha1(self.root.encode("utf-8")).hexdigest()[:10])


def find(start):
    folder = os.path.abspath(start)
    while True:
        candidate = os.path.join(folder, FILE)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(folder)
        if parent == folder:
            raise SystemExit(f"No {FILE} here or in any folder above {os.path.abspath(start)}")
        folder = parent


def load(path=None, base=None):
    """The configuration at `path`, or the nearest one above the working
    directory; `base` overrides the app's address, e.g. a second instance."""
    path = path or find(os.getcwd())
    root = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8") as source:
        raw = json.load(source)

    def resolve(relative):
        return os.path.join(root, relative) if relative else None

    for required in ("base", "publish", "harness"):
        if required not in raw:
            raise SystemExit(f'{path}: missing "{required}"')
    fidelity = raw.get("fidelity") or {}
    # "/app/" for a folder, "/" for the root: never "//", which a browser
    # reads as a protocol-relative URL to another host.
    folder = raw["publish"]["url"].strip("/")
    publish_url = "/" + folder + "/" if folder else "/"
    return Config(
        path=os.path.abspath(path),
        root=root,
        base=(base or raw["base"]).rstrip("/"),
        publish_dir=resolve(raw["publish"]["dir"]),
        publish_url=publish_url,
        harness=resolve(raw["harness"]),
        mirror=raw.get("mirror"),
        adapters=tuple(raw.get("adapters") or ()),
        scenarios=resolve(raw.get("scenarios")),
        fidelity=Fidelity(
            states=resolve(fidelity.get("states")),
            roles=resolve(fidelity.get("roles")),
            include=tuple(resolve(p) for p in fidelity.get("include") or ()),
            hide=tuple(fidelity.get("hide") or ()),
            viewport=tuple(fidelity.get("viewport") or (1440, 900)),
        ),
    )
