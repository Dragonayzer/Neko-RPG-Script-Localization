# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

def cjk(s): return any('一' <= c <= '鿿' for c in s)

existing = set()
lr1 = re.compile(r"^\s*'(.+?)':\s*'(.*?)',\s*$")
lr2 = re.compile(r"^\s*\['(.+?)',\s*'(.*?)'\],?\s*$")
for l in open('../Script.txt', encoding='utf-8'):
    for lr in (lr1, lr2):
        m = lr.match(l)
        if m and cjk(m.group(1)):
            existing.add(m.group(1))

STR = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')

for fn in ['main.js', 'display.js']:
    txt = open('../NekoRPG/src/' + fn, encoding='utf-8').read()
    uniq = []; seen = set()
    for m in STR.finditer(txt):
        s = next(g for g in m.groups() if g is not None)
        if s and cjk(s) and s not in seen:
            seen.add(s); uniq.append(s)
    new = [s for s in uniq if s not in existing]
    dyn = [s for s in new if '${' in s or '<' in s]
    static = [s for s in new if '${' not in s and '<' not in s]
    short = [s for s in static if len(s) <= 14 and not any(p in s for p in '。，！？')]
    longp = [s for s in static if s not in short]
    with open('_ui_%s_short.tsv' % fn.replace('.js',''), 'w', encoding='utf-8') as f:
        for s in short: f.write(s + '\t\n')
    with open('_ui_%s_long.tsv' % fn.replace('.js',''), 'w', encoding='utf-8') as f:
        for s in longp: f.write(s + '\t\n')
    with open('_ui_%s_dynamic.tsv' % fn.replace('.js',''), 'w', encoding='utf-8') as f:
        for s in dyn: f.write(s + '\t\n')
    print("===== %s: %d CJK, %d not in script =====" % (fn, len(uniq), len(new)))
    print("  static short (label-like): %d" % len(short))
    print("  static long (prose)      : %d" % len(longp))
    print("  dynamic (${}/html)       : %d" % len(dyn))
    print()
