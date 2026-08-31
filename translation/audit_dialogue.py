# -*- coding: utf-8 -*-
"""Every dialogue text/name in dialogues.js, chunked as the DOM splits it.

audit_locations.py checks the 49 dialogue NAMES; nothing checked the ~1400
text chunks players actually read, which is how "获取了 … 经验！" survived inside a
multi-award XP line (v10.4).

dialogue_answer_div holds the whole answer with <br> separators, so each run
between tags is one text node. Anything still Chinese after the pipeline is
what a player sees mid-conversation.
"""
import os, re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')

TR = r'D:\Work\!Ai\neko-rpg-translation\translation'
os.chdir(TR); sys.path.insert(0, TR)
import verify_screenshot as v

CJK = re.compile(r'[\u4e00-\u9fff]')
TAG = re.compile(r'<[^>]*>')
SLOT = re.compile(r'\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')
src = open('../NekoRPG/src/dialogues.js', encoding='utf-8').read()

fields = collections.OrderedDict([
    ('name', r'name:\s*"((?:[^"\\]|\\.)*)"'),
    ('text', r'text:\s*"((?:[^"\\]|\\.)*)"'),
])

seen, bad = set(), []
counts = collections.Counter()
for label, pat in fields.items():
    for m in re.finditer(pat, src):
        raw = m.group(1).replace('\\"', '"')
        if not CJK.search(raw):
            continue
        for chunk in TAG.split(SLOT.sub('42', raw)):
            c = ' '.join(chunk.split())
            if not c or not CJK.search(c) or c in seen:
                continue
            seen.add(c)
            counts[label] += 1
            out = v.apply_prose(c)[0]
            if CJK.search(out):
                bad.append((label, c, out))

print('dialogue chunks checked: %d  (%s)'
      % (len(seen), ', '.join('%s %d' % kv for kv in counts.items())))
print('unresolved: %d' % len(bad))
for label, c, out in bad[:25]:
    print('   [%s] %-40s -> %s' % (label, c[:38], out[:44]))

# ---------------------------------------------------------------------------
# MERGED TAILS. Testing chunks in isolation is not enough: a textline carrying
# a spec unlock whose text does NOT end in <br> has main.js's reward text
# appended straight onto its LAST chunk, so the two share one text node and the
# whole-node exact entry for that chunk can never match. Checking chunks alone
# reported 0 unresolved while a player was looking at Chinese (v11.1).
APPEND = '\u3010\u7130\u6d77\u971c\u5929[\u9886\u57df\u4e09\u91cd]\u3011\u83b7\u53d6\u4e8664\u79ed\u7ecf\u9a8c\uff01'

tails, tail_bad = 0, []
for b in re.findall(r'new Textline\(\{(.*?)\}\s*\)', src, re.S):
    m = re.search(r'text:\s*"((?:[^"\\]|\\.)*)"', b)
    if not m or 'spec:' not in b:
        continue
    text = m.group(1)
    if not CJK.search(text) or re.search(r'<br\s*/?>\s*$', text, re.I):
        continue                      # a trailing <br> opens a fresh node
    last = TAG.split(text)[-1].strip()
    if not last or not CJK.search(last):
        continue
    tails += 1
    head = v.apply_prose(last + APPEND)[0].split('\u3010Flame')[0]
    if CJK.search(head):
        tail_bad.append((last, head))

print('\nmerge-exposed tails checked: %d, unresolved: %d' % (tails, len(tail_bad)))
for last, head in tail_bad:
    print('   %-40s -> %s' % (last[:38], head[:44]))
