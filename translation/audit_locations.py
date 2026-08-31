# -*- coding: utf-8 -*-
"""Focused sweep of everything the location panel can display: location names,
trader names, travel/action button text, and dialogue entry points.

Pulls each from source and pushes it through the same pipeline the userscript
uses, so the whole location surface is checked at once instead of one report at
a time.
"""
import re, sys, collections
sys.stdout.reconfigure(encoding='utf-8')

import verify_screenshot as v          # reuses the exact/regex/frag simulation

CJK = re.compile(r'[一-鿿]')

def read(p):
    return open('../NekoRPG/src/' + p, encoding='utf-8').read()

loc = read('locations.js')
tra = read('traders.js')
dia = read('dialogues.js')

groups = collections.OrderedDict()
groups['location names'] = re.findall(r'locations\["([^"]+)"\]\s*=\s*new', loc)
groups['trader names'] = (re.findall(r'traders\["([^"]+)"\]', tra)
                          + re.findall(r'traders:\s*\["([^"]+)"\]', loc)
                          + re.findall(r'\{traders:\s*"([^"]+)"\}', loc))
groups['travel text'] = re.findall(r'custom_text:\s*"([^"]+)"', loc)
groups['activity text'] = (re.findall(r'starting_text:\s*"([^"]+)"', loc)
                           + re.findall(r'action_text:\s*"([^"]+)"', loc)
                           + re.findall(r'leave_text:\s*"([^"]+)"', loc))
groups['dialogue entries'] = re.findall(r'dialogues:\s*\[([^\]]*)\]', loc)
groups['dialogue names'] = re.findall(r'dialogues\["([^"]+)"\]', dia)

# Only mirror wrapping the game actually does. traders.js really builds
# `与 ${name} 交易`, so a trader name must survive inside that sentence.
# Dialogue buttons do NOT work that way - display.js renders
# dialogues[x].starting_text, which is already covered under 'activity text' -
# so synthesising 和 X 对话 here just invented failures that cannot occur.
WRAPPERS = {
    'trader names': lambda s: '与 %s 交易' % s,
}

total = bad = 0
for name, items in groups.items():
    seen, misses = set(), []
    for raw in items:
        for s in re.split(r'"\s*,\s*"', raw.strip().strip('"')):
            s = s.strip()
            if not s or not CJK.search(s) or s in seen:
                continue
            seen.add(s)
            total += 1
            out = v.apply_prose(s)[0]
            if CJK.search(out):
                misses.append((s, out))
                continue
            wrap = WRAPPERS.get(name)
            if wrap:                      # also check the rendered form
                out2 = v.apply_prose(wrap(s))[0]
                if CJK.search(out2):
                    misses.append((wrap(s), out2))
    bad += len(misses)
    print('%-18s %3d checked, %d unresolved' % (name, len(seen), len(misses)))
    for s, out in misses:
        print('      %-34s -> %s' % (s[:32], out[:60]))
print('\n%d checked, %d unresolved' % (total, bad))
