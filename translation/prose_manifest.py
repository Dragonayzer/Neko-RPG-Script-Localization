# -*- coding: utf-8 -*-
# Build a resumable prose inventory: all remaining CJK prose per source file,
# excluding anything already translated (Script.txt + glossary/*.tsv + prose/*.tsv).
import re, sys, os, glob
sys.stdout.reconfigure(encoding='utf-8')

def cjk(s): return any('一' <= c <= '鿿' for c in s)

# ---- collect DONE zh strings (already translated somewhere) ----
done = set()
# Script.txt: dict keys ('zh': 'en',) and pair-list ['zh','en']
for l in open('../Script.txt', encoding='utf-8'):
    for lr in (re.compile(r"^\s*'(.+?)':\s*'(.*?)',\s*$"),
               re.compile(r"^\s*\['(.+?)',\s*'(.*?)'\],?\s*$")):
        m = lr.match(l)
        if m and cjk(m.group(1)): done.add(m.group(1))
# glossary + prose tsv files: add EVERY CJK cell (prose files have the zh
# description in col1, name in col0; glossary in col0) so nothing already
# translated gets re-listed.
done_files = glob.glob('glossary/*.tsv') + glob.glob('prose/*.tsv')
done_files = [p for p in done_files if not os.path.basename(p).startswith('_')]
for p in done_files:
    for l in open(p, encoding='utf-8'):
        if l.startswith('#') or not l.strip(): continue
        for cell in l.rstrip('\n').split('\t'):
            if cjk(cell): done.add(cell)

STR = re.compile(r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|`((?:[^`\\]|\\.)*)`')
KEY = re.compile(r'([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:\s*$')

FILES = ['dialogues.js','enemies.js','items.js','locations.js','skills.js',
         'display.js','main.js','character.js','combat_stances.js','traders.js',
         'active_effects.js','activities.js','crafting_recipes.js','misc.js']

def is_prose(key, s):
    if key == 'description': return True
    if len(s) > 12: return True
    if any(p in s for p in '。，！？；'): return True
    return False

seen = set()
manifest = []  # (file, static/dynamic, id, string)
for fn in FILES:
    path = '../NekoRPG/src/' + fn
    if not os.path.exists(path): continue
    rows = []
    for i, line in enumerate(open(path, encoding='utf-8'), 1):
        for m in STR.finditer(line):
            s = next(g for g in m.groups() if g is not None)
            if not s or not cjk(s): continue
            before = line[:m.start()].rstrip()
            km = KEY.search(before)
            key = km.group(1) if km else '?'
            if not is_prose(key, s): continue
            if s in done or s in seen: continue
            seen.add(s)
            kind = 'dyn' if ('${' in s or '<' in s) else 'stat'
            rows.append((kind, i, s))
    if rows:
        manifest.append((fn, rows))

# write per-file source dumps (only TODO), + a summary manifest
os.makedirs('prose', exist_ok=True)
total_stat = total_dyn = 0
summary = []
for fn, rows in manifest:
    base = fn.replace('.js','')
    stat = [r for r in rows if r[0]=='stat']
    dyn  = [r for r in rows if r[0]=='dyn']
    sc = sum(len(r[2]) for r in stat); dc = sum(len(r[2]) for r in dyn)
    total_stat += len(stat); total_dyn += len(dyn)
    with open('prose/_todo_%s.tsv' % base, 'w', encoding='utf-8') as f:
        for kind, ln, s in rows:
            f.write('%s\t%d\t%s\n' % (kind, ln, s))
    summary.append((fn, len(stat), sc, len(dyn), dc))

print('Remaining prose (excluding all already-translated):')
print('%-22s %6s %8s %6s %8s' % ('file','#stat','statCh','#dyn','dynCh'))
for fn, ns, sc, nd, dc in summary:
    print('%-22s %6d %8d %6d %8d' % (fn, ns, sc, nd, dc))
print('%-22s %6d %8s %6d' % ('TOTAL', total_stat, '', total_dyn))
