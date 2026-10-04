/* Prumo inside the page: what a scenario records with and acts through.
 *
 * A scenario records findings with L(key, value) and expectations with
 * check(name, pass, detail), and calls done() when it has finished; the
 * runner reads window.__log back. Console errors and uncaught errors are
 * collected on their own, so "no errors" is always part of the result rather
 * than something a scenario has to remember to check.
 */
(function () {
  // biome-ignore lint/suspicious/noRedundantUseStrict: a classic script injected by <script src>, not a module
  'use strict';
  /* Every run starts with nothing remembered. */
  try { localStorage.clear(); sessionStorage.clear(); } catch { /* storage blocked */ }

  const log = { errors: [], checks: [] };
  window.__log = log;
  window.L = function (key, value) { log[key] = value; };

  /* What makes a scenario a test rather than a probe: a named expectation
     that passes or fails, with what was actually seen when it fails. */
  window.check = function (name, pass, detail) {
    log.checks.push({ name: name, pass: !!pass, detail: detail === undefined ? null : detail });
  };

  /* A scenario says when it has finished. The runner reads the log as soon
     as it does, and a run that never says so fails as unfinished. */
  window.done = function () { log.done = true; };

  /* A scenario that provokes an error on purpose declares it, and only the
     errors it names stop counting against the run; everything else still
     fails it. */
  const allowed = [];
  window.allowErrors = function (pattern) { allowed.push(pattern); };

  const consoleError = console.error;
  console.error = function (...args) {
    const parts = args.map(function (a) { return a && a.stack ? a.stack : String(a); });
    const text = parts.join(' ').slice(0, 400);
    const expected = allowed.some(function (pattern) { return pattern.test(text); });
    if (expected) {
      log.expectedErrors ??= [];
      log.expectedErrors.push(text);
    } else {
      log.errors.push(text);
    }
    return consoleError.apply(console, args);
  };
  window.addEventListener('error', function (event) {
    log.errors.push('uncaught: ' + (event.error && event.error.stack || event.message).slice(0, 400));
  });

  const input = function (event) {
    window.__prumoInput ??= [];
    window.__prumoInput.push(event);
  };

  window.V = {
    /* Waits for a condition instead of a fixed time, then continues either
       way: on timeout the checks that follow fail with what they saw. A
       condition that throws (the page still booting) counts as not yet.
       A timeout is also logged with the condition's source, because the
       check that fails after it can name a symptom far from the cause. */
    until: function (ready, then, timeoutMs) {
      const deadline = Date.now() + (timeoutMs || 10000);
      const met = function () { try { return ready(); } catch { return false; } };
      (function poll() {
        if (met()) return then();
        if (Date.now() > deadline) {
          log.timeouts ??= [];
          log.timeouts.push(String(ready).replace(/\s+/g, ' ').slice(0, 140));
          return then();
        }
        setTimeout(poll, 100);
      })();
    },
    /* Real keyboard input, delivered by the runner as trusted events (real
       clock only): "Tab", "Shift+Tab", "Enter", "Escape", "Space", arrows. */
    press: function (key) { input(key); },
    /* A real pointer over the element, delivered by the runner like keys;
       wait for element.matches(':hover') before reading what it changes. */
    hover: function (selector) { input({ hover: selector }); },
    /* A JWT whose only meaningful claim is its expiry, for pages that read
       `exp` without checking a signature. */
    jwt: function (expiresInSeconds, claims) {
      const encode = function (value) { return btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
      const payload = Object.assign({ sub: 'prumo' }, claims || {}, { exp: Math.floor(Date.now() / 1000) + expiresInSeconds });
      return encode({ alg: 'HS256' }) + '.' + encode(payload) + '.sig';
    },
    /* Every rule that matches the element and declares a property matching
       `property`, in source order, with the layer or media it sits in: the
       answer to "why does this value not take" without a debugger. */
    rules: function (selector, property) {
      const element = document.querySelector(selector), found = [], pattern = new RegExp(property);
      const walk = function (list, where) {
        Array.prototype.forEach.call(list, function (rule) {
          if (rule.styleSheet) return walk(rule.styleSheet.cssRules, where + ' @import ' + (rule.layerName || ''));
          if (!rule.selectorText) return rule.cssRules && walk(rule.cssRules, where + ' @' + (rule.name || rule.conditionText || rule.constructor.name));
          const declared = Array.prototype.filter.call(rule.style, function (name) { return pattern.test(name); });
          let matches = false;
          try { matches = element.matches(rule.selectorText); } catch { /* a pseudo-element selector */ }
          if (matches && declared.length) {
            found.push(where + ' | ' + rule.selectorText + ' { ' + declared.map(function (name) {
              return name + ': ' + rule.style.getPropertyValue(name) + (rule.style.getPropertyPriority(name) ? ' !important' : '');
            }).join('; ') + ' }');
          }
        });
      };
      Array.prototype.forEach.call(document.styleSheets, function (sheet) {
        try { walk(sheet.cssRules, (sheet.href || 'inline').split('/').pop()); } catch { /* cross-origin */ }
      });
      return found;
    },
    /* An interface inventory: every distinct corner radius, type size and
       weight, family and border the page renders, with how often each
       occurs and one element that uses it. A coherent system has few
       values; a rare one is usually a leftover. */
    inventory: function () {
      const tally = { radius: {}, type: {}, family: {}, border: {} };
      const name = function (node) {
        return node.tagName.toLowerCase() + (node.id ? '#' + node.id : '') +
          (typeof node.className === 'string' && node.className.trim() ? '.' + node.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
      };
      const add = function (kind, value, node) {
        if (!value || value === '0px' || value === 'none') return;
        tally[kind][value] ??= { count: 0, example: name(node) };
        const entry = tally[kind][value];
        entry.count++;
      };
      document.querySelectorAll('body *').forEach(function (node) {
        const box = node.getBoundingClientRect();
        if (!box.width || !box.height) return;
        const style = getComputedStyle(node);
        add('radius', style.borderTopLeftRadius, node);
        const ownText = Array.prototype.some.call(node.childNodes, function (child) {
          return child.nodeType === 3 && child.textContent.trim();
        });
        if (ownText) {
          add('type', style.fontSize + ' ' + style.fontWeight, node);
          add('family', style.fontFamily.split(',')[0].replace(/['"]/g, ''), node);
        }
        if (style.borderTopWidth !== '0px' && style.borderTopStyle !== 'none') add('border', style.borderTopWidth + ' ' + style.borderTopColor, node);
      });
      const result = {};
      Object.keys(tally).forEach(function (kind) {
        const rows = Object.keys(tally[kind]).map(function (value) {
          return tally[kind][value].count + '  ' + value + '  (' + tally[kind][value].example + ')';
        }).sort(function (a, b) { return parseInt(b, 10) - parseInt(a, 10); });
        result[kind] = { distinct: rows.length, values: rows };
      });
      return result;
    },
    text: function (selector) {
      const node = document.querySelector(selector);
      return node ? node.textContent.replace(/\s+/g, ' ').trim() : null;
    },
    box: function (selector) {
      const node = document.querySelector(selector);
      if (!node) return null;
      const r = node.getBoundingClientRect();
      return { left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top + scrollY), width: Math.round(r.width), height: Math.round(r.height) };
    }
  };
})();
