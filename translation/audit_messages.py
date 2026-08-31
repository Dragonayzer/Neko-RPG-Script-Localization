# -*- coding: utf-8 -*-
"""Sweep names as they appear INSIDE message templates.

Why this exists as a separate audit:

audit_skills.py checks each skill name on its own, and an EXACT-only entry
passes that test - `合成` alone resolves to "Crafting" just fine. But the
message log renders `${this.name()} 达到了 level ${n}`, which our layer matches
with a whole-node REGEX. A regex inserts the captured group verbatim, so the
name has to be resolvable as a FRAGMENT (or via v4.0 itemNames) or it survives
untranslated inside otherwise-perfect English:

    合成 reached level 12          <- reported by a player
    战斗 reached level 18          <- reported again, same cause

The bare-name audit reported "0 unresolved" through both of those. The
distinguishing property is not "is this name translated" but "is this name
translated when it is EMBEDDED IN A SENTENCE", so that is what this checks:
every name is rendered into the real templates and run through the pipeline.
"""
import re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')

import verify_screenshot as v

CJK = re.compile(r'[一-鿿]')

skills_src = open('../NekoRPG/src/skills.js', encoding='utf-8').read()

names = collections.OrderedDict()
names['skill names'] = [m for nd in re.findall(r'names:\s*\{([^}]*)\}', skills_src)
                        for m in re.findall(r'\d+\s*:\s*"([^"]+)"', nd)]

# Dialogue names go through the same shredder: "你应该与 ${dialogue} 对话" and
# "[和与] ${name} 对话" are whole-node regexes, so the captured name is inserted
# verbatim and an EXACT-only name survives in Chinese. Nothing checked these
# until a player reported "You should talk to 峰" (v9.8). 峰 has to STAY
# exact-only - as a fragment it wrecks 巅峰 (Peak) and 峰大哥 - so it is handled
# by exact entries for the rendered forms, which this sweep verifies.
dlg_src = open('../NekoRPG/src/dialogues.js', encoding='utf-8').read()
names['dialogue names'] = sorted({
    m.group(1) for m in re.finditer(r'dialogues\[\s*"([^"]+)"\s*\]\s*=', dlg_src)})

# The templates that interpolate a name into running text. Kept literal (rather
# than scraped) because each needs a plausible value for its OTHER slots, and
# because a template that stops appearing in the game should fail loudly here
# rather than silently dropping out of the sweep.
#
# Scoped PER GROUP on purpose. Cross-producing every name with every template
# manufactures failures: 峰 is a character, never a skill, so "峰 达到了 level 12"
# is a string the game cannot emit - and an audit that cries about impossible
# input is one nobody reads.
TEMPLATES = {
    'skill names': [
        '{} 达到了 level 12',      # skill level-up (message_skill_leveled_up)
        'x2 {} 经验获取',           # xp multiplier readout
        '解锁新技能: {}',           # skill unlock
    ],
    'dialogue names': [
        '与 {} 对话',              # dialogue trigger
        '和 {} 对话',              # same, other particle
        '你应该与 {} 对话',         # "you should talk to X" reminder
    ],
}

total = bad = 0
for group, items in names.items():
    seen, misses = set(), []
    for nm in items:
        nm = nm.strip()
        if not nm or not CJK.search(nm) or nm in seen:
            continue
        seen.add(nm)
        for tpl in TEMPLATES[group]:
            total += 1
            out = v.apply_prose(tpl.format(nm))[0]
            # Only the NAME matters here; the carrier text is audited elsewhere.
            if CJK.search(out) and nm in out:
                misses.append((nm, tpl, out))
                break
    bad += len(misses)
    print('%-14s %3d names checked, %d unresolved when embedded'
          % (group, len(seen), len(misses)))
    for nm, tpl, out in misses:
        print('      %-14s in %-18s -> %s' % (nm, tpl.format('_'), out[:52]))

print('\n%d renderings checked, %d names unresolved when embedded' % (total, bad))
