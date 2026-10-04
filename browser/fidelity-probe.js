// Measures the elements a project's roles name on whichever side it runs:
// the reference page opened from disk, or the page inside the project's
// harness. `prumo fidelity` runs it on both and prints what differs. Boxes
// are relative to the first role, the frame, so a page that places the frame
// elsewhere compares by layout.
window.__fidelity = function (side, roles) {
  const PROPS = ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'textTransform', 'color',
               'backgroundColor', 'backgroundImage', 'boxShadow', 'borderRadius', 'padding', 'gap', 'opacity',
               'backdropFilter', 'borderTopWidth', 'borderTopColor', 'textAlign', 'display'];
  const column = side === 'mock' ? 1 : 2;
  const frame = document.querySelector(roles[0][column]).getBoundingClientRect();

  function find(selector) {
    const parts = selector.split('|');
    const all = document.querySelectorAll(parts[0]);
    return all[parts[1] ? Number(parts[1]) : 0] || null;
  }
  function measure(element) {
    const r = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const round = window.__fidelityExact ? function (v) { return Math.round(v * 100) / 100; } : Math.round;
    const out = { x: round(r.x - frame.x), y: round(r.y - frame.y), w: round(r.width), h: round(r.height) };
    PROPS.forEach(function (p) { out[p] = p === 'fontFamily' ? style[p].split(',')[0].replace(/["']/g, '').trim() : style[p]; });
    if (element instanceof SVGElement) out.stroke = style.stroke + ' ' + style.strokeWidth;
    const text = element.childNodes.length && [].some.call(element.childNodes, function (n) { return n.nodeType === 3 && n.textContent.trim(); });
    if (text) out.text = element.textContent.trim().replace(/\s+/g, ' ').slice(0, 60);
    return out;
  }

  const result = {};
  roles.forEach(function (role) {
    const selector = role[column];
    if (!selector) return;
    const element = find(selector);
    /* Present means drawn: an element under display:none has no boxes, and
       for the reader it is not there. */
    result[role[0]] = element && element.getClientRects().length ? measure(element) : null;
  });
  return result;
};
