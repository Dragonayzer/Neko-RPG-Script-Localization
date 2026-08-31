// compactMaxedSkillBars(): every toggle combination, maxed vs live bars.
// Cosmetic behaviour lives in JS and the Python suite cannot reach it.
// Run against a BUILT script:  node uitest_maxbars.js ../Script.txt
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

const reSrc = src.match(/const MAXED_RE = [^\n]+/)[0];
const fnSrc = src.slice(src.indexOf('    function compactMaxedSkillBars() {'));
const end = fnSrc.indexOf('\n    }\n');
if (end === -1) throw new Error('could not slice function body');
const fnBody = fnSrc.slice(0, end + 7);

function mkBar(name, xp) {
  const n = { textContent: name };
  const x = { textContent: xp };
  const fill = { style: {}, cls: 'skill_bar_current' };
  const text = { children: [n, x] };
  return {
    firstElementChild: text, style: {},
    querySelector: (sel) => (sel === '.skill_bar_current' ? fill : null),
    _n: n, _x: x, _fill: fill,
  };
}

// Returns the two bars after one run of the shipped function under `env`.
function run(env) {
  const maxed = mkBar('Night Vision : level 20/20', 'Max!');
  const live = mkBar('Combat : level 12/60', '48.2%');
  const document = { querySelectorAll: () => [maxed, live] };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const COMPACT_MAXED_SKILL_BARS = env.compact;
  const MAXED_BAR_HIGHLIGHT = env.highlight;
  // read the colours actually shipped, so this test cannot pass on stale values
  const MAXED_BAR_BG = eval(src.match(/const MAXED_BAR_BG = [^;]+/)[0].split('=')[1]);
  const MAXED_BAR_BORDER = eval(src.match(/const MAXED_BAR_BORDER = [^;]+/)[0].split('=')[1]);
  eval(reSrc + '\n' + fnBody);
  compactMaxedSkillBars();
  compactMaxedSkillBars();   // idempotency
  return { maxed, live };
}

for (const compact of [true, false]) {
  for (const highlight of [true, false]) {
    const { maxed, live } = run({ master: true, compact, highlight });
    console.log('compact=' + (compact ? 'on ' : 'off') +
                '  highlight=' + (highlight ? 'on ' : 'off'));
    console.log('   maxed name : ' + JSON.stringify(maxed._n.textContent));
    console.log('   maxed xp   : ' + JSON.stringify(maxed._x.textContent));
    console.log('   maxed style: bg=' + JSON.stringify(maxed.style.backgroundColor) +
                ' border=' + JSON.stringify(maxed.style.borderColor) +
                ' fillH=' + JSON.stringify(maxed._fill.style.height));
    console.log('   NON-maxed  : ' + JSON.stringify(live._n.textContent) +
                '  bg=' + JSON.stringify(live.style.backgroundColor) +
                ' fillH=' + JSON.stringify(live._fill.style.height));
  }
}

// ---- WIRING: compaction must also run off-throttle ------------------------
// Every case above exercises the function in isolation, which cannot see WHEN
// it runs - and that was the bug: the name was restored in the mutation batch
// while the compaction waited for the throttled scan(), so a maxed bar whose
// skill gains XP every tick flickered between the two renderings. Assert the
// call site, since nothing else can.
const hotFn = src.slice(src.indexOf('    function translateHot() {'));
const hotBody = hotFn.slice(0, hotFn.indexOf('\n    }\n'));
const wired = hotBody.indexOf('compactMaxedSkillBars();') !== -1;
console.log('\ntranslateHot re-compacts in the same batch : ' + (wired ? 'YES' : 'NO'));
if (!wired) {
  console.log('   maxed bars will flicker between compacted and uncompacted');
  process.exit(1);
}
// Order matters too: the name has to be English before it is compacted.
const nameFirst = hotBody.indexOf('HOT_SEL') < hotBody.indexOf('compactMaxedSkillBars();');
console.log('name translated before compaction          : ' + (nameFirst ? 'YES' : 'NO'));
if (!nameFirst) process.exit(1);

// The master switch has to beat both sub-toggles being on - that is the whole
// point of it, and a `&&` where an `||` belongs would still pass every case
// above.
const off = run({ master: false, compact: true, highlight: true });
const untouched = off.maxed._n.textContent === 'Night Vision : level 20/20' &&
                  off.maxed._x.textContent === 'Max!' &&
                  off.maxed.style.backgroundColor === undefined &&
                  off.maxed._fill.style.height === undefined;
console.log('\nENABLE_VISUAL_OVERRIDES=false, both sub-toggles on');
console.log('   bar left exactly as the game wrote it : ' + (untouched ? 'YES' : 'NO'));
if (!untouched) { console.log('   ', JSON.stringify(off.maxed._n.textContent),
                              JSON.stringify(off.maxed.style)); process.exit(1); }
