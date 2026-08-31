# -*- coding: utf-8 -*-
"""Definitive coverage check: take every CJK string literal in the game source,
push it through the same pipeline the userscript uses, and report whatever still
has Chinese left in it.

This is what catches gaps the original terminology/prose split missed - short
strings with no sentence punctuation were filed as "terminology" and only mined
for a few categories, so things like activity names were never translated.
"""
import re, sys, os, glob, collections
sys.stdout.reconfigure(encoding='utf-8')

S = open('../Script.txt', encoding='utf-8').read()

def grab(name):
    body = S.split("const %s = Object.assign(Object.create(null), {" % name)[1]
    body = body.split("\n    });")[0]
    out = {}
    for line in body.split('\n'):
        m = re.match(r"^\s+'(.*)': '(.*)',$", line)
        if m:
            out[m.group(1).replace("\\'", "'")] = m.group(2).replace("\\'", "'")
    return out

exact, frag = grab('proseExact'), grab('proseFrag')

# itemNames + every buttons pair also translate text at runtime
extra = {}
blk = S.split('const itemNames = {')[1].split('\n    };')[0]
for m in re.finditer(r"^\s+'(.+?)': '(.*?)',$", blk, re.M):
    extra[m.group(1).replace("\\'", "'")] = m.group(2)
# pairs may sit on their own line OR inline, e.g.
#   '#inventory_sort_by_price': [['价值排序', 'Sort by Price']],
#
# ORDER MATTERS. applySelector applies EVERY matching pair to a node, walking the
# list top to bottom, so an earlier short pair can destroy a later long one
# (#skill_list's ['经验获取','XP Gain'] vs the full sentence further down). The
# previous version of this audit treated these as an unordered dict of exact
# keys, which is exactly why it reported ~98% coverage while tooltips were
# visibly broken in game. Keep them in file order and replay them destructively.
V4_PAIRS = []
for m in re.finditer(r"\['((?:[^'\\]|\\.)+?)',\s*'((?:[^'\\]|\\.)*?)'\]", S):
    zh = m.group(1).replace("\\'", "'")
    en = m.group(2).replace("\\'", "'")
    extra[zh] = en
    V4_PAIRS.append((zh, en))

rx_block = S.split('const proseRegex = [')[1].split('\n    ].map(')[0]
RX = []
for line in rx_block.split('\n'):
    m = re.match(r"^\s+\['(.*)', '(.*)', '(.*)'\],$", line)
    if m:
        pat, rep, hint = (g.replace("\\'", "'").replace('\\\\', '\\') for g in m.groups())
        try:
            # Keep the REPLACEMENT. It used to be parsed and thrown away, so
            # this audit could only ask "does a rule match?" - see chunk_covered.
            # JS writes $1, Python wants \1.
            py_rep = re.sub(r'\$(\d)', r'\\\1', rep.replace('\\', '\\\\'))
            RX.append((re.compile(pat), py_rep, hint))
        except re.error:
            pass

ALL_SUB = dict(frag); ALL_SUB.update(extra)
KEYS = sorted(ALL_SUB, key=len, reverse=True)
SUB_RE = re.compile('|'.join(re.escape(k) for k in KEYS)) if KEYS else None
CJK = re.compile(r'[一-鿿]')

TAG = re.compile(r'<[^>]*>')

def chunk_covered(s):
    s = s.strip()
    if not s or not CJK.search(s):
        return True
    if s in exact or s in extra:
        return True
    # the game glues separators onto some descriptions
    core = re.sub(r'^[：:、，,。．\-\s]+', '', s)
    if core in exact or core in extra:
        return True
    # A regex MATCHING is not proof of translation - it has to actually remove
    # the Chinese. '^(.+?)！$' -> '$1!' matched every string ending in ！ and
    # only swapped the punctuation, yet this loop reported all 286 of them as
    # covered while the game rendered them in Chinese. Apply the rule and judge
    # the RESULT, then fall through to the fragment stage carrying the rewritten
    # text - which is what applyProse does (stage 2 substitutes and breaks,
    # stage 3 then runs on the substituted text).
    for pat, rep, hint in RX:
        if hint in s and pat.search(s):
            s2 = pat.sub(rep, s, count=1)
            if s2 != s:
                s = s2
                break
    if not CJK.search(s):
        return True

    # Whether a string survives depends on WHICH pass reaches it first, and that
    # varies by container (EARLY_PROSE_FULL gets our fragments before the v4.0
    # pairs; everything else gets them after). The audit can't tell which
    # container a source literal ends up in, so try both orders:
    #   ok               - works either way
    #   order-sensitive  - works only if our fragments go first, i.e. it must
    #                      live in an early container or be promoted to exact
    #   missing          - broken either way; genuinely untranslated
    def v4(t):
        # applySelector applies EVERY matching pair, in list order - which is how
        # a short pair destroys a longer one further down the same list.
        for zh, en in V4_PAIRS:
            if zh in t:
                t = t.replace(zh, en)
        return t

    def frags(t):
        return SUB_RE.sub(lambda m: ALL_SUB[m.group(0)], t) if SUB_RE else t

    frags_first = not CJK.search(frags(v4(frags(s))))
    v4_first = not CJK.search(frags(v4(s)))
    if v4_first:
        return True
    return 'order' if frags_first else False

def covered(t):
    # HTML tags split a string into separate DOM text nodes, and each is matched
    # on its own at runtime - so check per chunk, not on the whole literal.
    results = [chunk_covered(c) for c in TAG.split(t)]
    if all(r is True for r in results):
        return True
    if any(r is False for r in results):
        return False
    return 'order'          # some chunk only survives if our pass goes first

STR = re.compile(r'"((?:[^"\\]|\\.)*)"' + r"|'((?:[^'\\]|\\.)*)'" + r"|`((?:[^`\\]|\\.)*)`")
KEY = re.compile(r'([A-Za-z_][A-Za-z0-9_]*|\d+)\s*:\s*$')

missing = collections.defaultdict(list)
seen = set()
total = 0

# index.html holds static UI text (the family panel, option labels, headers) as
# element content rather than as JS string literals - a blind spot in the first
# version of this audit. Pull the CJK-bearing text runs out of the markup.
HTML_TEXT = re.compile(r'>([^<>]*[一-鿿][^<>]*)<')
for path in ['../NekoRPG/index.html']:
    if not os.path.exists(path):
        continue
    html = open(path, encoding='utf-8').read()
    for m in HTML_TEXT.finditer(html):
        t = m.group(1).strip()
        if not t or t in seen or len(t) > 400:
            continue
        seen.add(t)
        total += 1
        if not covered(t):
            line = html[:m.start()].count('\n') + 1
            missing['index.html'].append((line, 'html', t))

for path in sorted(glob.glob('../NekoRPG/src/*.js')):
    fn = os.path.basename(path)
    for i, line in enumerate(open(path, encoding='utf-8'), 1):
        if line.lstrip().startswith('//'):
            continue
        for m in STR.finditer(line):
            t = next(g for g in m.groups() if g is not None)
            if not t or not CJK.search(t) or len(t) > 400 or t in seen:
                continue
            seen.add(t)
            total += 1
            res = covered(t)
            if res is not True:
                key = KEY.search(line[:m.start()].rstrip())
                tag = 'ORDER' if res == 'order' else (key.group(1) if key else '?')
                missing[fn].append((i, tag, t))

n = sum(len(v) for v in missing.values())
n_ord = sum(1 for v in missing.values() for r in v if r[1] == 'ORDER')
print('unique CJK literals in source : %d' % total)
print('NOT fully covered             : %d' % n)
print('   genuinely missing          : %d  (no translation survives either order)' % (n - n_ord))
print('   order-sensitive            : %d  (fine while our pass runs first -' % n_ord)
print('                                    i.e. an EARLY_PROSE container)\n')
# Most of what is left is deliberately untranslated, or is covered by a route
# this audit cannot see. Classify it here so the headline number stops looking
# like a backlog - the only line that ever needs action is "UNEXPLAINED".
UNITS = set('万亿兆京垓秭穣沟涧正载极')
REALM = set('微潮大天云领世初中高巅一二三四五六七八九十')

def why_ok(fn, ln, s):
    s = s.strip()
    if s in UNITS or s == '/亿':
        return 'myriad units - formatMyriad handles them attached to digits'
    if s in REALM:
        return 'realm chars - switch() LOOKUP KEYS in main.js, never displayed'
    if fn == 'index.html' and 555 <= ln <= 559:
        return 'fish banner - one glyph per node, swapped wholesale by translateFishFont'
    if fn == 'game_time.js' or s in ('个', '年'):
        return 'assembled inline; the rendered line is owned by a regex/fragment'
    if 'name_prefix' in s:
        return 'weapon template - built combinatorially from materials x types'
    if s.startswith('你的 ${mapp'):
        # Cannot be judged as a literal - the slot name is only known at runtime.
        # All 13 rendered forms verified: the 10 original slots resolve via the
        # v4.0 >=8-char promotion into proseExact, the 3 tool slots via the exact
        # entries in glossary 11. The tooltip pass is exact-only, so the
        # 你的 X 槽位 regex cannot fire there and half-translate one.
        return 'slot tooltip template - all 13 rendered forms verified covered'
    return None

expl = collections.Counter()
unexplained = []
for fn, rows in missing.items():
    for ln, tag, t in rows:
        if tag == 'ORDER':
            continue
        r = why_ok(fn, ln, t)
        if r:
            expl[r] += 1
        else:
            unexplained.append((fn, ln, t))
print('--- of the genuinely-missing, accounted for ---')
for k, v in expl.most_common():
    print('   %2d  %s' % (v, k))
print('   %2d  UNEXPLAINED%s' % (len(unexplained), ' <-- ACTION NEEDED' if unexplained else ''))
for fn, ln, t in unexplained:
    print('        %s:%s  %s' % (fn, ln, t[:70]))
print()
for fn, rows in sorted(missing.items(), key=lambda kv: -len(kv[1])):
    print('%-22s %d' % (fn, len(rows)))
print('\n--- by field name ---')
c = collections.Counter(k for rows in missing.values() for _, k, _ in rows)
for k, v in c.most_common(12):
    print('   %-18s %d' % (k, v))
with open('_uncovered.tsv', 'w', encoding='utf-8') as f:
    for fn, rows in sorted(missing.items()):
        for ln, k, t in rows:
            f.write('%s\t%d\t%s\t%s\n' % (fn, ln, k, t))
print('\nwrote _uncovered.tsv')
