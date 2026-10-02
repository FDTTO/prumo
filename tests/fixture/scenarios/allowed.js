// An error provoked on purpose and declared does not fail the run.
allowErrors(/expected noise/);
console.error('expected noise');
check('this passes', true);
done();
