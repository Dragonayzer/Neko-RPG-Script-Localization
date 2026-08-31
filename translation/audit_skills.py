# -*- coding: utf-8 -*-
"""Sweep everything the skills panel can display.

#skill_list is special: it gets the EARLY pass in exact-only mode (no fragments,
no regexes), then v4.0's own pair list runs, then our fragments get whatever is
left. So a phrase of ours that is only a FRAGMENT is useless here - v4.0's short
pairs (经验获取 -> "XP Gain", 技能 -> ...) will have chewed the sentence up first.
This reproduces that exact order so those cases show up.
"""
import re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')

import verify_screenshot as v

CJK = re.compile(r'[一-鿿]')
S = open('../Script.txt', encoding='utf-8').read()

# v4.0 #skill_list pairs, in list order (order is what does the damage).
#
# The list SPREADS shared arrays into itself (`...statPairs,`), and statPairs
# holds ['攻击','Attack'] / ['防御','Defense'] / ['敏捷','Agility']. Reading only
# the literal [zh,en] rows made those invisible, so this audit reported
# "0 unresolved" while the skill tooltip showed
#     基础Attack,Defense,Agility + 8000
# - the short stat pairs fire before our per-panel pass and destroy the
# whole-node regex. Resolve the spreads, in place, in order.
PAIR_RE = re.compile(r"\['((?:[^'\\]|\\.)+?)',\s*'((?:[^'\\]|\\.)*?)'\]")

def _pairs_of(text):
    return [(m.group(1).replace("\\'", "'"), m.group(2).replace("\\'", "'"))
            for m in PAIR_RE.finditer(text)]

SHARED = {}
for _name in re.findall(r'const (\w+Pairs) = \[', S):
    _blk = S.split('const %s = [' % _name)[1].split('\n    ];')[0]
    SHARED[_name] = _pairs_of(_blk)

blk = S.split("'#skill_list': [")[1].split('\n        ],')[0]
SKILL_PAIRS = []
for _line in blk.split('\n'):
    _sp = re.match(r'\s*\.\.\.(\w+),', _line)
    if _sp:
        SKILL_PAIRS.extend(SHARED.get(_sp.group(1), []))
    else:
        SKILL_PAIRS.extend(_pairs_of(_line))

TAG = re.compile(r'<[^>]*>')

def pipeline(s):
    """HTML tags split a string into separate DOM text nodes, each matched on its
    own - so check per chunk, exactly as the runtime does."""
    return ' '.join(_chunk(c) for c in TAG.split(s) if c.strip())

def _chunk(s):
    """early exact + COMPLETE regexes -> v4.0 #skill_list pairs -> fragments"""
    t = s.strip()
    if t in v.exact:
        return v.exact[t]
    core = re.sub(r'^["“”\'：:、，,．\-\s]+', '', t).rstrip('"”\' ')
    if core in v.exact:
        return v.exact[core]
    # The early pass also runs whole-node regexes, but takes one ONLY if it
    # FULLY resolves the node (regexMustComplete). That is what lets the
    # milestone line beat #skill_list's statPairs, while still refusing
    # "X technique-category" rules that would leave an untranslated $1 and
    # block the v4.0 pair able to render the whole phrase.
    for pat, rep, hint in v.RX:
        if hint in t and pat.search(t):
            py_rep = re.sub(r'\$(\d)', r'\\\1', rep.replace('\\', '\\\\'))
            nxt = pat.sub(py_rep, t, count=1)
            # myriad units are pending work for formatMyriad, not untranslated
            # Chinese - mirrors residualChinese() in applyProse. Without this the
            # model accepts "+ 8000" and rejects "+ 972万", which is exactly how
            # the v9.1 fix looked correct while failing on every large value.
            if nxt != t and not CJK.search(v.MYRIAD_RE.sub(r'', nxt)):
                return nxt
    for zh, en in SKILL_PAIRS:
        if zh in t:
            t = t.replace(zh, en)
    return v.apply_prose(t)[0]

src = open('../NekoRPG/src/skills.js', encoding='utf-8').read()
# all three quote styles: reading only "..." is how 增加基础经验获取量 slipped past
# this audit while being visibly broken in game.
STR = re.compile(r'"((?:[^"\\]|\\.)*)"' + r"|'((?:[^'\\]|\\.)*)'" + r'|`((?:[^`\\]|\\.)*)`')

groups = collections.OrderedDict()
groups['skill names'] = [m for nd in re.findall(r'names:\s*\{([^}]*)\}', src)
                         for m in re.findall(r'\d+\s*:\s*"([^"]+)"', nd)]
groups['descriptions'] = re.findall(r'description:\s*"([^"]+)"', src)

# Milestone / effect text: the `return `...`` templates. These render into the
# skill tooltip and were NOT audited by anything - audit_skills skipped them as
# "template literals", audit_coverage judges the raw literal rather than the
# rendered node. That gap is how a player found
#     基础Attack,Defense,Agility + 8000
# still sitting in a tooltip. Rendered here with a value substituted for each
# ${...}, which is the string the player actually sees.
RENDER = re.compile(r'\$\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}')
groups['milestone text'] = [RENDER.sub('42', m.group(1))
                            for m in re.finditer(r'return\s+`([^`]*)`', src)]

# skills.js carries its own copy of the myriad-unit array; those single
# characters are never rendered on their own (formatMyriad handles them attached
# to digits) and are deliberately not translated - see 09_dialogue_terms header.
UNITS = set('万亿兆京垓秭穣沟涧正载极')
# Only skip slices that are plainly cut out of the middle of an expression -
# a leading "]." or "}" means the regex sheared a template literal. Strings that
# merely CONTAIN ${...} are real display text and must still be checked.
CODEY = re.compile(r'^\s*[\]\}]')

# DELIBERATELY NOT AUDITED HERE: skills.js effect text.
#
# It is built from template literals (`...${expr}...`), and neither extraction
# strategy gives a trustworthy answer. Matching whole JS literals either shears
# the template (yielding raw code like "base_xp_cost: 100,") or swallows it
# whole; matching bare Chinese runs is too granular, because those runs are
# pieces of strings that the runtime resolves with a WHOLE-NODE regex - so they
# report as broken when they are fine. Both produced long lists of false alarms.
#
# audit_coverage.py already covers this text correctly: it is chunk-aware and
# regex-aware. What THIS script adds is the #skill_list ordering simulation,
# which matters for names and descriptions - so it audits only those, rather
# than emitting noise about the rest.
#
# One real gap did hide behind the old extraction (增加基础经验获取量, fixed by
# promoting it to an exact entry); if effect text needs auditing again, do it in
# audit_coverage.py where the chunk/regex handling already exists.

total = bad = 0
for name, items in groups.items():
    seen, misses = set(), []
    for s in items:
        s = s.strip()
        if not s or not CJK.search(s) or s in seen:
            continue
        seen.add(s)
        total += 1
        out = pipeline(s)
        if CJK.search(out):
            misses.append((s, out))
    bad += len(misses)
    print('%-14s %3d checked, %d unresolved' % (name, len(seen), len(misses)))
    for s, out in misses:
        print('      %-30s -> %s' % (s[:28], out[:64]))
print('\n%d checked, %d unresolved' % (total, bad))
