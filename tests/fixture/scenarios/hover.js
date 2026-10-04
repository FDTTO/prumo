// @alone
// A real pointer over the box, and the style only a real pointer brings.
V.until(
  function () {
    return !!document.querySelector('.box');
  },
  function () {
    V.hover('.box');
    V.until(
      function () {
        return document.querySelector('.box').matches(':hover');
      },
      function () {
        const box = document.querySelector('.box');
        check('the pointer is over the box', box.matches(':hover'));
        check(
          'the hover style applies',
          getComputedStyle(box).backgroundColor === 'rgb(9, 9, 9)',
          getComputedStyle(box).backgroundColor,
        );
        done();
      },
    );
  },
);
