# -*- coding: utf-8 -*-
"""Hunt the characteristic defect of this project: EXACT-only names.

A name that resolves on its own but NOT inside a longer node is a latent bug.
The moment the game splices it into a message, tooltip or template, it survives
in Chinese surrounded by perfect English - which is exactly how 合成/战斗
(v8.0/8.2), 领域 (v9.4), 峰 (v9.8), the 13 crafting categories (v9.9) and the
XP-multiplier readout (v10.0) reached players.

Cause is always the same: glossaries 00-04 and 11 are not in FORCED_FRAG_FILES,
so their entries can only match a WHOLE text node.

Discriminator: wrap the name in ASCII (which matches nothing itself). Bare form
resolves + wrapped form does not  =>  exact-only.

Everything still listed below is a DELIBERATE exception with a stated reason.
A new name appearing here is a real finding.
"""
import os, re, sys, glob, collections
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_screenshot as v

CJK = re.compile(r'[一-鿿]')
SRC = os.path.join('..', 'NekoRPG', 'src')

# Names that MUST stay exact-only, and how they are covered instead.
ALLOWED = {
    '峰': 'the character Feng; as a fragment it wrecks 巅峰 (Peak) and 峰大哥. '
          'Covered by exact entries for the rendered forms (glossary 11).',
}
# Whole groups whose only interpolation site is already scoped.
ALLOWED_GROUPS = {
    'ComponentNameMap': 'only used as `选择一个[${…}]` (2 call sites), and all 13 '
                        'names have bracket-scoped fragments (glossary 07).',
    # The wrap test cannot see v4.0's scoped pair lists, so these look exact-only
    # here while rendering correctly in game. Each was verified in its real
    # container before being listed - do not add a group without doing that.
    'SkillsCategoryMap': 'skill-list headers, rendered as `${cat} 技能`; all 8 '
                         'verified via audit_skills.pipeline (Combat Skills, '
                         'Technique Skills, …) from #skill_list pairs.',
    'BreakDownMap': 'stat-breakdown rows, rendered as `<br>${k}: ${value}` inside '
                    '.stat_tooltip, whose pair list covers all 10 - and orders '
                    '技能里程碑 before 技能, so the longer one wins.',
    'EquipSlotMap': 'rendered as `类型:/槽位: <b>${v}</b>` inside .item_tooltip; the '
                    '<b> makes the value its own node and statPairs/slotPairs '
                    'there translate it.',
}
# Names deliberately not translated bare, resolved by scoped rules instead.
ALLOWED_BARE = {
    '全部': 'v4.0 button pair renders the filter tab; the XP readout is covered '
            'by the scoped 全部 经验获取 regex.',
    '技能': 'a bare fragment would break "秘法 技能" -> Technique Skills; the XP '
            'readout is covered by the scoped 技能 经验获取 regex.',
}

PATTERNS = collections.OrderedDict([
    ('items', r'item_templates\["([^"]+)"\]'),
    ('enemies', r'enemy_templates\["([^"]+)"\]'),
    ('locations', r'locations\["([^"]+)"\]'),
    ('effects', r'effect_templates\["([^"]+)"\]'),
])

groups = collections.OrderedDict((k, set()) for k in PATTERNS)
for f in glob.glob(os.path.join(SRC, '*.js')):
    s = open(f, encoding='utf-8').read()
    for k, p in PATTERNS.items():
        for m in re.finditer(p, s):
            if CJK.search(m.group(1)):
                groups[k].add(m.group(1))
    # \w*Map, not \w*NameMap: SkillsCategoryMap holds the skill-list headers and
    # was invisible to the narrower pattern.
    for m in re.finditer(r'(\w*Map)\s*=\s*\{', s):
        body = s[m.end():s.find('}', m.end())]
        vals = {x for x in re.findall(r'"([^"]+)"', body) if CJK.search(x)}
        if vals:
            groups.setdefault(m.group(1), set()).update(vals)

# Plain ARRAYS of display strings (let MM1 = ["0-23点", ...]). Not objects, so
# the *Map scan above misses them entirely - which is how the Blazing Sun
# blessing printed "The current period is 23-45点" (v10.5). Only 3 such arrays
# exist (MM1/MM2/MM3), so this stays cheap.
for f in glob.glob(os.path.join(SRC, '*.js')):
    s = open(f, encoding='utf-8').read()
    for m in re.finditer(r'(?:let|const|var)\s+(\w+)\s*=\s*\[([^\]\[]{0,600})\]', s):
        vals = {x for x in re.findall(r'"([^"]*)"', m.group(2)) if CJK.search(x)}
        if vals:
            groups.setdefault('array ' + m.group(1), set()).update(vals)

st = open(os.path.join(SRC, 'combat_stances.js'), encoding='utf-8').read()
groups['stance names'] = {m.group(1) for m in re.finditer(r'name:\s*"([^"]+)"', st)
                          if CJK.search(m.group(1))}

total = flagged = 0
print('%-18s %6s %10s %10s' % ('group', 'names', 'exact-only', 'bare-miss'))
findings = []
for k, ns in groups.items():
    exact_only, bare_miss = [], []
    for n in sorted(ns):
        total += 1
        if CJK.search(v.apply_prose(n)[0]):
            bare_miss.append(n)
        elif CJK.search(v.apply_prose('Q' + n + 'Z')[0]):
            exact_only.append(n)
    print('%-18s %6d %10d %10d' % (k, len(ns), len(exact_only), len(bare_miss)))
    for n in exact_only:
        if k not in ALLOWED_GROUPS and n not in ALLOWED:
            findings.append(('exact-only', k, n))
    for n in bare_miss:
        # ALLOWED_GROUPS applies here too: a group covered by a v4.0 scoped pair
        # list fails BOTH tests, because this tool cannot see those pairs.
        if k not in ALLOWED_GROUPS and n not in ALLOWED_BARE:
            findings.append(('untranslated', k, n))

print('\n%d names checked' % total)
if findings:
    print('%d UNEXPLAINED <-- ACTION NEEDED' % len(findings))
    for kind, k, n in findings:
        print('   %-14s %-18s %s' % (kind, k, n))
else:
    print('0 UNEXPLAINED (all remaining flags are documented exceptions)')
