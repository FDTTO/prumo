# Prumo

*Prumo* is the Brazilian word for a plumb line: the weighted string a builder
holds against a wall to know it stands true to the plan, rather than taking
the wall's word for it.

Prumo checks a web page the same way. It drives the real page in a headless
Chromium on the real clock, and answers questions a unit test cannot:

| Question | Command |
|---|---|
| Did anything that used to work stop working? | `prumo suite` |
| Does this part render, measure and behave right? | `prumo run SCENARIO` |
| Which styles and functions does no scenario reach? | `prumo suite --coverage` |
| Would the suite notice if this function broke? | `prumo mutate` |
| Does the page match its design, property by property? | `prumo fidelity [STATE]` |
| Does a refactor leave the page looking the same? | `prumo run --clip` twice, then `prumo diff` |
| Does a site as it is served pass its checks? | `prumo visit SCENARIO --serve DIR` |

It needs Python 3.10+, Node 22+ and any Chromium (Edge, Chrome or Chromium,
found where they install, or named with `--browser` / `PRUMO_BROWSER`). No
packages: the standard libraries of both, plus Pillow for `diff` only.

## How a project uses it

Add Prumo as a submodule and describe the page in a `prumo.json` at the
project's root:

```
git submodule add https://github.com/FDTTO/prumo tools/prumo
python tools/prumo suite
```

```json
{
  "base": "http://localhost:8080",
  "publish": { "dir": "target/classes/static/app", "url": "/app/" },
  "harness": "test/ui/harness.html",
  "mirror": "/index.html",
  "adapters": ["swagger-ui"],
  "scenarios": "test/ui/scenarios"
}
```

- **publish**: a folder the running app serves, and the URL it serves it
  under. Prumo writes its pages there for a run and removes them after; the
  files found there are what coverage and mutation work on.
- **harness**: the project's page that boots what is checked, with nothing
  else. Scenarios run inside it.
- **mirror** (optional): the served page the harness stands in for. Its
  module preloads are copied into the harness, and a harness that loads
  different stylesheets than it is refused.
- **adapters**: helpers for what the page is built on; `swagger-ui` for
  Swagger UI 5.
- **fidelity** (optional): see [Matching the design](#matching-the-design).

## Scenarios

A scenario is plain JavaScript, run inside the harness after Prumo's core
and adapters, in its own function scope:

```js
// @widths 375,1280
// A saved draft survives a reload.
V.until(function () { return !!document.querySelector('#editor'); }, function () {
  document.querySelector('#save').click();
  V.until(function () { return V.text('#status') === 'Saved'; }, function () {
    check('the draft is saved', V.text('#status') === 'Saved', V.text('#status'));
    done();
  });
});
```

`check(name, pass, detail)` is an expectation, `L(key, value)` a recorded
value, `done()` the end of the run. A run fails when a check fails, a
console error is logged, or it never calls `done()`. The header sets
`@widths`, `@wait` (a ceiling in ms), `@virtual MS` (virtual time) and
`@alone` (run by itself, after the parallel batch).

The core's `V`:

- `V.until(ready, then, timeoutMs)`: wait for a condition, never a clock. On
  timeout it continues, so the checks that follow fail with what they saw,
  and the condition's source is logged as the cause.
- `V.press(key)`, `V.hover(selector)`: real, trusted input delivered by the
  runner: `Tab`, `Shift+Tab`, `Enter`, `Escape`, `Space`, arrows.
- `V.text(selector)`, `V.box(selector)`, `V.jwt(seconds, claims)`.
- `V.rules(selector, property)`: every rule that matches the element and
  declares the property, in source order, with its layer or media. The
  answer to "why does this value not take" without a debugger.
- `V.inventory()`: every distinct radius, type size, family and border the
  page renders, with counts. A coherent system has few values; a rare one is
  usually a leftover.
- `allowErrors(regex)`: console errors a scenario provokes on purpose.

The `swagger-ui` adapter adds `V.open`, `V.execute` (open, Try it out,
fill, Execute, each step waiting for what it presses), `V.fakeResponse`,
`V.authorize`, `V.held`, `V.logoutHeld`, `V.response`, `V.status`,
`V.json`, `V.param` and `V.definition`.

## Coverage and mutation

`prumo suite --coverage` records, in every run, which style rules of the
publish folder's stylesheets were applied and which functions of its
scripts ran, and ends with what no scenario reached, by file and line. The
browser reports only the rules it applied, so the total comes from parsing
the stylesheets on disk: a stylesheet no run loaded counts whole.

`prumo mutate` then knocks one named function out at a time (a `return;` as
its first statement), serves the mutant and runs only the scenarios that
coverage shows running it. A failing run kills the mutant; a green one means
the function could stop working unnoticed. Calibrate it before trusting a
score: a function a scenario is known to check must be killed, and one
nothing checks must survive. `--only` and `--sample` narrow a pass.

## Matching the design

`prumo fidelity` opens a reference page from disk (a mockup) and the real
page through the harness, in the same state and viewport, measures pairs of
elements on both, and prints every property that differs, reference value
first. A screenshot says that two pages differ; this says which property of
which element.

```json
"fidelity": {
  "states": "design/fidelity/states",
  "roles": "design/fidelity/roles.js",
  "include": ["design/fidelity/shared.js"],
  "hide": [".picker"],
  "viewport": [1440, 900]
}
```

A state is a scenario named for it, whose header names the reference and
which brings the page there, then calls `measure()`:

```js
// @reference design/mockup.html#empty
V.until(function () { return !!document.querySelector('.list'); }, measure);
```

Roles pair a selector on each side, `[role, reference, page]`, in
`window.__fidelityRoles`; the first is the frame every box is measured
from. A role neither side draws in a state is not a difference; one side
drawing it and the other not is. `--exact` measures boxes to a hundredth of
a pixel, `--shots` saves both viewports for `prumo diff`.

## Why it works this way

**The real clock by default.** A virtual-time budget skips idle time, so
anything paced by timers against a real backend (a poll that backs off 1s,
2s, 4s) spends its whole schedule in under a second and reports a state no
reader ever sees. `--virtual` exists for long, mostly idle scenarios, and
cannot judge animation frames.

**Conditions, not clocks.** A check that reads at a fixed time passes on a
fast machine and fails on a loaded one, or worse, reads the previous state
and passes. Every wait in the core and adapters is on a condition, and a
run under `--coverage`, which slows the page, is the stress test that finds
the clocks left in a scenario.

**The harness mirrors what is served.** A harness that copies configuration
by hand drifts from production, and the suite then measures a page nobody
receives. The harness reads the served configuration where it can; Prumo
copies the served page's module preloads into it and refuses to run when
the two load different stylesheets.

**Trusted input for what only trusted input shows.** Chromium shows
`:focus-visible` only after real keyboard input and `:hover` only under a
real pointer; a synthetic event from the page proves neither. Input is sent
over the DevTools protocol, and scenarios that send it run alone, since
browsers in parallel contend for it.

**The process that outlives the browser owns its profile.** On Windows the
launched browser hands off to another process and exits, and under load the
profile's files stay locked for seconds after the browser closes. Prumo
creates each profile, hands it to the runner, and reclaims it after the
runner exits, waiting out the locks; a profile that still cannot be removed
fails the run. A runner that only warned once left 1.7 GB of profiles behind
before anyone noticed.

**What it publishes, it removes.** Pages and scripts Prumo writes are named
`prumo-*`, removed when the run ends even on failure, and never counted as
the project's code.

## Traps it already paid for

- **Programmatic focus is not keyboard focus.** After a click, `focus()` is
  pointer focus and never enters `:focus-visible`. Walk with `V.press('Tab')`.
- **A headless page may not hold the window's focus**, and keys sent to it
  go nowhere. The runner enables focus emulation.
- **Virtual time freezes transitions and starves `requestAnimationFrame`.**
  The browser runs with reduced motion (`--motion` keeps transitions); a
  harness whose page repaints through rAF should schedule it on a timer.
- **`--window-size` is ignored for pages opened over the protocol.** The
  runner sets the viewport itself, so 320px works.
- **A fixed debugging port can attach to a previous run** still shutting
  down. The runner uses port 0 and reads `DevToolsActivePort`.
- **`var name` at a script's top level is `window.name`**, which turns a
  function into a string. Scenarios run in their own function scope.
- **Existing in the DOM is not being visible.** A 0x0 dialog inside a
  hidden ancestor passes any existence check. Assert painted size and hit
  testing for anything a reader must see.

## Method

- **A check has to be able to fail.** Before trusting a pass, ask whether
  the same check would have failed for the symptom. Prove it by sabotaging
  what it guards, and read what the sabotaged run measured, not only its
  verdict: a sabotage can miss for reasons of its own.
- **Calibrate the instrument before the measurement.** Two runs of
  unchanged code must agree (`prumo diff` reports `identical`); a mutation
  pass must kill what is checked and spare what is not.
- **One claim per verified thing.** A change that touches two places is
  verified in both.
- **When a result disagrees with itself, instrument before theorising.** A
  copy of the scenario that logs the state at the moment of the check names
  the cause in one run.

## Layout

```
__main__.py              the command line
prumo/                   configuration, pages, runs, coverage, mutation, fidelity, diff, visit
browser/runner.js        one page over the DevTools protocol
browser/core.js          what a scenario uses in the page
browser/adapters/        helpers per framework
browser/fidelity-probe.js
tests/                   Prumo's own checks, against a fixture site
```
