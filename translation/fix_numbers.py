# -*- coding: utf-8 -*-
"""Rewrite transliterated myriad units in the translated prose into scientific
notation: "9999 Zhao" -> "9.999e15".

Chinese groups large numbers by 10^4 (万 亿 兆 京 垓 秭 ...). Transliterating the
unit ("Zhao", "Gai") carries none of the meaning for an English reader, so the
value is converted outright. Scientific notation is the target because that is
exactly what the game itself emits when its option_format_change setting is on,
so computed and hard-coded numbers end up looking the same.

Only the English column of the prose files is touched; the Chinese source
columns are left alone. Run once; it is idempotent (no unit words remain after).
"""
import re, sys, glob, os
sys.stdout.reconfigure(encoding='utf-8')

EXP = {'Wan': 4, 'Yi': 8, 'Zhao': 12, 'Jing': 16, 'Gai': 20,
       'Zi': 24, 'Rang': 28, 'Gou': 32, 'Jian': 36}

# number + unit, plus an optional redundant annotation we wrote alongside it,
# e.g. "10 Jing (10^17)" or "54 Zhao (5.4e13)"
PAT = re.compile(
    r'(\d[\d,]*(?:\.\d+)?)\s*(' + '|'.join(EXP) + r')\b'
    r'(\s*\((?:10\^\d+|[\d.]+e\d+)\))?'
)

def sci(mantissa, unit_exp):
    v = float(mantissa.replace(',', ''))
    if v == 0:
        return '0'
    e = unit_exp
    # normalise to a single leading digit
    while v >= 10:
        v /= 10.0
        e += 1
    while v < 1:
        v *= 10.0
        e -= 1
    v = round(v, 3)
    if v >= 10:                      # rounding can tip 9.9996 -> 10
        v /= 10.0
        e += 1
    s = ('%g' % v)
    return '%se%d' % (s, e)

def convert(text):
    return PAT.sub(lambda m: sci(m.group(1), EXP[m.group(2)]), text)

total = 0
for path in sorted(glob.glob('prose/done_*.tsv') + glob.glob('prose/items_desc.tsv')):
    lines = open(path, encoding='utf-8').read().split('\n')
    out, changed = [], 0
    for line in lines:
        if line.startswith('#') or not line.strip():
            out.append(line)
            continue
        cols = line.split('\t')
        new_en = convert(cols[-1])          # English is always the last column
        if new_en != cols[-1]:
            changed += 1
            cols[-1] = new_en
        out.append('\t'.join(cols))
    if changed:
        open(path, 'w', encoding='utf-8').write('\n'.join(out))
        print('  %-24s %d line(s)' % (os.path.basename(path), changed))
        total += changed

print('\n%d lines rewritten' % total)
print('\nsanity check:')
for a, b in [('9999', 'Zhao'), ('4.489', 'Gai'), ('167.24', 'Jing'),
             ('64', 'Zi'), ('1', 'Zhao'), ('1000', 'Zhao')]:
    print('   %s %s -> %s' % (a, b, sci(a, EXP[b])))
