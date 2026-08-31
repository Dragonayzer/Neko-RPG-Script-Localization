# -*- coding: utf-8 -*-
"""Find literal Chinese myriad-unit numbers, and the transliterated units I left
in the English (Zhao / Jing / Gai / Zi ...), which mean nothing to a reader."""
import re, sys, glob, os, collections
sys.stdout.reconfigure(encoding='utf-8')

UNITS = {'万': 4, '亿': 8, '兆': 12, '京': 16, '垓': 20, '秭': 24,
         '穣': 28, '沟': 32, '涧': 36, '正': 40, '载': 44, '极': 48}
TRANSLIT = ['Wan', 'Yi', 'Zhao', 'Jing', 'Gai', 'Zi', 'Rang', 'Gou', 'Jian']

NUM_ZH = re.compile(r'(\d[\d,\.]*)\s*([' + ''.join(UNITS) + r'])')
NUM_TL = re.compile(r'(\d[\d,\.]*)\s*(' + '|'.join(TRANSLIT) + r')\b')

zh_hits, tl_hits = collections.Counter(), collections.Counter()
files = collections.Counter()

for p in sorted(glob.glob('prose/done_*.tsv') + glob.glob('prose/items_desc.tsv')
                + glob.glob('glossary/*.tsv')):
    for line in open(p, encoding='utf-8'):
        if line.startswith('#'):
            continue
        cols = line.rstrip('\n').split('\t')
        en = cols[-1] if cols else ''
        for m in NUM_TL.finditer(en):
            tl_hits[m.group(0)] += 1
            files[os.path.basename(p)] += 1
        # a Chinese unit left sitting in the English column
        for m in NUM_ZH.finditer(en):
            zh_hits[m.group(0)] += 1
            files[os.path.basename(p)] += 1

print('Transliterated units still in the English (%d distinct):' % len(tl_hits))
for k, v in tl_hits.most_common(40):
    print('   %-18s x%d' % (k, v))
print('\nChinese units still in the English (%d distinct):' % len(zh_hits))
for k, v in zh_hits.most_common(30):
    print('   %-18s x%d' % (k, v))
print('\nBy file:')
for k, v in files.most_common():
    print('   %-24s %d' % (k, v))
