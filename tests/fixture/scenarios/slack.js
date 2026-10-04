// A wait for something that never comes, after which the checks still pass:
// the run passes, and says the wait ran out.
V.until(function () { return !!document.querySelector('#never-there'); }, function () {
  check('the page is still here', !!document.querySelector('.box'));
  done();
}, 300);
