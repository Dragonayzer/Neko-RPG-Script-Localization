# -*- coding: utf-8 -*-
"""List every string the builder had to drop, with the chunk breakdown that
caused it, and (where possible) the done_*.tsv row to edit.

A drop means the Chinese and English disagree on how many DOM text nodes the
string becomes, so pairing them would put the wrong English in the wrong node.
Nearly all are cases where the English merged or split lines relative to the
Chinese - fixable by moving <br> placement in the translation.
"""
import re, sys, os, glob
sys.stdout.reconfigure(encoding='utf-8')

src = open('build.py', encoding='utf-8').read()
head = src.split('# ------------------------------------------------------- split into EXACT/FRAG')[0]
g = {'__name__': 'x', '__file__': 'build.py'}
exec(head, g)
pairs = g['pairs']
cjk = g['cjk']
TAG = re.compile(r'<[^>]*>')

# where did each English string come from? map en -> (file, key)
origin = {}
for p in sorted(glob.glob('prose/done_*.tsv')) + ['prose/items_desc.tsv']:
    if not os.path.exists(p):
        continue
    for line in open(p, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        c = line.rstrip('\n').split('\t')
        if len(c) >= 2:
            origin.setdefault(c[-1], (os.path.basename(p), c[0]))

BR = ('<br>', '<br/>', '<br />')
rows = []
for zh, en in pairs.items():
    if '<' not in zh:
        continue
    cz, ce = TAG.split(zh), TAG.split(en)
    if len(cz) == len(ce):
        continue
    tags = TAG.findall(zh) + TAG.findall(en)
    br_only = all(t.lower() in BR for t in tags)
    if br_only:
        continue                       # rebalance_br already handles these
    rows.append((zh, en, cz, ce))

print('unpairable (non-<br> tag structure): %d\n' % len(rows))
for i, (zh, en, cz, ce) in enumerate(rows, 1):
    f, k = origin.get(en, ('?', '?'))
    print('--- %d/%d  [%s row %s]  zh=%d en=%d  (need en=%d)'
          % (i, len(rows), f, k, len(cz), len(ce), len(cz)))
    print('   ZH tags: %s' % ' '.join(TAG.findall(zh)))
    print('   EN tags: %s' % ' '.join(TAG.findall(en)))
    for j, c in enumerate(cz):
        print('   z%-2d %s' % (j, c[:88]))
    for j, c in enumerate(ce):
        print('   e%-2d %s' % (j, c[:88]))
    print()
