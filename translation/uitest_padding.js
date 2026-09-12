// Chunk padding: the space a chunk keeps at an inline-tag boundary, and the
// keys that are deliberately refused one.
// Run against a BUILT script:  node uitest_padding.js ../Script.txt
//
// A chunk is one DOM text node and a tag boundary is not a word boundary, so
// "PS:对" + <span>云霄级</span> rendered "targetsSkyhigh-Tier" for seventeen
// versions. build.py now keeps the space the translator wrote - but only where
// the key means one thing, because proseExact is context-free and a value
// chosen beside a <span> is applied everywhere that key appears.
//
// Both directions are pinned here. A regression in the KEEP set glues words
// together again; a regression in the REFUSE set puts a stray space into a
// place that never wanted one, which is the more expensive mistake and the
// harder one to spot.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

// ---- read proseExact out of the built file ---------------------------------
function table(name) {
  const i = src.indexOf('const ' + name + ' = Object.assign');
  if (i === -1) throw new Error('no ' + name + ' block');
  const end = src.indexOf('\n    });', i);
  const out = Object.create(null);
  const row = /^        '((?:[^'\\]|\\.)*)': '((?:[^'\\]|\\.)*)',$/gm;
  const body = src.slice(i, end);
  let m;
  while ((m = row.exec(body))) {
    const un = (s) => s.replace(/\\(['\\nrt])/g, (_, c) =>
        ({ n: '\n', r: '\r', t: '\t' }[c] || c));
    out[un(m[1])] = un(m[2]);
  }
  return out;
}
const exact = table('proseExact');
const frag = table('proseFrag');

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(42) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// ---- kept: the space is load-bearing --------------------------------------
// Each of these sits immediately before an inline tag in the game's own HTML,
// so without the space the next chunk's first word is glued to the last one.
console.log('padding KEPT (space sits against an inline tag)');
[
  // display.js spec tooltip: "…效力削弱<span>10%</span>" -> "…weakened by 10%"
  ['PS:对', ' '],
  // spec 20: "…自身攻击<span>3倍</span>" -> "…difference between 3x"
  ['敌人每回合额外造成自身攻击', ' '],
].forEach(([k, tail]) => {
  const v = exact[k];
  expect('present: ' + k.slice(0, 18), typeof v, 'string');
  if (typeof v === 'string') {
    expect('ends with a space: ' + k.slice(0, 12), v.slice(-tail.length), tail);
  }
});

// The whole class, not just the samples: a floor, so a build that quietly
// stopped keeping padding fails here even if these two keys survive.
const padded = Object.keys(exact).filter((k) => exact[k] !== exact[k].trim());
expect('keys keeping padding, at least', padded.length >= 120, true);
console.log('       (actual: ' + padded.length + ')');

// ---- refused: the key means more than one thing ---------------------------
// 攻击 is a chunk here AND a standalone stat label in display.js; 获取了 is
// authored both with and without the space, so first-wins would be picking a
// spelling by file order. Both must ship unpadded.
console.log('\npadding REFUSED (key is shared or ambiguous)');
['攻击', '获取了'].forEach((k) => {
  const v = exact[k];
  if (typeof v !== 'string') { expect('present: ' + k, typeof v, 'string'); return; }
  expect('unpadded: ' + k, v, v.trim());
});

// ---- padding that predates this, and is not ours --------------------------
// A pair whose CHINESE carries padding ("点伤害。" arrives as " 点伤害。") has
// always been registered as a forced FRAGMENT with its spacing intact, and is
// popped back out of proseExact entirely. That path is the reason the fix
// above is shaped the way it is, so it is pinned rather than assumed.
console.log('\nforced fragments keep their own padding');
expect('点伤害。 is a fragment, not exact', '点伤害。' in exact, false);
expect('点伤害。 keeps its leading space', frag['点伤害。'], ' damage.');

// v17.9: index.html runs the realm span straight into this label with no
// separator, so English rendered "Dust-Tier Basicnewborn count:". The space is
// authored into the glossary value; nothing else can supply it, because the two
// nodes belong to different passes.
//
// v18.0: and it must stay SHORT. An 80px <input> shares the line, so the space
// alone pushed it onto the next row. Both halves are pinned - the leading space
// and a length under the 14 characters that fit before it.
expect('newborn label leads with a space',
       frag['新生儿数 :'].startsWith(' '), true);
expect('  and stays shorter than it was', frag['新生儿数 :'].length < 14, true);
console.log('       (' + JSON.stringify(frag['新生儿数 :']) + ')');

// ---- shape of what we did keep --------------------------------------------
// Catches a mangled build: padding must be ordinary spaces around real text,
// never a stray tab or newline, and never the whole value.
console.log('\nshape of the kept padding');
const malformed = padded.filter((k) => !/^ ?[^\s][\s\S]*[^\s] ?$|^ ?[^\s] ?$/.test(exact[k]));
expect('every padded value is text with spaces', malformed.length, 0);
if (malformed.length) malformed.slice(0, 5).forEach((k) => console.log('     ' + JSON.stringify(exact[k])));

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
