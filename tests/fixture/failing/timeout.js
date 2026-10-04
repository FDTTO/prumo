// A wait that runs out is named as the cause.
V.until(
  function () {
    return !!document.querySelector('#never-there');
  },
  function () {
    check('the element arrived', !!document.querySelector('#never-there'));
    done();
  },
  500,
);
