# -*- coding: utf-8 -*-
import re, sys
sys.stdout.reconfigure(encoding='utf-8')
def cjk(s): return any('一' <= c <= '鿿' for c in s)
src = open('../NekoRPG/src/items.js', encoding='utf-8').read()
pat = re.compile(r'name:\s*"([^"]+)"\s*,\s*\n\s*description:\s*"((?:[^"\\]|\\.)*)"')
items = []
for m in pat.finditer(src):
    nm, de = m.group(1), m.group(2)
    if cjk(de): items.append((nm, de))
seen = set(); uniq = []
for nm, de in items:
    if de not in seen: seen.add(de); uniq.append((nm, de))
tot = sum(len(de) for _, de in uniq)
lens = sorted(len(de) for _, de in uniq)
print("unique item descriptions:", len(uniq))
print("total chars:", tot)
print("median len:", lens[len(lens)//2], "| min", lens[0], "| max", lens[-1])
print("share of 2286 prose: %.0f%%" % (len(uniq)/2286*100))
with open('prose/_items_desc_src.tsv', 'w', encoding='utf-8') as f:
    for nm, de in uniq: f.write(nm + '\t' + de + '\n')
print("wrote prose/_items_desc_src.tsv")
for nm, de in uniq[:5]: print("  [%s] %s" % (nm, de[:80]))
