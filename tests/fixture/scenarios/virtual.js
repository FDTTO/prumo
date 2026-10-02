// @virtual 20000
// On virtual time, a long timer fires without waiting it out in real time.
setTimeout(function () {
  check('a ten second timer fired', true);
  done();
}, 10000);
