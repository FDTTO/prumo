// @alone
// A real Tab reaches Save, and only a real key shows its focus ring.
V.press('Tab');
V.until(function () { return document.activeElement && document.activeElement.id === 'save'; }, function () {
  const save = document.querySelector('#save');
  check('Tab reaches Save in :focus-visible', save.matches(':focus-visible'));
  check('the ring is drawn', getComputedStyle(save).outlineStyle === 'solid', getComputedStyle(save).outlineStyle);
  done();
});
