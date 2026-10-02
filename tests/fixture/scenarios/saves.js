// @widths 1280,375
// Save shows "Saved", waited for on the condition, not a clock.
V.until(function () { return document.body.getAttribute('data-decorated') === 'yes'; }, function () {
  document.querySelector('#save').click();
  V.until(function () { return V.text('.status') === 'Saved'; }, function () {
    check('the status says Saved', V.text('.status') === 'Saved', V.text('.status'));
    done();
  });
});
