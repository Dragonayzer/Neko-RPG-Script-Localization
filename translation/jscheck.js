// jscheck.js - ground truth. Runs the ACTUAL generated proseExact/proseRegex/
// proseFrag from a built Script.txt, in a real JS engine, against one probe
// string. Every other checker here is a Python re-implementation of applyProse,
// and those have been wrong before (audit_coverage twice). When a player report
// disagrees with the Python tools, this settles it.
//
//   node translation/jscheck.js Script.txt "基础攻击,防御,敏捷 + 3000"
//   node translation/jscheck.js releases/Neko_RPG_Localization_8.6.txt "..."
//
// Prints the text after the regex stage (naming the rule that fired, or listing
// the rules that passed the indexOf hint filter but did not match) and after the
// fragment stage - which is what isolates an ordering bug from a missing entry.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

function grab(startMarker, endMarker) {
  const i = src.indexOf(startMarker);
  const j = src.indexOf(endMarker, i);
  return src.slice(i, j + endMarker.length);
}

const rxSrc = grab('const proseRegex = [', '].map((r) => [new RegExp(r[0]), r[1], r[2]]);');
// the dicts contain '});' inside string values, so anchor on the indented close
const fgSrc = grab('const proseFrag = Object.assign(Object.create(null), {', '\n    });');
const exSrc = grab('const proseExact = Object.assign(Object.create(null), {', '\n    });');

// strip the statement's trailing ';' - wrapping it in parens is a SyntaxError
const body = (s, decl) => s.replace(decl, '').replace(/;\s*$/, '');
const proseRegex = eval(body(rxSrc, 'const proseRegex ='));
const proseFrag  = eval('(' + body(fgSrc, 'const proseFrag =') + ')');
const proseExact = eval('(' + body(exSrc, 'const proseExact =') + ')');
const proseFragRe = new RegExp(Object.keys(proseFrag)
    .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');

const probe = process.argv[3];
let text = probe.trim();

if (proseExact[text]) {
  console.log('EXACT ->', proseExact[text]);
  process.exit(0);
}
// applyProse also retries the exact lookup with leading separators / wrapping
// quotes stripped ("core"). Without this the oracle reports false failures on
// every quoted dialogue option.
const core = text
    .replace(/^["“”'：:、，,．\-–—\s]+/, '')
    .replace(/["“”'\s]+$/, '');
if (core && core !== text && proseExact[core]) {
  console.log('EXACT(core) ->', proseExact[core]);
  process.exit(0);
}
// --complete mirrors the early precise pass (regexMustComplete): only a rule
// that FULLY resolves the node is taken, so a half-translating rule cannot
// block the v4.0 pair that would have rendered the whole phrase.
const mustComplete = process.argv.includes('--complete');
const IDEO_RE = /[一-鿿]/;
// myriad units are pending work for formatMyriad (stage 4), not untranslated
// Chinese - mirrors residualChinese() in applyProse
const MYRIAD_RE = /(\d+(?:\.\d+)?)\s*([万亿兆京垓秭穣沟涧正载极])/g;
const residualChinese = (t) => IDEO_RE.test(t.replace(MYRIAD_RE, '$1'));
// dialogue options render as `"${name}"`; anchored regexes must see past the
// quotes (mirrors applyProse)
const qm = text.match(/^(["“”']+)([\s\S]*)(["“”']+)$/);
const qPre = qm ? qm[1] : '', qPost = qm ? qm[3] : '';
let rxText = qm ? qm[2] : text;
let firedIdx = -1;
for (let i = 0; i < proseRegex.length; i++) {
  const rule = proseRegex[i];
  if (rxText.indexOf(rule[2]) === -1) continue;
  const next = rxText.replace(rule[0], rule[1]);
  if (next !== rxText) {
    if (mustComplete && residualChinese(next)) continue;
    firedIdx = i; rxText = next; break;
  }
}
text = qPre + rxText + qPost;
console.log('after regex stage :', JSON.stringify(text));
if (firedIdx >= 0) {
  console.log('  fired rule #' + firedIdx + ' hint=' + JSON.stringify(proseRegex[firedIdx][2]));
} else {
  console.log('  NO regex fired');
  // which rules even passed the indexOf hint filter?
  const seen = proseRegex.filter((r) => text.indexOf(r[2]) !== -1);
  console.log('  rules passing the hint filter: ' + seen.length);
  seen.slice(0, 6).forEach((r) => console.log('     hint=' + JSON.stringify(r[2]) +
      '  matches=' + r[0].test(text) + '  src=' + r[0].source.slice(0, 46)));
}
text = text.replace(proseFragRe, (m) => proseFrag[m] === undefined ? m : proseFrag[m]);
console.log('after frag stage  :', JSON.stringify(text));
