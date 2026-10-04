// What the core reads off the page: the rules behind a value, and the
// inventory of what the page renders.
V.until(function () { return !!document.querySelector('.status'); }, function () {
  const rules = V.rules('.status', 'color');
  check('rules names the rule that sets the colour', rules.some(function (rule) { return /\.status \{ color: rgb\(1, 2, 3\) \}/.test(rule); }), rules);
  const inventory = V.inventory();
  check('the inventory counts the type the page renders', inventory.type.distinct >= 1 && inventory.family.distinct >= 1, inventory.type);
  done();
});
