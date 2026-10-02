// What the fixture page does: Save shows "Saved" a moment later. decorate()
// runs but nothing checks what it does; never() is never called.
function save() {
  setTimeout(function () { document.querySelector('.status').textContent = 'Saved'; }, 300);
}

function decorate() {
  document.body.setAttribute('data-decorated', 'yes');
}

function never() {
  return 'unreached';
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelector('#save').addEventListener('click', save);
  decorate();
});
