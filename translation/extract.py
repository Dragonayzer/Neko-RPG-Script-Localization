# -*- coding: utf-8 -*-
"""
Extract every CJK-containing string literal from the NekoRPG game source,
tagged with its file, line, and the JS key it sits under (name/description/etc).
Splits into TERMINOLOGY (short, translate directly for glossary consistency)
vs PROSE (long, batch out to DeepSeek).
"""
import re, os, json, collections

SRC = os.path.join(os.path.dirname(__file__), '..', 'NekoRPG', 'src')
OUT = os.path.dirname(__file__)

FILES = ['items.js','enemies.js','skills.js','locations.js',
         'combat_stances.js','crafting_recipes.js','activities.js',
         'active_effects.js','traders.js','dialogues.js','character.js',
         'display.js','trade.js','misc.js','main.js']

def has_cjk(s):
    return any('一' <= c <= '鿿' or '㐀' <= c <= '䶿'
               or c in '·【】' for c in s if '一' <= c <= '鿿' or '㐀' <= c <= '鿿') \
           or any('一' <= c <= '鿿' for c in s)

# match "double" or 'single' or `template` quoted string literals
STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"' r"|'((?:[^'\\]|\\.)*)'" r"|`((?:[^`\\]|\\.)*)`")
# nearest identifier key before the string on the same line, e.g.  name:  description:  15:
KEY_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:\s*$')

rows = []  # (file, line, key, string)
seen = set()
for fn in FILES:
    path = os.path.join(SRC, fn)
    if not os.path.exists(path):
        continue
    for i, line in enumerate(open(path, encoding='utf-8'), 1):
        for m in STR_RE.finditer(line):
            s = next(g for g in m.groups() if g is not None)
            if not s or not any('一' <= c <= '鿿' for c in s):
                continue
            # find the key preceding this literal on the same line
            before = line[:m.start()].rstrip()
            km = KEY_RE.search(before)
            key = km.group(1) if km else '?'
            dedup = (fn, key, s)
            if dedup in seen:
                continue
            seen.add(dedup)
            rows.append((fn, i, key, s))

# ---- Global dedupe BY STRING (references collapse into their definition) ----
# Keep the most informative context for each unique string: a definition
# site (name/description/names) outranks a bare reference (item_name/id/?).
KEY_RANK = {'name':0,'names':0,'description':0,'text':1,'custom_text':1,
            'unlock_text':1,'starting_text':1,'dialogue':1,'effect':1}
def rank(key): return KEY_RANK.get(key, 5)

best = {}   # string -> (file, line, key)
for fn, ln, key, s in rows:
    if s not in best or rank(key) < rank(best[s][2]):
        best[s] = (fn, ln, key)

uniq = [(fn, ln, key, s) for s, (fn, ln, key) in best.items()]

# Categorize each unique string
PROSE_KEYS = {'description'}
def is_prose(key, s):
    if key in PROSE_KEYS:
        return True
    if len(s) > 12 or any(p in s for p in '。，,！!？?；;'):
        return True
    return False

term  = sorted([r for r in uniq if not is_prose(r[2], r[3])], key=lambda r:(r[0],r[1]))
prose = sorted([r for r in uniq if     is_prose(r[2], r[3])], key=lambda r:(r[0],r[1]))

def dump(fname, data):
    with open(os.path.join(OUT, fname), 'w', encoding='utf-8') as f:
        for fn, ln, key, s in data:
            f.write(f"{fn}\t{ln}\t{key}\t{s}\n")

dump('_terminology_raw.tsv', term)
dump('_prose_raw.tsv', prose)

print(f"Raw CJK string occurrences : {len(rows)}")
print(f"UNIQUE CJK strings          : {len(uniq)}")
print(f"  Terminology (glossary)    : {len(term)}")
print(f"  Prose (DeepSeek)          : {len(prose)}")
print()
# Where each unique string is DEFINED
byfile = collections.Counter(r[0] for r in uniq)
print("Unique strings by defining file:")
for fn, c in byfile.most_common():
    t = sum(1 for r in term if r[0]==fn)
    p = sum(1 for r in prose if r[0]==fn)
    print(f"  {fn:22} {c:5}   term={t:4}  prose={p:4}")
