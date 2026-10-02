/* Prumo's adapter for Swagger UI 5: acting on a page built by SwaggerUIBundle
 * through its own store (window.ui) and its own controls, as a reader would.
 * Loaded after core.js; adds to window.V.
 */
(function () {
  'use strict';
  var ui = function () { return window.ui; };
  /* Operations a scenario asked to open, before Swagger shows them as open. */
  var opening = {};

  Object.assign(window.V, {
    /* Opens a tag section and one operation, nothing more: not before `at`,
       and then as soon as the page has the section and the operation to
       click, since a click on a page still building finds nothing. */
    open: function (tag, operationId, at) {
      opening[tag + ' ' + operationId] = true;
      var section = function () { return document.querySelector('h3.opblock-tag[data-tag="' + tag + '"]'); };
      var block = function () { return document.getElementById('operations-' + tag + '-' + operationId); };
      setTimeout(function () {
        V.until(function () { return !!section(); }, function () {
          if (section() && section().getAttribute('data-is-open') === 'false') section().click();
          V.until(function () { return !!block(); }, function () {
            if (block() && !block().classList.contains('is-open')) block().querySelector('.opblock-summary-control').click();
          }, 15000);
        }, 15000);
      }, at || 0);
    },
    /* Opens an operation, presses Try it out, writes the body through
       React's own value setter (assigning .value directly does not notify
       React) and presses Execute. Each step waits for what it presses, so a
       slow page delays the call instead of losing it. */
    execute: function (tag, operationId, body, at) {
      var find = function (selector) { return document.querySelector('#operations-' + tag + '-' + operationId + ' ' + selector); };
      V.open(tag, operationId, at);
      setTimeout(function () {
        V.until(function () { return !!find('.try-out__btn'); }, function () {
          var tryOut = find('.try-out__btn');
          if (tryOut && !tryOut.classList.contains('cancel')) tryOut.click();
          V.until(function () { return !!find('button.execute') && (!body || !!find('textarea.body-param__text')); }, function () {
            var area = find('textarea.body-param__text');
            if (area && body) {
              Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(area, body);
              area.dispatchEvent(new Event('input', { bubbles: true }));
            }
            var run = find('button.execute');
            if (run) run.click();
          }, 15000);
        }, 15000);
      }, at || 0);
    },
    /* A response as if Execute had run, without touching the backend. The
       request is set too, plain and mutated, because Swagger's live response
       block reads the mutated one and crashes without it.
       An operation with a request body resolves when first opened, and
       resolving mounts the body's content-type control, whose mount clears
       the response. A fake set on an operation still resolving would vanish
       a moment later, so it fails here, out loud: wait for the operation's
       .responses-wrapper first. */
    fakeResponse: function (path, method, status, body, url, headers, duration) {
      var at = ['paths', path, method.toLowerCase()];
      var spec = ui().specSelectors.specJson();
      var tag = spec.getIn(at.concat(['tags', 0])), operationId = spec.getIn(at.concat('operationId'));
      var shown = opening[tag + ' ' + operationId] || ui().layoutSelectors.isShown(['operations', tag, operationId]);
      if (shown && spec.getIn(at.concat('requestBody')) && !ui().specSelectors.specResolvedSubtree(at)) {
        window.__log.errors.push('fakeResponse(' + method + ' ' + path + ') before the operation resolved: Swagger clears it on resolving');
      }
      var request = { url: url, method: method.toUpperCase(), headers: {} };
      ui().specActions.setRequest(path, method, request);
      ui().specActions.setMutatedRequest(path, method, request);
      ui().specActions.setResponse(path, method, {
        ok: status >= 200 && status < 300, status: status, url: url, headers: headers || {},
        text: body === null || body === undefined ? '' : JSON.stringify(body), duration: duration
      });
    },
    definition: function (scheme) { return ui().specSelectors.securityDefinitions().get(scheme); },
    /* Authorizes with the store's own immutable definition, as the dialog
       does; a plain object makes Swagger's persistence step throw. */
    authorize: function (scheme, value) {
      var payload = {};
      payload[scheme] = { name: scheme, schema: V.definition(scheme), value: value };
      ui().authActions.authorize(payload);
    },
    held: function (scheme) {
      var entry = ui().authSelectors.authorized().get(scheme);
      return entry && entry.get ? entry.get('value') : null;
    },
    /* Logs out only what is held: Swagger's logout throws on a scheme it
       does not hold. */
    logoutHeld: function () {
      var names = ui().authSelectors.authorized().keySeq().toArray();
      if (names.length) ui().authActions.logout(names);
    },
    response: function (path, method) { return ui().specSelectors.responseFor(path, method); },
    status: function (path, method) { var r = V.response(path, method); return r ? r.get('status') : null; },
    json: function (path, method) {
      var r = V.response(path, method);
      try { return JSON.parse(r.get('text')); } catch (ignored) { return null; }
    },
    param: function (path, method, key) {
      var values = ui().specSelectors.parameterValues([path, method]);
      return values ? values.get(key || 'path.id') || null : null;
    }
  });
})();
