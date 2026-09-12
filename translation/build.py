# -*- coding: utf-8 -*-
"""
Assemble Script.txt v5.0 from the glossaries + translated prose.

Never loads content into a human's head: joins done_*.tsv (key -> English) back
against the frozen _todo_*.tsv (key -> Chinese) to recover zh->en pairs.

Output split:
  EXACT     : whole-text-node match (plain strings)  -> O(1) dict lookup
  FRAGMENTS : substring pairs, from strings containing HTML tags or ${...}
              interpolations, which the DOM breaks into several text nodes.
"""
import re, sys, os, glob, json, shutil, collections
sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

def cjk(s): return any('\u4e00' <= c <= '\u9fff' for c in s)

# ---------------------------------------------------------------- load pairs
pairs = {}          # zh -> en
srcs  = collections.Counter()
conflicts = []

def add(zh, en, origin):
    zh = zh.strip(); en = en.strip()
    if not zh or not en or not cjk(zh):
        return
    if zh in pairs and pairs[zh] != en:
        conflicts.append((zh, pairs[zh], en, origin))
        return                      # first writer wins (glossaries load first)
    pairs[zh] = en
    srcs[origin] += 1

def rows(path):
    out = []
    for line in open(path, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        out.append(line.rstrip('\n').split('\t'))
    return out

# 1) glossaries: zh <TAB> en <TAB> [note]
#    06_combat_log.tsv is handled separately below: its entries are substrings by
#    nature ("受到了" inside a longer line), so they must not go through the
#    exact/fragment classifier, and their significant spaces must survive.
SPACE_MARK = '␣'
# Handled as substrings (see 1b). 05_ui belongs here too: entries like 饱食
# ("饱食 II") and 攻击 are labels that appear INSIDE longer runtime text, so as
# exact-match keys they could never fire.
FORCED_FRAG_FILES = ('05_', '06_', '07_', '08_', '09_', '10_')
materials = {}                       # zh -> en, for building weapon names
stats = {}                           # zh -> en, stat names (Attack, Luck, ...)
for p in sorted(glob.glob('glossary/*.tsv')):
    base = os.path.basename(p)
    if base[:3] in FORCED_FRAG_FILES:
        continue
    for r in rows(p):
        if len(r) >= 2:
            add(r[0], r[1], base)
            if base.startswith('00_') and len(r) >= 3:
                if r[2] == 'material':
                    materials[r[0].strip()] = r[1].strip()
                elif r[2] == 'stat':
                    stats[r[0].strip()] = r[1].strip()

# 1b) forced substrings: combat-log pieces, with ␣ standing in for real spaces.
forced_frag = {}
for _p in sorted(glob.glob('glossary/*.tsv')):
    if os.path.basename(_p)[:3] not in FORCED_FRAG_FILES:
        continue
    for r in rows(_p):
        if len(r) >= 2:
            zh = r[0].replace(SPACE_MARK, ' ')
            en = r[1].replace(SPACE_MARK, ' ')
            if zh and en:
                forced_frag[zh] = en

# 1c) compound weapon names. items.js builds these at runtime as
#         `${head.name_prefix} ${WTM[weapon_type]}`     e.g. "脉冲 剑"
#     so the space-joined form never appears in any source string and can only be
#     produced combinatorially. Exact-match, so no substring collision risk.
WEAPON_TYPES = {'剑': 'Sword', '三叉戟': 'Trident',
                '月轮': 'Moonwheel', '战锤': 'War Hammer'}
weapon_names = {}
for mzh, men in materials.items():
    for wzh, wen in WEAPON_TYPES.items():
        # spaced form is what getName() builds at runtime; the unspaced form is
        # how the predefined templates are written (铁剑, 秘银月轮, 充能戟)
        weapon_names['%s %s' % (mzh, wzh)] = '%s %s' % (men, wen)
        weapon_names['%s%s' % (mzh, wzh)] = '%s %s' % (men, wen)
# 戟 is the short form of 三叉戟 used in the predefined weapon names
for mzh, men in materials.items():
    weapon_names['%s戟' % mzh] = '%s Trident' % men

# 1d) location names. These live only in Script.txt's #location_actions_div pair
#     list, so they translate on travel buttons and nowhere else - the location
#     title bar, the bestiary zone headers and "[ Enter X ]" all stayed Chinese.
#     Promote them to global fragments. Only the block after the DeepSeek marker
#     is taken: the pairs above it include generic words like ['到','to'] and
#     ['每','Every'] that would be catastrophic as global substrings.
# 1e) English enemy name -> original Chinese. Needed twice: to map a translated
#     name back for game code that reads it out of the DOM as a lookup key (the
#     bestiary/levelary hover handlers), and reversed, to let enemy names match
#     as substrings inside combat-log lines.
enemy_en_zh = {}
for r in rows('glossary/02_enemies.tsv'):
    if len(r) >= 2:
        _z, _e = r[0].strip(), r[1].strip()
        if _z and _e:
            enemy_en_zh.setdefault(_e, _z)

loc_frag = {}
# the 7 base names added in 04_locations.tsv aren't in Script.txt's list yet, and
# levelary rows like "纳家练兵场 - 7" need them as substrings, not exact matches
for r in rows('glossary/04_locations.tsv'):
    if len(r) >= 2 and r[0].strip():
        loc_frag[r[0].strip()] = r[1].strip()
_hdr = open('../Script.txt', encoding='utf-8').read()
_m = re.search(r'// Location list tanslated via DeepSeek(.*?)\n\s*\],', _hdr, re.S)
if _m:
    for _p in re.finditer(r"\['([^']+)',\s*'((?:[^'\\]|\\.)*)'\]", _m.group(1)):
        _zh, _en = _p.group(1), _p.group(2).replace("\\'", "'")
        if cjk(_zh):
            loc_frag[_zh] = _en

# 1f) Long sentences from the v4.0 pair lists, promoted to exact matches.
#
#     applySelector walks a selector's pair list IN ORDER and applies EVERY match
#     to a node, so a short pair listed earlier permanently destroys a longer one
#     listed later. #skill_list has
#         ['经验获取', 'XP Gain']                         (line ~1115)
#     before
#         ['增加所有低于此技能等级的秘法技能经验获取，…', …]   (line ~1146)
#     so the full sentence can never match - it has already been chewed up. That
#     bug predates the prose layer; it just became visible once everything around
#     it was translated.
#
#     Promoting these to proseExact fixes it without touching the hand-maintained
#     v4.0 lists: exact runs first, matches the whole node, and the short pairs
#     then find nothing left to break.
v4_long = {}
for _p in re.finditer(r"\['((?:[^'\\]|\\.)+?)',\s*'((?:[^'\\]|\\.)*?)'\]", _hdr):
    _zh = _p.group(1).replace("\\'", "'").replace('\\\\', '\\')
    _en = _p.group(2).replace("\\'", "'").replace('\\\\', '\\')
    # 8, not 10: "偷偷用镐子挖出宝石" is 9 characters and was falling through, so
    # the 宝石 -> "Gem" fragment shredded it before its own pair could match.
    if cjk(_zh) and len(_zh) >= 8 and _en:
        v4_long[_zh] = _en

# 2) items_desc.tsv: zh_name <TAB> zh_desc <TAB> en_desc
for r in rows('prose/items_desc.tsv'):
    if len(r) >= 3:
        add(r[1], r[2], 'items_desc.tsv')

# 3) done_*.tsv joined against _todo_*.tsv
#    key_mode: 'line' = _todo col1 (srcline) | 'row' = 1-based row index
JOBS = [
    ('items',     ['prose/done_items.tsv'],      'line'),
    ('enemies',   sorted(glob.glob('prose/done_enemies_*.tsv')), 'line'),
    ('locations', ['prose/done_locations.tsv'],  'line'),
    ('character', ['prose/done_character.tsv'],  'line'),
    ('skills',    ['prose/done_skills.tsv'],     'line'),
    ('dialogues', sorted(glob.glob('prose/done_dialogues_*.tsv')), 'row'),
    ('main',      ['prose/done_main.tsv'],       'row'),
    ('display',   ['prose/done_display.tsv'],    'row'),
    # Per-game-version corpora for content added after the original bulk pass.
    # A NEW frozen pair each time, never a regeneration of an existing one: the
    # keys above are positional (source line, or row index), so re-extracting
    # any _todo file after an upstream update renumbers it and silently re-pairs
    # every English string to a NEIGHBOURING Chinese one. The "no matching key"
    # warning below only catches a key that resolves to nothing.
    ('v341',      ['prose/done_v341.tsv'],       'row'),
    ('v346',      ['prose/done_v346.tsv'],       'row'),
    ('v347',      ['prose/done_v347.tsv'],       'row'),
]
for name, done_files, mode in JOBS:
    todo = rows('prose/_todo_%s.tsv' % name)          # kind, srcline, zh
    if mode == 'line':
        lookup = {r[1]: r[2] for r in todo if len(r) >= 3}
    else:
        lookup = {str(i): r[2] for i, r in enumerate(todo, 1) if len(r) >= 3}
    miss = 0
    for df in done_files:
        for r in rows(df):
            if len(r) < 2:
                continue
            zh = lookup.get(r[0])
            if zh is None:
                miss += 1
                continue
            # Padding in the SOURCE literal (" 上钩了！", " 受到了 ") means the game
            # concatenates this onto something else - "Lake Carp" + " 上钩了！" -
            # so it is never a whole text node and exact-match can never fire.
            # Register those as substrings, keeping the English spacing intact
            # (the space de-duplication in applyProse tidies any doubling).
            if zh != zh.strip():
                forced_frag.setdefault(zh.strip(), r[1].rstrip('\r\n'))
            add(zh, r[1], name)
    if miss:
        print('  !! %s: %d done-rows had no matching _todo key' % (name, miss))

# 4) small tails: file <TAB> srcline <TAB> en
tails = {}
for fn in ['traders', 'activities', 'crafting_recipes', 'misc']:
    for r in rows('prose/_todo_%s.tsv' % fn):
        if len(r) >= 3:
            tails[(fn + '.js', r[1])] = r[2]
for r in rows('prose/done_smalltails.tsv'):
    if len(r) >= 3:
        zh = tails.get((r[0], r[1]))
        if zh:
            add(zh, r[2], 'smalltails')

# ------------------------------------------------------- split into EXACT/FRAG
TAG  = re.compile(r'<[^>]*>')

def split_interp(s):
    """Split on ${...} honouring nested braces; return literal chunks."""
    out, buf, i = [], [], 0
    while i < len(s):
        if s[i] == '$' and i + 1 < len(s) and s[i+1] == '{':
            out.append(''.join(buf)); buf = []
            depth, i = 0, i + 1
            while i < len(s):
                if s[i] == '{': depth += 1
                elif s[i] == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        else:
            buf.append(s[i]); i += 1
    out.append(''.join(buf))
    return out

def fragments(s):
    """Literal text chunks that will exist as their own DOM text content."""
    chunks = []
    for part in TAG.split(s):          # HTML tags become element boundaries
        chunks.extend(split_interp(part))
    return chunks

def interp_split(s):
    """Split on ${...} into (literal_parts, expressions), preserving order.
    len(literals) == len(expressions) + 1."""
    lits, exprs, buf, i = [], [], [], 0
    while i < len(s):
        if s[i] == '$' and i + 1 < len(s) and s[i + 1] == '{':
            lits.append(''.join(buf)); buf = []
            depth, j = 0, i + 1
            while j < len(s):
                if s[j] == '{':
                    depth += 1
                elif s[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            exprs.append(s[i:j + 1])
            i = j + 1
        else:
            buf.append(s[i]); i += 1
    lits.append(''.join(buf))
    return lits, exprs

BR_TAGS = ('<br>', '<br/>', '<br />', '</br>')   # </br> is invalid but the
                                                 # source uses it; browsers
                                                 # render it as a line break

def _is_br(t):
    return t.lower() in BR_TAGS

def _split_words(text, n):
    """Break text into n runs of roughly equal length, on word boundaries."""
    words = text.split(' ')
    if not text or len(words) < n:
        return None
    target = len(text) / float(n)
    parts, cur = [], ''
    for w in words:
        if cur and len(parts) < n - 1 and len(cur) + 1 + len(w) > target:
            parts.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    parts.append(cur)
    while len(parts) < n:
        parts.append('')
    return parts

def _segments(chunks, tags):
    """Group chunks into segments delimited by NON-<br> tags.

    Those tags (colour spans, <b>) carry meaning and must line up exactly; the
    <br>s between them are just line wrapping and can be redistributed.
    """
    segs, seps = [[chunks[0]]], []
    for i, t in enumerate(tags):
        if _is_br(t):
            segs[-1].append(chunks[i + 1])
        else:
            seps.append(t)
            segs.append([chunks[i + 1]])
    return segs, seps

def rebalance_any(cz, ce, zh, en):
    """Re-wrap the English so it occupies the same DOM text nodes as the Chinese.

    Generalises rebalance_br: instead of demanding the string be <br>-only, it
    demands only that the NON-<br> tag sequence is identical on both sides. Those
    tags are structural (a coloured <span> must still wrap the same idea), while
    the <br>s around them are cosmetic line wrapping that Chinese uses far more
    freely than English. Within each span-delimited segment the English is
    re-split to match the Chinese line count.
    """
    zt, et = TAG.findall(zh), TAG.findall(en)
    if [t for t in zt if not _is_br(t)] != [t for t in et if not _is_br(t)]:
        return None                     # real structural difference; don't guess
    zsegs, _ = _segments(cz, zt)
    esegs, _ = _segments(ce, et)
    if len(zsegs) != len(esegs):
        return None
    out = []
    for zseg, eseg in zip(zsegs, esegs):
        if len(zseg) == len(eseg):
            out.extend(eseg)
            continue

        z_idx = [i for i, c in enumerate(zseg) if c.strip()]
        e_txt = [c.strip() for c in eseg if c.strip()]

        # Preferred: the two sides carry the same number of NON-EMPTY lines and
        # differ only in blank ones. Map them one-to-one and leave the blanks
        # blank. This keeps each line intact - vital when the lines are distinct
        # units (different speakers, a sound effect), where rewrapping would
        # strew speaker tags across line breaks.
        if len(z_idx) == len(e_txt):
            slot = [''] * len(zseg)
            for i, t in zip(z_idx, e_txt):
                slot[i] = t
            out.extend(slot)
            continue

        # Fallback: genuinely different line counts, so the segment has to be
        # re-wrapped. Only safe when the Chinese lines are one flowing
        # paragraph. Refuse when the segment looks deliberately structured -
        # blank lines used as separators, or lines opening with a speaker tag
        # "[X]" / a stage direction "(…)". Re-wrapping those strews speaker
        # labels across line breaks ("(sound of the / Moonwheel slicing) [Neko]
        # Important"), which is worse than leaving the text in Chinese.
        # Blank lines are fine - they are paragraph breaks, and the loop below
        # only fills Chinese-bearing slots, so they survive untouched. What we
        # must not rewrap is dialogue: lines opening with a speaker tag "[X]" or
        # "【X】" are distinct utterances, and re-flowing them moves the labels
        # onto the wrong lines.
        # Dialogue: half-width [X] marks a speaker (item and skill names use
        # full-width 【X】, so they must not count here). Re-flowing across
        # speakers scatters the labels, but each utterance can be re-wrapped
        # safely on its own - so align on the speaker lines as anchors and only
        # redistribute the continuation lines between them.
        def spk(s):
            return s.lstrip()[:1] == '['

        if any(spk(zseg[i]) for i in z_idx):
            zgroups, egroups = [], []
            for i in z_idx:
                if spk(zseg[i]) or not zgroups:
                    zgroups.append([i])
                else:
                    zgroups[-1].append(i)
            for t in e_txt:
                if spk(t) or not egroups:
                    egroups.append([t])
                else:
                    egroups[-1].append(t)
            if len(zgroups) != len(egroups):
                return None            # can't pair utterances; leave it alone
            slot = [''] * len(zseg)
            for zg, eg in zip(zgroups, egroups):
                text = ' '.join(eg)
                parts = _split_words(text, len(zg)) if len(zg) != len(eg) else eg
                if parts is None:
                    return None
                for i, p in zip(zg, parts):
                    slot[i] = p
            out.extend(slot)
            continue
        idxs = [i for i in z_idx if cjk(zseg[i])]
        text = ' '.join(e_txt)
        if not idxs or not text:
            return None
        parts = _split_words(text, len(idxs))
        if parts is None:
            return None
        slot = [''] * len(zseg)
        for i, p in zip(idxs, parts):
            slot[i] = p
        out.extend(slot)
    return out if len(out) == len(cz) else None

def rebalance_br(cz, ce, zh, en):
    """Re-split the English so it has as many visual lines as the Chinese.

    Chinese uses <br> as cosmetic line wrapping, often mid-sentence, e.g.
        ……也罢。<br>（唉，这次居然栽在一个小丫头手上，<br>运气是真的差……）
    English joins those into one flowing clause, so the translation legitimately
    has fewer breaks and the chunks no longer pair up 1:1. Rather than drop the
    string, redistribute the English text across the same number of lines.

    Only <br> is handled; if either side carries any other tag the structure is
    meaningful and we must not guess. Returns a new list of English chunks, or
    None when it isn't safe.
    """
    tags = TAG.findall(zh) + TAG.findall(en)
    if not tags or any(t.lower() not in BR_TAGS for t in tags):
        return None
    # Only the chunks that actually hold Chinese get text; blank ones (from
    # consecutive <br><br>) must stay blank so the line breaks are preserved.
    idxs = [i for i, c in enumerate(cz) if c.strip() and cjk(c)]
    if not idxs:
        return None
    text = ' '.join(p.strip() for p in ce if p.strip())
    if not text:
        return None
    words, n = text.split(' '), len(idxs)
    if len(words) < n:
        return None
    target = len(text) / float(n)
    parts, cur = [], ''
    for w in words:
        if cur and len(parts) < n - 1 and len(cur) + 1 + len(w) > target:
            parts.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    parts.append(cur)
    while len(parts) < n:
        parts.append('')
    out = [''] * len(cz)
    for slot, part in zip(idxs, parts):
        out[slot] = part
    return out

def make_regex_pair(zh, en):
    """Turn an interpolated template into an anchored regex + replacement.

    Splitting these into fragments is WRONG: English reorders, so
    "制造 ${x} 失败!" -> "Failed to craft ${x}!" would teach us that 制造 means
    "Failed to craft" and 失败 means "!", and those then fire as substrings in
    unrelated text. Matching the whole rendered node keeps word order intact.

    Returns (pattern, replacement, hint) or None if the two sides don't use the
    same set of expressions (then we can't map capture groups safely).
    """
    zl, ze = interp_split(zh)
    el, ee = interp_split(en)
    if not ze or any(e not in ze for e in ee):
        return None
    # A pattern whose literals hold no ideograph is not translating anything -
    # there is no word order to preserve. It can only be swapping punctuation,
    # and that is actively harmful: stage 2 runs BEFORE the fragment stage and
    # breaks on first match, so such a rule rewrites the node and destroys the
    # character longer fragment keys are anchored on. '^(.+?)！$' -> '$1!' was
    # pre-empting 286 fragment keys - every Chinese string ending in ！ - which
    # is how a fully-translated glossary line still rendered as Chinese.
    # Punctuation belongs in the fragment stage, where it sorts last and can
    # only touch what nothing else claimed.
    if not any(cjk(l) for l in zl):
        return None
    # The pattern is anchored against the TRIMMED node text, so the literals
    # must be trimmed at the outer edges too. A chunk sliced out of HTML keeps
    # the source's indentation ("  快速返回 [${...}]"), and a pattern starting
    # with those spaces could never match.
    zl[0], zl[-1] = zl[0].lstrip(), zl[-1].rstrip()
    el[0], el[-1] = el[0].lstrip(), el[-1].rstrip()
    pattern = ''
    for k, lit in enumerate(zl):
        pattern += re.escape(lit)
        if k < len(ze):
            # A TRAILING interpolation can legitimately render empty - the game
            # writes optional suffixes as `${cond?"":"(…)"}` - and (.+?) then
            # refuses the common case. That silently killed
            #   使用了 ${name} , 获取了 ${n} 经验${E_modi==1?"":`(压级-…)`}
            # which needs one char after 经验 to match but usually has none, so
            # the message stayed Chinese and v4.0 chewed it into "Used了 …".
            # Only the LAST group is loosened, and only when nothing follows it:
            # inner groups sit between literals and must stay non-empty or they
            # would swallow their anchors.
            if k == len(ze) - 1 and not zl[-1].strip():
                pattern += '(.*)'
            else:
                pattern += '(.+?)'
    repl = ''
    for k, lit in enumerate(el):
        repl += lit
        if k < len(ee):
            repl += '$%d' % (ze.index(ee[k]) + 1)
    # cheap pre-filter so we don't run hundreds of regexes against every node
    hint = max(zl, key=len) if zl else ''
    if not hint.strip():
        return None
    return '^' + pattern + '$', repl, hint.strip()

exact, frag, regexes, skipped = {}, {}, [], []
rebalanced = 0
chunk_keys = set()      # exact keys that are a whole text node in their own right
_seen_rx = set()

# Some ${...} slots expand to HTML, not text: format_money() returns
# `<span class="coin coin_copper">18D</span>` and friends. That splits the node
# at runtime exactly as a literal tag would, so the whole-node regex built from
# such a template can NEVER match - the node stops at the slot ("余额不足! (").
# Reported twice from the message log: 余额不足! and 钱包:.
#
# So also emit the literal pieces as fragments. This is the splitting that
# make_regex_pair warns against, and it is only safe under a strict guard: the
# expressions must appear in the SAME ORDER on both sides, which is what makes
# literal k on the left correspond to literal k on the right. If English
# reorders the slots, we emit nothing and leave the regex as the only attempt.
# Names whose ${...} slot expands to HTML rather than text. Two kinds:
#   - functions that RETURN markup: format_money() -> <span class="coin">...
#   - variables ASSIGNED markup:    lvl_display = `<span class="realm_terra">...`
# Found by scanning src/*.js for `NAME = "<..."` and keeping the ones actually
# interpolated into a Chinese template; lvl_display is the only variable that
# qualifies today (it is why "Neko 境界突破，达到 <span>" stayed Chinese).
HTML_SLOT_FNS = ('format_money', 'lvl_display')
html_frag = {}

def add_html_slot_frags(zh, en):
    zl, ze = interp_split(zh)
    el, ee = interp_split(en)
    if not ze or ze != ee or len(zl) != len(el):
        return
    if not any(fn in e for e in ze for fn in HTML_SLOT_FNS):
        return
    for a, b in zip(zl, el):
        # STRIP both sides. Stage 3 matches against `trimmed`, so a key holding
        # the source's trailing space ("钱包: ") could never fire; the runtime
        # writes back with original.replace(trimmed, text), which restores the
        # surrounding whitespace anyway. Same convention as the padded-literal
        # rule above.
        a, b = a.strip(), b.strip()
        if a and cjk(a) and b:
            html_frag.setdefault(a, b)

def pad_norm(ec):
    """One space, at most, on each side that had any whitespace at all.

    What the padding means is 'there is a word boundary here', so a run of two
    spaces (authored in a couple of done_*.tsv rows) or a stray tab says nothing
    extra. HTML would collapse them anyway; normalising keeps the tables tidy
    and stops whitespace noise from looking like two different translations to
    the uniqueness check below.
    """
    return ((' ' if ec[:1].isspace() else '') + ec.strip() +
            (' ' if ec[-1:].isspace() else ''))


def add_chunk(zc, ec):
    """Handle one DOM text node's worth of content.

    HTML tags split a string into several text nodes, so each chunk is matched
    on its own. A chunk containing ${...} becomes a regex (word order is
    preserved); a plain chunk becomes a whole-node exact match. Nothing here
    produces substrings any more - those come only from the curated lists.
    """
    if '${' in zc:
        add_html_slot_frags(zc, ec)
        rp = make_regex_pair(zc, ec)
        if rp and rp[0] not in _seen_rx:
            _seen_rx.add(rp[0])
            regexes.append(rp)
        else:
            skipped.append((zc, 'dup-regex' if rp else 'regex', ec))
        return
    a = zc.strip()
    if a and cjk(a) and ec.strip():
        # Keep the space the translator wrote, where the key is unambiguous
        # enough for it to be safe - see PAD_OK below. A tag boundary is not a
        # word boundary, so stripping both sides glued "…weakened by" to the
        # <span> holding "10%".
        exact.setdefault(a, pad_norm(ec) if a in PAD_OK else ec.strip())
        # A chunk is its own DOM text node, so exact-match already covers it;
        # remember that, to keep it out of the substring alternation below.
        chunk_keys.add(a)

# Split first, register second. The padding guard below has to see every value
# a key is given before any of them is committed. The ops list preserves
# registration order, and with it the precedence between a whole string
# (assignment, always wins) and a chunk (setdefault, first wins) - so replaying
# it is identical to the single pass this replaced.
_ops = []
for zh, en in pairs.items():
    if '${' not in zh and '<' not in zh:
        _ops.append(('whole', zh, en))
        continue
    if '<' in zh:
        cz, ce = TAG.split(zh), TAG.split(en)
        if len(cz) != len(ce):
            # rebalance_any also covers the <br>-only case (no non-<br> tags =>
            # a single segment), and it alone has the non-empty-line alignment
            # and the "don't rewrap structured text" guard. The older
            # rebalance_br is deliberately NOT tried first: it would rewrap
            # speaker lines and scatter the labels.
            ce = rebalance_any(cz, ce, zh, en)
            if ce is None:
                skipped.append((zh, 'structure', en))   # real difference; don't guess
                continue
            rebalanced += 1
        for a, b in zip(cz, ce):
            _ops.append(('chunk', a, b))
    else:
        _ops.append(('chunk', zh, en))

# ---- which chunks may keep the space their translator wrote ----------------
# A chunk is one DOM text node, and a tag boundary is not a word boundary:
# "PS:对" + <span class='realm_cloudy'>云霄级</span> is correct Chinese and
# rendered "PS: No effect on targetsSkyhigh-Tier". The done_*.tsv English has
# always carried that space; add_chunk used to strip it off both sides.
#
# Restoring it is safe only where the key means ONE thing, because proseExact
# is context-free: a value chosen for the one place a key sits beside a <span>
# is then applied EVERYWHERE that key appears. 攻击 is both a chunk here and a
# standalone stat label in display.js, and would have picked up a stray space
# in the stat panel to fix a tooltip somewhere else. So, two conservative rules:
#   - the key is given exactly ONE English value across the whole corpus, so
#     setdefault never has to choose between two spellings that differ only in
#     padding (获取了 is authored both ways), and
#   - the key is not also a whole-string entry.
# Every refusal is printed. Silently dropping the space is how this survived
# seventeen versions unnoticed, and a silent exception list would be the same
# mistake one level down.
_whole_keys = {zh for kind, zh, _ in _ops if kind == 'whole'}
_chunk_vals = collections.defaultdict(set)
for _kind, _zc, _ec in _ops:
    if _kind == 'chunk' and '${' not in _zc:
        _k = _zc.strip()
        if _k and cjk(_k) and _ec.strip():
            _chunk_vals[_k].add(pad_norm(_ec))
PAD_OK = {k for k, v in _chunk_vals.items() if len(v) == 1 and k not in _whole_keys}
pad_kept = sorted(k for k in PAD_OK
                  if any(x != x.strip() for x in _chunk_vals[k]))
# forced_frag keys are popped back out of exact further down and shipped as
# fragments, padding and all - so a refusal there costs nothing and listing it
# is noise in a report whose whole point is to be actionable.
pad_refused = sorted(k for k, v in _chunk_vals.items()
                     if k not in PAD_OK and k not in forced_frag
                     and any(x != x.strip() for x in v))

for _kind, _a, _b in _ops:
    if _kind == 'whole':
        exact[_a] = _b
    else:
        add_chunk(_a, _b)

# Hand-written patterns for text the game assembles inline rather than from a
# single template literal, so nothing in the source can be paired against it.
# (pattern, replacement, indexOf-hint)
regexes.extend([
    # "31698纪元 1380年 19日 052:06" -> "Epoch 31698 Yr 1380 D 45 052:06".
    # Kept tight on purpose: Chinese characters are double-width, so the
    # original occupies far fewer columns than a spelled-out English date and
    # "Year/Day" plus commas overflowed #time_div. If it still wraps, the next
    # step down is 'E$1 Yr$2 D$3 '.
    (r'(\d+)纪元\s*(\d+)年\s*(\d+)日\s*', 'Epoch $1 Yr $2 D $3 ', '纪元'),
    # "12.34年" -> "12.34 yr". The ice-container ETA is assembled inline as
    # (n).toFixed(2)+'年', and index.html ships a static "10000 年" placeholder
    # that shows until the first tick overwrites it. Anchored on purpose: the
    # 纪元 pattern above owns the full date line, which also contains 年.
    (r'^([\d.,]+)\s*年$', '$1 yr', '年'),
    # container_element_time picks its unit by magnitude: 秒/分钟/小时/天/年.
    # 分钟 and 小时 are fragments already; these two were not, so the engine ETA
    # showed Chinese at short and medium durations only. Anchored, so a bare
    # digits+天 node is the only thing they can touch (天 is far too common
    # otherwise - 天空级, 天外飞船).
    (r'^([\d.,]+)\s*秒$', '$1 s', '秒'),
    (r'^([\d.,]+)\s*天$', '$1 d', '天'),
    # Equipment-slot tooltip: display.js builds `你的 ${mapp[key]} 槽位` for all
    # 13 slots. v4.0 pairs cover the 10 original ones; the tool slots
    # (镰刀/镐子/斧子) were added later and had none, which is how
    # "你的 Scythe Slot" reached a player. The three are exact entries in
    # glossary 11 so they fire in the exact-only tooltip pass; this pattern is
    # the general safety net, and any Chinese left in $1 is cleaned up by the
    # fragment stage, which runs after this one on the same text.
    (r'^你的\s*(.+?)\s*槽位$', 'Your $1 Slot', '槽位'),
    # 灵体 (Ethereal): display.js CONCATENATES the value into the middle of the
    # string ("...造成<span>" + spec_value[21] + "与角色敏捷之差的五倍</span>..."), so
    # the node is "360000与角色敏捷之差的五倍". The exact entry for the bare phrase
    # cannot match with a number glued to its front, and the fragment stage then
    # chewed it into "360000与CharacterAgility之差的五倍".
    # 'x' not '×', to match the style the prose already uses (2.5x, 20x Attack).
    (r'^(.+?)与角色敏捷之差的五倍$', '5x ($1 - Agility)', '之差的五倍'),
    # Bare count/multiplier inside a coloured span: "敌人攻击<span>4次</span>。"
    # Exact entries exist only for the values that happen to appear literally in
    # the source (2次 from 2连击, 2.5倍), so every other value fell through and
    # rendered as Chinese. ANCHORED, so they match only a node that is exactly a
    # number plus the unit - "50倍伤害" and its whole-node exact entry are
    # untouched, and stage-1 exact still beats these anyway.
    (r'^([\d.,]+)次$', '$1 times', '次'),
    (r'^([\d.,]+)倍$', '$1x', '倍'),
    # XP-multiplier readout: `x${mult} ${MulNameMap[k]} 经验获取`. The generic
    # rule built from that template captures the NAME as $2 and inserts it
    # verbatim, and the fragment stage runs too late to rescue it - so
    # "x2 全部 经验获取" rendered as "x2 全部 XP Gain". 等级 survives because it is
    # a fragment; 全部 and 技能 deliberately are not (全部 is a v4.0 button pair,
    # a bare 技能 fragment breaks "秘法 技能" -> Technique Skills). Longer hint,
    # so these sort ahead of the generic rule. The optional leading comma covers
    # the ", x2 …" continuation form; a non-participating group is '' in JS.
    (r'^(,\s*)?x(.+?)\s+全部\s+经验获取$', '$1x$2 All XP Gain', '全部 经验获取'),
    (r'^(,\s*)?x(.+?)\s+技能\s+经验获取$', '$1x$2 Skill XP Gain', '技能 经验获取'),
    # dialogue options are formulaic: "和 枫杏红 对话", "与 营地商铺 对话"
    (r'^[和与]\s*(.+?)\s*对话$', 'Talk with $1', '对话'),
    (r'^[和与]\s*(.+?)\s*交流$', 'Speak with $1', '交流'),
    (r'^使用\s*\[(.+?)\]$', 'Use [$1]', '使用'),
    (r'^参悟(.+)$', 'Comprehend $1', '参悟'),
    # V3.43 Blood Peak modifiers. display.js interpolates the held count into
    # BOTH the bracket tag and the figure, so there is no fixed string to match
    # - the count appears twice in the first one and the amount is a
    # format_numberL() result in the second.
    (r'^\[(.+?)x限制器\]本区光环已被降低(.+?)%!$',
     "[$1x Restrictor] This zone's aura is lowered by $2%!", '本区光环已被降低'),
    (r'^\[(.+?)x增幅器\]本区光环已被增幅(.+?)!$',
     "[$1x Amplifier] This zone's aura is amplified by $2!", '本区光环已被增幅'),
    # V3.42 吹火 C6. Both names are interpolated; $2 is an enemy name and is
    # left in Chinese by this stage, then resolved by the fragment stage which
    # runs after it on the same text - enemy names are all fragments.
    (r'^(.+?) 将 (.+?) 的攻击 延迟了0.5轮!\[吹火 C6\]\.$',
     "$1 delayed $2's attack by 0.5 rounds! [Fire-Blowing C6].", '延迟了0.5轮'),
    # V3.44 family power unlock. main.js builds it as
    #     `因 ${name} 的战力超过了 ${power} , 家族系统开放了 <span…> REALM </span>!`
    # so the realm name is inside a coloured span and the node this sees is
    # only the LEADING chunk, ending after 家族系统开放了. Anchoring on the
    # whole sentence would never match. The trailing space is kept in the
    # replacement because the span follows immediately.
    (r'^因 (.+?) 的战力超过了 (.+?) , 家族系统开放了\s*$',
     "$1's Power passed $2, so the family system opened up ", '家族系统开放了'),
    # 清野瀑布 wf2, once DeathCount-1 has unlocked. main.js:844 concatenates
    #     "如今也算是历经了" + format_number(total_deaths) + "次生死呢，<br>…"
    # so the count is spliced into the middle of the sentence and the <br>
    # ends the text node. The prose entry for this line was written across the
    # <br>, and the build's rebalancing left "次生死呢，" as an EXACT entry -
    # which can never fire, because at runtime it is only ever a SUFFIX after
    # the number. Result on screen: "By now, having been through 3次生死呢，".
    #
    # v17.2 tried to fix this with two ^…$ templates and they never fired: the
    # node is MERGED. wf2 also carries static text, and main.js:1411 does
    #     displayed_text = textline.text;  displayed_text += textline_special(…)
    # so the runtime node is the static line's TAIL glued to the special
    # line's HEAD - "也知道了…意思。如今也算是历经了3次生死呢，" - and an anchored
    # pattern cannot see it. The suffix is a FRAGMENT now, which works whether
    # the node is merged or not. See 09_dialogue_terms.tsv.
    #
    # The count of one keeps a rule of its own, because English needs plural
    # agreement and a fragment cannot branch. Matched on the whole merged node,
    # so if the static text ever changes this simply stops matching and the
    # fragment takes over - rendering "1 brushes with death", which is wrong but
    # not broken.
    # V3.45: bulk use of a consumable past its realm cap is emptied rather
    # than applied, to avoid the stall. The item name is interpolated, so $1
    # is left in Chinese here and resolved by the fragment stage after.
    (r'^为避免批量使用带来的潜在卡顿，已清空 (.+?) \.$',
     'Cleared $1 to avoid the stutter bulk use would cause.', '已清空'),
    (r'^也知道了父亲大人的话是什么意思。如今也算是历经了1次生死呢，$',
     'and I understand what Father meant.'
     'By now, having been through a single brush with death,', '了1次生死呢'),
    # V3.46 turned Sayuki's third refusal from a flat "top ten" into the live
    # rank, so the old exact key in 11_dialogue_exact.tsv is retired for this
    # template. NOTE: the game calls chara_result.toLocateString - a typo for
    # toLocaleString - so as shipped this line throws before it is ever logged.
    # The pattern is here for when that is fixed; it costs nothing until then.
    (r'^\[纱雪\]达到燕岗领排名 (.+?) / 10 之后随便卖！$',
     '[Sayuki] Sell him all you like once you hit Yangang Fief rank $1 / 10!',
     '达到燕岗领排名'),
])

# longest hint first so more specific templates win
regexes.sort(key=lambda r: -len(r[2]))

# ---- textline_special chunks that MERGE with the dialogue line -------------
# main.js builds a dialogue answer as
#     let displayed_text = textline.text;          // "[枫杏红]…" from dialogues.js
#     displayed_text += textline_special(spec);    // no <br> in between
# so the dialogue's last segment and the special text's FIRST segment land in one
# DOM text node. The special's leading chunk therefore never matches its own
# exact entry - which is how "[Feng Xinghong]我说，“饵料”已经布下!!" reached a
# player with a perfectly good translation sitting unused in the dict. The frag
# stage then translated only the speaker tag and the punctuation, which is the
# tell for this whole class: a fully English line with one Chinese island.
#
# Promote those leading chunks to fragments so they fire whatever is glued in
# front of them. Derived from main.js rather than hand-listed, so a newly added
# branch is covered automatically; the English is taken from the pair that
# already exists, so there is nothing to keep in sync.
_mainjs = open('../NekoRPG/src/main.js', encoding='utf-8').read()
merge_promoted = []
for _m in re.finditer(r'displayed_text\s*\+=\s*[`\'"]([^`\'"]*)[`\'"]', _mainjs):
    _piece = _m.group(1)
    if _piece.lstrip().startswith('<br>'):
        continue                       # opens its own node; not merge-exposed
    _lead = _piece.split('<br>')[0].strip()
    # Only whole literals: a chunk containing ${...} is matched by a whole-node
    # regex instead, and promoting a fragment of one would split the template.
    if not _lead or '${' in _lead or not cjk(_lead):
        continue
    # Must already be a known exact entry, and long enough that firing as a
    # substring cannot be an accident. Short strings stay exact-only - that is
    # the 剑/巨剑徽章 rule.
    if len(_lead) < 6 or _lead not in exact:
        continue
    frag[_lead] = exact.pop(_lead)
    merge_promoted.append(_lead)

# ---- merge the specially-handled sets -------------------------------------
# Combat-log pieces are substrings by nature, so they override any exact entry
# that happens to share the key (e.g. "伤害" alone as a stat label).
for _zh, _en in forced_frag.items():
    frag[_zh] = _en
    exact.pop(_zh, None)
# Literals stranded next to an HTML-producing ${} slot (see add_html_slot_frags).
# setdefault, not assignment: a curated entry always outranks a derived one.
for _zh, _en in html_frag.items():
    frag.setdefault(_zh, _en)
# Location names apply everywhere, not just on travel buttons.
for _zh, _en in loc_frag.items():
    frag.setdefault(_zh, _en)
# Bare material names as substrings. Recipe names are compositional
# ("熔炼精钢" = Smelt + Steel, "盖亚合金" = Gaia + Alloy), so with the verbs and
# suffixes in 08 these compose instead of needing an entry each. Longest-first
# ordering keeps 精钢锭 (Steel Ingot) winning over 精钢 (Steel).
for _zh, _en in materials.items():
    if len(_zh) >= 2:
        frag.setdefault(_zh, _en)
# Stat names as substrings too. v4.0's statPairs only reach .item_tooltip and
# .stat_tooltip, so a stat named anywhere else - e.g. the active-effect tooltip's
# "幸运 : x1.2" - had no match at all. Longest-first keeps 攻击速度 (Attack Speed)
# ahead of 攻击 (Attack), and 生命上限 (Health Cap) ahead of 生命 (Health).
for _zh, _en in stats.items():
    if len(_zh) >= 2:
        frag.setdefault(_zh, _en)
# Enemy names too: combat log lines embed them ("百方[...][BOSS] 受到了 N 伤害"),
# and exact-match only fires when the name is the entire text node.
for _en, _zh in enemy_en_zh.items():        # this map is keyed English -> Chinese
    frag.setdefault(_zh, _en)
# Long v4.0 sentences: setdefault so our own translation wins where we have one.
for _zh, _en in v4_long.items():
    exact.setdefault(_zh, _en)

# Space-joined weapon names only ever exist at runtime; exact-match is safe.
for _zh, _en in weapon_names.items():
    exact.setdefault(_zh, _en)
    # ...and as substrings, so suffixed forms still resolve: "铁剑·改" is split by
    # the ·改 entry, leaving a bare 铁剑 that exact-match can no longer see.
    # Longest-first keeps 铁剑刃 (Iron Sword Blade) ahead of 铁剑 (Iron Sword).
    if len(_zh) >= 2:
        frag.setdefault(_zh, _en)

# Long strings double as substrings. The game concatenates descriptions into
# bigger nodes ("黑暗 I : 一个永远和...地方"), where a whole-node match can never
# fire. A 8+ character Chinese sentence is distinctive enough that matching it
# inside other text carries no realistic collision risk.
for _zh, _en in list(exact.items()):
    if len(_zh) >= 8 and cjk(_zh) and _zh not in chunk_keys:
        frag.setdefault(_zh, _en)

# Item and skill names, lifted from the v4.0 itemNames dict, so they also
# translate when embedded in a sentence ("制造了 铁锭 x5", "解锁新技能: 挖掘").
# applyItemNames only catches them in specific containers and anchored patterns.
# 2-char minimum: single characters like 峰 (Peak) would wreck 峰大哥 (Brother Feng).
_names_block = _hdr.split('const itemNames = {')[1].split('\n    };')[0]
_item_names = 0
for _m in re.finditer(r"^\s+'((?:[^'\\]|\\.)+)': '((?:[^'\\]|\\.)*)',$", _names_block, re.M):
    _zh = _m.group(1).replace("\\'", "'")
    _en = _m.group(2).replace("\\'", "'")
    if len(_zh) >= 2 and cjk(_zh) and _en:
        if frag.setdefault(_zh, _en) is _en:
            _item_names += 1

# ------------------------------------------------------------------ emit JS
def js(s):
    return (s.replace('\\', '\\\\').replace("'", "\\'")
             .replace('\n', '\\n').replace('\r', ''))

def dict_block(name, d, keyorder=None, numeric=False):
    """numeric=True emits values unquoted - for partTiers, whose values are
    integers and where a quoted '0' would still be truthy in JS."""
    keys = keyorder if keyorder else sorted(d)
    # null-prototype: a plain {} would make proseExact['constructor'] (and
    # 'toString', '__proto__', ...) return inherited members and corrupt any
    # text node that happens to equal one of those words.
    lines = ["    const %s = Object.assign(Object.create(null), {" % name]
    for k in keys:
        val = '%d' % d[k] if numeric else "'%s'" % js(d[k])
        lines.append("        '%s': %s," % (js(k), val))
    lines.append("    });")
    return '\n'.join(lines)

# longest first so the mega-regex prefers the most specific match
frag_keys = sorted(frag, key=lambda k: (-len(k), k))

block = []
block.append("    // ==== GENERATED by translation/build.py - do not hand-edit ====")
block.append("    // %d exact-match strings, %d substring fragments." % (len(exact), len(frag)))
block.append("    // EXACT: whole text node equals the key (descriptions, dialogue, labels).")
block.append("    // FRAG : pieces of strings the DOM splits apart because the source had")
block.append("    //        HTML tags or ${...} interpolation. Matched as substrings via one")
block.append("    //        combined regex (longest alternative first = longest match wins).")
block.append(dict_block('proseExact', exact))
block.append("")
block.append(dict_block('proseFrag', frag, frag_keys))
block.append("")
block.append("    // Single alternation instead of N passes per text node - one regex scan.")
block.append("    const proseFragRe = new RegExp(Object.keys(proseFrag)")
block.append("        .map((s) => s.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')).join('|'), 'g');")
block.append("")
block.append("    // Interpolated templates ('制造 ${x} 失败!'), matched against the whole")
block.append("    // node. Splitting these into substrings would be wrong: English reorders,")
block.append("    // so we would learn that 制造 means 'Failed to craft'. Entries are")
block.append("    // [pattern, replacement, hint]; hint is a plain indexOf pre-filter.")
block.append("    const proseRegex = [")
for _pat, _rep, _hint in regexes:
    block.append("        ['%s', '%s', '%s']," % (js(_pat), js(_rep), js(_hint)))
block.append("    ].map((r) => [new RegExp(r[0]), r[1], r[2]]);")
block.append("")
block.append("    // English enemy name -> original Chinese, for game code that reads")
block.append("    // a translated name back out of the DOM and uses it as a lookup key.")
block.append(dict_block('bestiaryNames', enemy_en_zh))
block.append("")

# ---- travel options that walk BACKWARD -------------------------------------
# mirrorReturnIcons has to decide forward-vs-backward from the LABEL, because
# display.js emits an identical
#     <div class="travel_normal action_travel"><i>directions</i> TEXT
# for both. A prefix rule does NOT work, and the trap is specific: "Leave the
# village" and "Leave the safe path" both go FORWARD (Village -> Forest road ->
# Forest), while "Climb out", "Give up" and "Back off" all go back. So the set
# is enumerated instead of guessed.
#
# leave_text is backward BY CONSTRUCTION - display.js uses it only in the branch
# that walks to parent_location - so it is read straight out of locations.js and
# a newly added one can never be missed.
_locjs = open('../NekoRPG/src/locations.js', encoding='utf-8').read()

# connected_locations carry custom_text and can go either way, so these are
# curated. Keyed by the CHINESE so an entry survives a re-wording of the
# English. Anything rendering as "Return …" is left out - RETURN_LABEL_RE
# already covers it.
BACKWARD_CUSTOM = [
    '离开地宫',            # Leave the Crypt
    '走小路，回到营地',      # Take the side path, return to the Camp
    '赶路回到家族秘境',      # Hurry back to the Family Secret Realm
    '暂且离开这艘飞船',      # Leave this spaceship for now
    '暂且离开核心区域',      # Leave the core area for now
    '离开决战之地',         # Leave the final battle ground
]

# Rest locations: a location you can sleep at, i.e. one whose definition
# carries a `sleeping:` block. Read out of locations.js so a newly added bed
# can never be missed.
#
# The slice runs from one `new Location(` to the NEXT DEFINITION, not to the
# next `locations[`: connected_locations reference other locations by
# locations["..."] inside a definition, and 纳可的房间 puts its sleeping block
# after one of those. Slicing on `locations[` drops it.
_loc_defs = list(re.finditer(r'locations\["([^"]+)"\]\s*=\s*new (\w+)\(', _locjs))
rest_locations = []
for _i, _m in enumerate(_loc_defs):
    _end = _loc_defs[_i + 1].start() if _i + 1 < len(_loc_defs) else len(_locjs)
    if re.search(r'\n\s{8}sleeping:\s*\{', _locjs[_m.end():_end]):
        rest_locations.append(_m.group(1))
# The count is cross-checked against the raw number of sleeping blocks, so a
# definition that stops matching the slice shows up as a build warning rather
# than as a silently uncoloured link. Also confirmed at build time: every
# location's `name:` equals its key, which is what data-travel is set from.
_sleep_total = len(re.findall(r'\bsleeping:\s*\{', _locjs))
if len(rest_locations) != _sleep_total:
    print('!!  rest locations: matched %d of %d sleeping blocks in locations.js'
          % (len(rest_locations), _sleep_total))

# Realm TIER prefixes, as the family roster renders them in English.
#
# Almost no full realm name ("天空级一阶") exists as a dictionary entry - they
# are assembled compositionally, tier fragment + rank fragment - so this looks
# up the PREFIX, not the whole string. The prefixes live in proseFrag and each
# carries a TRAILING SPACE, which is precisely how "Sky-Tier " + "Rank 1"
# joins: that space is the break point the roster wants.
_realm_blk = re.search(r'const realm_rate\s*=\s*\[(.*?)\n\]', _mainjs, re.S)
realm_tiers, _realm_missing = [], []
if _realm_blk:
    for _zh, _cls in re.findall(r'"([^"]+)"\s*,\s*"(realm_\w+)"', _realm_blk.group(1)):
        _pfx = _zh.split('级')[0] + '级'
        _en = (frag.get(_pfx) or exact.get(_pfx) or '').rstrip()
        if not _en:
            if _pfx not in _realm_missing:
                _realm_missing.append(_pfx)
            continue
        if _en not in realm_tiers:
            realm_tiers.append(_en)
else:
    print('!!  realm_rate not found in main.js - realm names will not break')
# Loud: an untranslated prefix is silent otherwise, since the runtime pass just
# leaves that cell on one line and looks like a styling choice.
if _realm_missing:
    print('!!  %d realm tier prefixes with NO translation - these will not break:'
          % len(_realm_missing))
    for _pfx in _realm_missing:
        print('      %s' % _pfx)

backward_labels, _backward_missing = [], []
for _zh in ([m.group(1) for m in re.finditer(r'leave_text:\s*"([^"]+)"', _locjs)]
            + BACKWARD_CUSTOM):
    # Look in BOTH dicts: the leave_texts resolve as location-nav FRAGMENTS,
    # not exact entries, so an exact-only lookup would silently emit Chinese
    # into a set that is only ever compared against English.
    _en = exact.get(_zh) or frag.get(_zh)
    if _en is None:
        if cjk(_zh):
            _backward_missing.append(_zh)   # untranslated: reported below
            continue
        _en = _zh                           # already English in the source
    if _en not in backward_labels:
        backward_labels.append(_en)

# ---- component tiers, for the crafting list prefix -------------------------
# The tooltip is NOT a usable source for this. display.js prints 部件等级 only
# inside `else if(item.tags.component)` and only under `if(item.component_tier)`,
# which fails in two unrelated ways:
#   - an Armor-class part (幻符背心, tier 16) takes the EQUIPPABLE branch and
#     never reaches the tier line at all - 53 items, every one of which the
#     tooltip reading called T0;
#   - a genuine tier-0 part (铁剑刃) is skipped by the falsy test - 10 items.
# A missing line means both things, so the DOM cannot tell them apart. Read the
# tiers from the source instead, where they are unambiguous.
_itemsjs = open('../NekoRPG/src/items.js', encoding='utf-8').read()
_tier_starts = [(m.start(), m.group(1)) for m in
                re.finditer(r'item_templates\[[\'"]([^\'"]+)[\'"]\]\s*=\s*new\s+\w+',
                            _itemsjs)]
# Display names come from the hand-maintained itemNames dict in Script.txt.
# A name already in English (the base game's "Iron hammer head") IS its own
# display name, so it needs no lookup.
_iname_blk = _hdr.split('const itemNames = {')[1].split('\n    };')[0]
_item_en = {m.group(1).replace("\\'", "'"): m.group(2).replace("\\'", "'")
            for m in re.finditer(r"'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)',",
                                 _iname_blk)}

part_tiers, _tier_missing, _tier_parts = {}, [], 0
for _i, (_pos, _zh) in enumerate(_tier_starts):
    _end = _tier_starts[_i + 1][0] if _i + 1 < len(_tier_starts) else len(_itemsjs)
    _tm = re.search(r'component_tier:\s*(\d+)', _itemsjs[_pos:_end])
    if not _tm:
        continue
    _tier = int(_tm.group(1))
    _tier_parts += 1
    if cjk(_zh):
        _en = _item_en.get(_zh)
        if _en is None:
            _tier_missing.append(_zh)      # reported below; would show no prefix
            _en = None
    else:
        _en = _zh
    if _en:
        part_tiers[_en] = _tier
    # Keep the Chinese key too, so the prefix still works with ENABLE_PROSE off.
    part_tiers[_zh] = _tier

block.append("    // Component tier by DISPLAYED part name, for the crafting list prefix.")
block.append("    // Read from items.js component_tier, NOT from the tooltip: the game omits")
block.append("    // that line both for tier 0 and for every Armor-class part, and a missing")
block.append("    // line cannot distinguish the two. Chinese keys are kept alongside the")
block.append("    // English so this still works with ENABLE_PROSE off.")
block.append(dict_block('partTiers', part_tiers, numeric=True))
block.append("")

block.append("""    // Locations you can sleep at, by the CHINESE key the travel links carry
    // in data-travel. Generated from locations.js: a rest location is exactly
    // one whose definition has a `sleeping:` block, which is what
    // last_location_with_bed is tracking and what the game's own quick-return
    // link is coloured for.
    //
    // Sliced from one `new Location(` to the next rather than to the next
    // `locations[`: connected_locations reference other locations by
    // locations["..."] INSIDE a definition, and 纳可的房间 declares its
    // sleeping block after one of those - so a naive slice would drop it. The
    // build cross-checks the count against the raw number of sleeping blocks
    // in the file, so a definition growing one later cannot be missed
    // silently. Keyed by the Chinese, so it is independent of ENABLE_PROSE.""")
block.append("""    // Realm tier names as the family roster renders them, generated from
    // main.js realm_rate. Looked up by PREFIX (微尘级, 天空级 …) rather than by
    // whole realm name: almost no full name is a dictionary entry, they are
    // assembled tier-fragment + rank-fragment, and each tier fragment carries
    // a trailing space - which is exactly the space breakRealmNames() turns
    // into a line break.""")
block.append("    const REALM_TIERS = new Set([")
for _en in realm_tiers:
    block.append("        '%s'," % js(_en))
block.append("    ]);")
block.append("")
block.append("    const REST_LOCATIONS = new Set([")
for _zh in rest_locations:
    block.append("        '%s'," % js(_zh))
block.append("    ]);")
block.append("")
block.append("    // Travel labels that walk BACKWARD, so the arrow is mirrored. Generated")
block.append("    // from locations.js leave_text (backward by construction) plus a curated")
block.append("    // list of connected_location custom_text. NOT a prefix rule: 'Leave the")
block.append("    // village' and 'Leave the safe path' both go forward.")
block.append("    const BACKWARD_LABELS = new Set([")
for _en in sorted(backward_labels):
    block.append("        '%s'," % js(_en))
block.append("    ]);")
block.append("")
block.append("""    // ---- names the game reads back out of the DOM ----------------------
    // index.html's bestiary AND levelary hover handlers both do:
    //     let key = hovered_element.children[0].innerHTML;
    //     add_*_tooltip(key);
    // and those index bestiary_entry_divs{} / levelary_entry_divs{} by the
    // CHINESE name. Once we translate the visible name the key misses,
    // .appendChild throws, and no tooltip is ever built.
    //
    // A static map only covers enemies; floor names ("荒兽森林 - 1") are
    // produced by substring translation, so instead we stash each original
    // on the element before it gets translated and map back from that.
    // Both list types share the .bestiary_entry_div class, so this covers both.
    const domOriginals = new Map();   // translated text -> original Chinese

    // Both of these run every scan against a list that can hold 500+ rows, so
    // the :not(...) clauses matter: they push the "already handled" filtering
    // into the browser's selector engine, leaving these near-free once the
    // bestiary has been seen once.
    function captureOriginalNames() {
        // Runs at the START of scan(), while newly-added rows are still Chinese.
        document.querySelectorAll(
            '.bestiary_entry_div > :first-child:not([data-zh-original])'
        ).forEach((el) => {
            // The CJK test matters: if a row was added mid-scan we may only see
            // it after it was translated, and storing English as the "original"
            // would bake in a useless identity mapping. Skip it instead and let
            // the static bestiaryNames fallback handle it.
            if (CJK_RE.test(el.innerHTML)) el.dataset.zhOriginal = el.innerHTML;
        });
    }

    function indexOriginalNames() {
        // Runs at the END of scan(). Only rows captured but not yet indexed,
        // and only once the visible text actually differs from the original -
        // i.e. after translation has happened.
        document.querySelectorAll(
            '.bestiary_entry_div > [data-zh-original]:not([data-tl-indexed])'
        ).forEach((el) => {
            const orig = el.dataset.zhOriginal;
            if (el.innerHTML !== orig) {
                domOriginals.set(el.innerHTML, orig);
                el.dataset.tlIndexed = '1';
            }
        });
    }

    function toOriginalName(name) {
        return domOriginals.get(name) || bestiaryNames[name] || name;
    }

    // Patched lazily: the game assigns these when its module loads, which is
    // after this userscript runs at document-start.
    let namesPatched = false;
    function patchNameLookups() {
        if (namesPatched) return;
        if (typeof window.add_bestiary_tooltip !== 'function') return;
        ['add_bestiary_tooltip', 'clear_bestiary_tooltip',
         'add_levelary_tooltip', 'clear_levelary_tooltip'].forEach((fn) => {
            const orig = window[fn];
            if (typeof orig !== 'function') return;
            window[fn] = function (name) { return orig(toOriginalName(name)); };
        });
        namesPatched = true;
    }

    // ---- myriad numbers -------------------------------------------------
    // Chinese groups large numbers by 10^4, so format_number() emits things
    // like "276.47万" (2.7647e6) and "4.489垓" (4.489e20). display.js has an
    // option_format_change setting that switches to exponential, but it only
    // covers numbers that actually pass through format_number - anything the
    // game concatenates itself still comes out with a unit attached. Convert
    // here so it reads the same either way.
    // A digit is required before the unit, so item names keep their characters
    // (万载冰髓锭 "Age-Old Frostmarrow Ingot" is untouched).
    const MYRIAD = {
        '万': 4, '亿': 8, '兆': 12, '京': 16, '垓': 20, '秭': 24,
        '穣': 28, '沟': 32, '涧': 36, '正': 40, '载': 44, '极': 48,
    };
    const MYRIAD_RE = /(\\d+(?:\\.\\d+)?)\\s*([万亿兆京垓秭穣沟涧正载极])/g;
    // ENABLE_NUMBER_FORMAT lives in the TOGGLES block at the top.

    function formatMyriad(t) {
        if (!ENABLE_NUMBER_FORMAT) return t;
        return t.replace(MYRIAD_RE, (m, num, unit) => {
            let v = parseFloat(num);
            if (!isFinite(v) || v === 0) return m;
            let e = MYRIAD[unit];
            while (v >= 10) { v /= 10; e += 1; }
            while (v < 1) { v *= 10; e -= 1; }
            v = Math.round(v * 1000) / 1000;
            if (v >= 10) { v /= 10; e += 1; }   // rounding can tip 9.9996 -> 10
            return v + 'e' + e;
        });
    }

    // ENABLE_PROSE lives in the TOGGLES block at the top.

    // Ideographs PLUS the CJK punctuation we rewrite. The punctuation matters:
    // the game strands it in its own text node ("...减弱<span>10%</span>。"), and
    // such a node holds no ideograph at all, so an ideograph-only test rejected
    // it forever - that is why fullwidth 。 and ： survived in fully translated
    // bestiary tooltips. 【】 are deliberately NOT here: item names keep them.
    const CJK_RE = /[\\u4e00-\\u9fff。，：；！？、（）]/;
    // Ideographs only. CJK_RE also matches punctuation, which must NOT count
    // as 'still Chinese' when deciding whether a regex fully resolved a node.
    const IDEO_RE = /[\\u4e00-\\u9fff]/;

    // ...and neither do MYRIAD UNITS. format_number emits "972万", which stage 4
    // (formatMyriad) turns into 9.72e6 - so a 万 left in the text is pending
    // work, not untranslated Chinese. Counting it as Chinese made
    // regexMustComplete reject the milestone rule for every LARGE value while
    // accepting it for small ones, so "基础Attack,Defense,Agility + 9.72e6"
    // survived v9.1: the fix was real, but only tested with "+ 8000".
    function residualChinese(t) {
        return IDEO_RE.test(t.replace(MYRIAD_RE, '$1'));
    }

    // The screen is a fixed set of panels. Translating per-panel (rather than
    // walking the document) means a change in one panel never costs anything
    // in the others - combat churns #combat_div and #message_log_div, and
    // nothing else needs re-examining.
    const PANEL_IDS = [
        'basic_character_info_div', 'time_and_location', 'inventory_div',
        'character_combat_management', 'inventory_combat_switch_selection',
        'location_div', 'combat_div', 'location_related_div',
        'skills_and_stances_div', 'engine_div', 'journal_div',
        'character_div', 'message_log_div', 'bottom_panel_div',
        'options_panel',
        // Floating tooltips that live outside the panel boxes - without these
        // the per-panel walk never reaches them at all.
        'effects_tooltip', 'gathering_tooltip',
    ];
    const PANEL_SET = new Set(PANEL_IDS);
    const PANEL_SELECTOR = PANEL_IDS.map((id) => '#' + id).join(',');

    // Which panels changed since the last pass. Starts "all" so the first scan
    // covers everything; afterwards the MutationObserver narrows it down.
    const dirtyPanels = new Set();
    let proseAllDirty = true;

    function markProseDirty(records) {
        for (let i = 0; i < records.length; i++) {
            const t = records[i].target;
            const el = t.nodeType === 1 ? t : t.parentElement;
            const panel = el && el.closest ? el.closest(PANEL_SELECTOR) : null;
            if (panel) {
                dirtyPanels.add(panel.id);
            } else {
                // something moved outside the known panels - be safe
                proseAllDirty = true;
                return;
            }
        }
    }

    // allowFrags=false runs only the precise stages (whole-node exact match and
    // whole-node template regexes) and skips substring replacement. Fragments
    // are a LAST RESORT: they must never pre-empt a more specific matcher. Used
    // for containers whose v4.0 pair list does legitimate full-phrase matching,
    // where an early 技能 -> "Skills" would stop 秘法 技能 -> "Technique Skills"
    // from ever matching.
    // allowRegex=false also skips the template regexes. They can half-translate:
    // "${category} 技能" -> "${category} Skills" turns 秘法 技能 into "秘法 Skills",
    // inserting the untranslated category as $1 and blocking the v4.0 pair that
    // would have rendered the whole phrase as "Technique Skills".
    function applyProse(root, allowFrags, allowRegex, regexMustComplete) {
        if (!ENABLE_PROSE) return;
        if (allowFrags === undefined) allowFrags = true;
        if (allowRegex === undefined) allowRegex = true;
        // Plain SHOW_TEXT and no filter callback on purpose: a NodeFilter runs
        // JS for every node the walker considers, which costs more than the
        // work it saves.
        const walker = document.createTreeWalker(
            root || document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const original = node.textContent;
            // Cheapest possible rejection, before anything allocates. Almost
            // every node on screen is already English or a bare number, and
            // every key we could match contains Chinese - so this one test
            // retires the common case without a .trim() or a dict lookup.
            if (!CJK_RE.test(original)) continue;
            const trimmed = original.trim();
            if (!trimmed) continue;
            // Fast path: the whole node is one translated string.
            const hit = proseExact[trimmed];
            if (hit) { node.textContent = original.replace(trimmed, hit); continue; }
            // The game glues a separator onto the front of some descriptions
            // ("<b>2-Hit Combo</b> ：敌人进攻速度很快…"), so the node is our key
            // plus a prefix. Retry once with the separator peeled off; replacing
            // only the core keeps the prefix in place.
            // Also strip wrapper quotes: display.js renders every dialogue
            // option as `"${textline.name}"`, so the node is our key inside a
            // pair of quotes and never matches on its own.
            const core = trimmed
                .replace(/^["\\u201c\\u201d'：:、，,．\\-\\u2013\\u2014\\s]+/, '')
                .replace(/["\\u201c\\u201d'\\s]+$/, '');
            if (core && core !== trimmed) {
                const hit2 = proseExact[core];
                if (hit2) { node.textContent = original.replace(core, hit2); continue; }
            }
            let text = trimmed;

            // 2) Interpolated templates, matched against the whole node so the
            //    English word order is preserved. The hint is a plain indexOf
            //    pre-filter so we don't run every pattern against every node.
            // Dialogue options are rendered as `"${name}"` (display.js builds
            // textline_div.innerHTML with literal quotes around the name), and
            // every template regex is anchored ^...$ - so the quotes alone stop
            // them matching. That silently disabled "和 X 对话" -> "Talk with X"
            // for EVERY dialogue option in the game, and "使用 [X]" -> "Use [X]".
            // Strip only the QUOTES here and re-attach them after; the wider
            // separator set used for the exact lookup must not be stripped,
            // because a leading ：or ，has to survive into the fragment stage
            // that converts it.
            const qm = text.match(/^(["\u201c\u201d']+)([\s\S]*)(["\u201c\u201d']+)$/);
            const qPre = qm ? qm[1] : '';
            const qPost = qm ? qm[3] : '';
            let rxText = qm ? qm[2] : text;
            for (let i = 0; allowRegex && i < proseRegex.length; i++) {
                const rule = proseRegex[i];
                if (rxText.indexOf(rule[2]) === -1) continue;
                const next = rxText.replace(rule[0], rule[1]);
                if (next !== rxText) {
                    // In the early precise pass, only take a rule that FULLY
                    // resolves the node. One that leaves Chinese behind (an
                    // untranslated $1) would block the v4.0 pair that could
                    // have rendered the whole phrase - the "秘法 技能" ->
                    // "秘法 Skills" failure. When it does fully resolve, going
                    // early is what saves it from #skill_list's statPairs,
                    // whose ['攻击','Attack'] fires before our per-panel pass
                    // and left "基础Attack,Defense,Agility + 8000" in a tooltip.
                    if (regexMustComplete && residualChinese(next)) continue;
                    rxText = next;
                    break;
                }
            }
            text = qPre + rxText + qPost;

            // 3) Curated substrings (combat log, place and enemy names) on
            //    whatever Chinese is still left. Skipped when the caller asked
            //    for precise matching only.
            if (allowFrags && CJK_RE.test(text)) {
                // No capture groups in proseFragRe, so the callback args are
                // (match, offset, wholeString).
                text = text.replace(proseFragRe, (m, offset, str) => {
                    let out = proseFrag[m];
                    if (out === undefined) return m;
                    // Chinese runs words together, so these replacements carry
                    // their own spaces. Drop one where the source already had a
                    // space, or "X 受到了 N" comes out as "X  took  N".
                    if (out.charAt(0) === ' ' && offset > 0
                            && str.charAt(offset - 1) === ' ') {
                        out = out.slice(1);
                    }
                    if (out.charAt(out.length - 1) === ' '
                            && str.charAt(offset + m.length) === ' ') {
                        out = out.slice(0, -1);
                    }
                    return out;
                });
            }

            // 4) Myriad-grouped numbers -> exponential ("276.47万" -> 2.7647e6).
            text = formatMyriad(text);

            if (text !== trimmed) node.textContent = original.replace(trimmed, text);
        }
    }

    // Containers that must be translated BEFORE the buttons pass. Their v4.0
    // pair lists contain deliberately broad rewrites - #message_box_div turns
    // ，into ", " and 获取了 into "Gained ", #location_actions_div turns 到 into
    // "to" (which is what produced "回to营地") - and those shred the longer,
    // more specific prose entries before they get a chance to match.
    // Scoped on purpose: running applyProse globally this early would translate
    // shared fragments like 技能 and break "行动 技能" -> "Activity Skills".
    // Containers whose v4.0 pass would otherwise rewrite the text before the
    // (longer, more specific) prose entries get a chance to match. skill_list
    // is here because applyItemNames' bracket rule turns "增加[水无心]系秘法的
    // 使用效果" into "增加[Water Heartless]系秘法…", after which the full-sentence
    // key can never match and the rest of the line stays Chinese.
    // Early pass, FULL (fragments included). Their v4.0 pair lists do broad,
    // destructive rewriting - #message_box_div turns ，into ", " and 获取 into
    // "Obtained:", #location_actions_div turns 到 into "to" - which shreds our
    // longer entries. We must get in first.
    const EARLY_PROSE_FULL = ['location_actions_div', 'location_name_div'];

    // Early pass, PRECISE ONLY (no fragments). #skill_list's pair list does
    // legitimate full-phrase matching (秘法 技能, 传统且高贵的剑术技能), so we take
    // the whole-sentence matches we can prove, then leave the text intact for
    // it. applyItemNames also brackets names here, which is why we can't simply
    // wait until after.
    // bottom_panel_div is here for the save/export row: v4.0's
    // #save_to_file_button pair rewrites 导出 -> "Export" in the buttons loop,
    // which would leave our whole-node key 导出(奖励) unable to match.
    // stance_list_div for the same reason, and it is worth spelling out because
    // it is the third instance of one bug. applySelector applies EVERY pair in
    // a list, IN ORDER, so a short key placed before a long one destroys the
    // long one. #stance_list_div lists the stance NAMES before the descriptions
    // that quote them, so 映星花·巨星 fired inside
    //     强大的单体攻击秘法。0级状态即为【映星花·巨星】的极限。
    // the whole-sentence pair could no longer match, and the prose fragment
    // stage then chewed what was left into "强大的单体Attack秘法.". Taking the
    // exact match first leaves the short name pairs the labels they are for.
    // uitest_order.js now enforces that every such shadowed pair sits in a
    // selector one of these early passes covers.
    const EARLY_PROSE_EXACT = ['skill_list', 'bottom_panel_div', 'stance_list_div'];

    // Same idea, but class-based: .item_tooltip / .recipe_tooltip carry
    // statPairs, so 攻击 -> "Attack" fires inside an item DESCRIPTION and breaks
    // the whole-sentence key. Take the exact match first, then let the pairs
    // have the (still intact) stat lines.
    //
    // Deliberately NOT filtered with :not([data-tl-e]). Recipe tooltips are
    // regenerated in place as material counts tick over, so a "done" marker
    // survives while the content resets to Chinese - and the element would then
    // be skipped forever. applyProse already rejects non-Chinese nodes on the
    // first test, so re-visiting a clean tooltip costs almost nothing.
    // .stat_tooltip for the same reason, found the same way. Its OWN pair list
    // ends with short terms - ['宝石', 'Gems'], ['境界', 'Realm'] - and the list
    // is applied in order, so any sentence not spelled out earlier in that list
    // gets eaten piecemeal. The SCGV description is not in it, so
    //     宝石耐性，全称宝石软上限起始点倍率(SoftCappedGemValue)
    // became "Gems耐性，全称Gems软上限起始点倍率(…)", at which point its exact
    // entry - which exists and is correct - could no longer match, and the
    // fragment stage layered 倍率 -> "multiplier" on top of the wreckage.
    // Taking the exact match first leaves the short pairs the stat lines they
    // are actually for.
    const EARLY_PROSE_EXACT_SEL = '.item_tooltip, .recipe_tooltip, .stat_tooltip';

    // The message log grows without bound, so re-walking all of it on every
    // scan gets steadily more expensive over a session. Entries are
    // append-only and never change once written, so walk back from the newest
    // and stop at the first one already handled: the cost then tracks how many
    // NEW messages arrived, not how long the log is.
    function translateMessageLog() {
        const box = document.getElementById('message_box_div');
        if (!box) return;
        const kids = box.children;
        for (let i = kids.length - 1; i >= 0; i--) {
            const el = kids[i];
            if (el.dataset.tlDone) break;
            applyProse(el);
            el.dataset.tlDone = '1';
        }
    }

    // Decorative diagonal banner in the fishing minigame ("a girl is
    // fishing..."). The <br>s split it into ONE TEXT NODE PER GLYPH, and single
    // characters must never be fragments (see 峰 -> "Peak"), so no matcher can
    // legally reach it. It is static markup that no game code ever rewrites, so
    // replace the whole thing once. Indents are &emsp; (= 1em = 30px here);
    // "fishing" at three of them is ~195px inside a 250px box.
    const FISH_FONT_HTML =
        'A<br><br>&emsp; girl<br><br>&emsp; &emsp; is<br><br>' +
        '&emsp; &emsp; &emsp; fishing<br><br>&emsp; &emsp; &emsp; &emsp; ...';

    function translateFishFont() {
        const el = document.getElementById('fish_font_div');
        if (!el || el.dataset.tlDone) return;
        if (!/[一-鿿]/.test(el.textContent)) return;
        el.innerHTML = FISH_FONT_HTML;
        el.dataset.tlDone = '1';
    }

    // HIGH PRIORITY: elements the game rewrites on a timer rather than in
    // response to the player. The 100ms scan throttle is invisible for text
    // that changes when you click something, but these are rebuilt every frame
    // (main.js drives the reactor readout at frametime 0.03), so between scans
    // they sit in Chinese and visibly flicker mid-sentence.
    //
    // Few and tiny, so translate them on EVERY mutation batch instead of
    // waiting for the throttled scan. Cost stays near zero once translated:
    // applyProse rejects a node on the CJK test before allocating anything, so
    // an already-English readout is one regex test per node. Safe to run this
    // often because the observer watches childList only - our own textContent
    // writes do not re-trigger it.
    const HOT_IDS = [
        'character_rank_div',       // 燕岗领排名: N
        'time_div',                 // 31698纪元 1380年 19日 052:06
        // The whole phase-change engine panel: the game rewrites its readouts
        // on a timer, so every one of them flickered. Covers what used to be
        // listed here as container_element_time (the ETA) plus its siblings.
        // Affordable despite being a whole panel: ~33 text nodes, mostly digits,
        // and applyProse rejects a node on the CJK test before allocating.
        'engine_div',
        'B1_core_diff',             // 消耗:N/s 临界度:M%
        'A7_core_diff',             // 消耗:N/s
        // Bottom bar. display.js rewrites #save_to_file_button on the same tick
        // as the clock, flipping it between 导出 and 导出(奖励) once an hour of
        // real time has passed - so it flickered like the reactor readouts.
        // Only 8 text nodes (options_panel is a SIBLING, not a child).
        //
        // Full stages here, even though bottom_panel_div is in
        // EARLY_PROSE_EXACT: 导出 is a FRAGMENT, not an exact entry, so an
        // exact-only pass would leave the common state in Chinese and fix
        // nothing. Checked every string in the bar first - each either fully
        // resolves through our layer (导出, 静音, 在战败时回到床上, the help
        // line) or is left completely untouched for v4.0 (保存, 导入). Nothing
        // is half-translated, which is what EARLY_PROSE_EXACT guards against.
        'bottom_panel_div',
        // Family panel. update_displayed_family() reassigns innerHTML on these
        // three every tick, which destroys and rebuilds the text node even when
        // the string has not changed - so the translation was thrown away and
        // re-applied on every scan, and the warning flickered.
        //
        // These three specifically, NOT #family_system: the roster table is a
        // child of it and can reach ~37 rows x 9 nodes, which would be ~330
        // nodes walked on every mutation batch in the game.
        // The roster IS handled off-throttle now, but in translateHot() behind
        // a visibility test rather than here - see the note there. It had to
        // be: its Chinese frame is taller than the English one, so leaving it
        // to the throttled pass moved the scrollbar under the player.
        // V3.44's family unlock readout, five spans rewritten by
        // update_displayed_family() on every tick like the ones below.
        // family_next_realm carries a Chinese realm name inside a coloured
        // span; the other four are numbers, but format_number emits 万/亿
        // suffixes, which are CJK and so are formatMyriad's business. Left on
        // this list rather than folded into the roster branch: they are five
        // tiny spans, where that branch walks ~330 nodes and is gated on the
        // tab being visible for exactly that reason.
        'family_next_realm',
        'family_cur_power',
        'family_next_power',
        'family_cur_rank',
        'family_next_rank',
        'baby_scale1',              // 新生儿超过1万，花费受到一重软上限限制(^1.5)
        'baby_scale2',              // …1亿…二重…(^1.75)
        'baby_scale3',              // …1兆…三重…(^2.0)
        // 境界 : 天空级一阶. Rewritten only `if(did_level)`, which LOOKS rare -
        // and is, until you hit an XP cap. At the cap character.add_xp() returns
        // the bottleneck string instead of nothing, so add_xp_to_character
        // passes that truthy value straight into
        // update_displayed_character_xp(level_up) as did_level, and the realm
        // line is rewritten on every XP tick. Same root cause as the bottleneck
        // message spam: capped play turns a level-up path into a per-tick path.
        'character_level_div',
    ];
    // NB: temp_diff / rad_diff / *_core_num are rewritten just as often but
    // hold only digits and symbols, so they are deliberately NOT here - this
    // list runs on every mutation batch and should stay as short as the job
    // requires. Add an id only after checking its writer emits Chinese.

    // Class-based hot entries, for text with no id of its own.
    //
    // .skill_bar_name is rewritten by update_displayed_skill_bar() as
    //     `${skill.name()} : level ${cur}/${max}`
    // on every skill XP update - i.e. continuously during any activity - so the
    // Chinese name reappeared between scans and flashed.
    //
    // Narrow ON PURPOSE. Putting '#skill_list' in HOT_IDS instead would be the
    // obvious move and would be wrong: translateHot runs FULL applyProse, and
    // the template regex `^(.+?)\\ 技能$` half-translates the category headers -
    // 秘法 技能 becomes "秘法 Skills", inserting the untranslated category and
    // blocking the v4.0 pair that renders the whole phrase as "Technique
    // Skills". That is why #skill_list is in EARLY_PROSE_EXACT (exact only) and
    // not here. A skill bar NAME carries no such template, so it is safe alone.
    // .skill_bar_max:hover .skill_tooltip - the OPEN skill tooltip.
    //
    // update_displayed_skill_bar() rewrites its XP line, milestone line and
    // effect description on every tick, so hovering a skill that is gaining XP
    // showed those flicking back to Chinese between scans.
    //
    // Scoped through :hover on purpose. There are ~111 skill tooltips in the
    // DOM and each holds a dozen text nodes, so walking them all every mutation
    // batch would cost more than the whole rest of this list put together; the
    // hover chain narrows it to the single one on screen, matched natively with
    // no layout or style flush - far cheaper than testing display on each.
    // getComputedStyle() or offsetParent would be the WRONG gate: both still
    // visit all 111 and force a flush on top.
    //
    // The parent class is not optional. ':hover .skill_tooltip' alone matches
    // EVERY skill tooltip, because <body> is always in the hover chain and they
    // all descend from it. uitest_order.js enforces that.
    //
    // 已满级 is deliberately not chased here: it is v4.0-only, and it is written
    // once when a skill maxes and never rewritten (a maxed skill gains no XP),
    // so it cannot stutter and the throttled pass is enough for it.
    const HOT_TOOLTIP_SEL = '.skill_bar_max:hover .skill_tooltip';
    const HOT_SEL = '.skill_bar_name, ' + HOT_TOOLTIP_SEL;
    // Named once, because it is both a key into `buttons` and the selector
    // applySelector queries with - if those two ever drift apart the lookup
    // returns undefined and the hot pass silently does nothing.
    const ENEMY_STAT_SEL = '.enemy_stat';

    function translateHot() {
        // The enemy stat lines, but ONLY while the combat panel is open.
        //
        // display.js rewrites all five per enemy with innerHTML on every combat
        // tick, so between throttled scans they sit in Chinese and the row
        // flickers between languages at attack speed. Same problem HOT_IDS
        // exists for - but these belong to the v4.0 SELECTOR pass, not the
        // prose layer, so they need their own call and it has to sit ABOVE the
        // ENABLE_PROSE guard: turning the prose layer off must not silently
        // take the stat labels with it, since the throttled pass would still
        // translate them.
        //
        // applySelector is the same code the scan runs, on the same pair list,
        // so there is no second definition of what these words mean. The
        // visibility test is a plain inline-style read - display.js sets
        // combat_div.style.display directly - so it forces no layout, and out
        // of combat this whole branch is one property read.
        if (HOT_ENEMY_STATS) {
            const combatDiv = document.getElementById('combat_div');
            if (combatDiv && combatDiv.style.display !== 'none') {
                applySelector(ENEMY_STAT_SEL, buttons[ENEMY_STAT_SEL]);
            }
        }
        if (!ENABLE_PROSE) return;
        for (let i = 0; i < HOT_IDS.length; i++) {
            const el = document.getElementById(HOT_IDS[i]);
            if (el) applyProse(el);
        }
        const hot = document.querySelectorAll(HOT_SEL);
        for (let i = 0; i < hot.length; i++) applyProse(hot[i]);
        // The open tooltip's XP line is rewritten every tick by
        // update_displayed_skill_xp_gain(), so its scientific annotation has to
        // be restored in the same batch as the translation - not one throttled
        // scan later, or the suffix flickers by itself. Scoped to that one
        // tooltip: the unhovered ~110 are only decoration and can wait.
        const openTip = document.querySelector(HOT_TOOLTIP_SEL);
        if (openTip) annotateXpGain(openTip);
        // The family roster, but ONLY while its tab is open.
        //
        // update_displayed_family_members() empties the table and rebuilds it
        // in Chinese once per game day. That Chinese frame is TALLER than the
        // finished English one - the rows wrap to three lines where ours take
        // two - so when the throttled pass translated it a moment later the
        // content shrank underneath the scrollbar and the view jumped.
        //
        // Translating here removes that frame at the source: a MutationObserver
        // callback runs before the browser paints, so the taller rendering is
        // never laid out and never seen. (A second, smaller drift survives that
        // and is handled separately - see restoreFamilyScroll below.)
        //
        // The visibility test is what makes this affordable. The roster runs to
        // ~37 rows of 9 cells, far too much to walk on every mutation batch in
        // the game - which is why HOT_IDS deliberately carries only the three
        // baby_scale spans. showFamily() sets display as an INLINE style, so
        // this is a plain property read with no style flush, and the ~330 nodes
        // are only walked while the player is actually looking at them.
        const famDiv = document.getElementById('family_div');
        if (famDiv && famDiv.style.display !== 'none') {
            const famList = document.getElementById('family_member_list');
            if (famList) {
                watchFamilyScroll(famDiv);
                // NB: breakRealmNames() below runs in this same batch, after
                // applyProse - it adds a line to most rows, and doing that one
                // frame later would change the table's height under the
                // scrollbar, which is the fault the whole branch exists to
                // avoid.
                // Did the roster just get rebuilt? The rebuild replaces every
                // <tr>, so the header row is a DIFFERENT NODE than the one we
                // translated last time. Node identity, not a measurement: no
                // layout is forced, and the batches in between cost one
                // property read. famHeadRow starts null so the first sighting
                // of the table is never mistaken for a rebuild.
                const head = famList.firstElementChild;
                const rebuilt = famHeadRow !== null && head !== famHeadRow;
                famHeadRow = head;
                applyProse(famList);
                breakRealmNames();
                if (rebuilt) restoreFamilyScroll(famDiv);
            }
        }
        // The location actions, but ONLY when they have just been rebuilt.
        //
        // change_location() replaces this whole panel, so on the throttled
        // pass the player saw a frame of Chinese options and then the bar
        // appearing under their cursor a tick later - on the one panel where
        // they are about to click something.
        //
        // The gate is node identity of the first child, not a timer and not a
        // measurement: clear_action_div() removes every element child, so a
        // rebuild leaves a different node there. Between rebuilds this costs
        // one property read per batch. The anchor is re-read AFTER the passes
        // because addActionBar() inserts the bar as the new first child.
        //
        // The whole pipeline runs here, not just applyProse: the bar CLONES
        // the rows' icons, so the mirrored return arrow and the rest tint have
        // to be on them already. Splitting it would freeze a bar built from
        // un-mirrored, un-tinted icons, since addActionBar early-returns once
        // the bar exists and would never revisit it.
        const actHost = document.getElementById('location_actions_div');
        if (actHost && actHost.firstElementChild !== actionBarAnchor) {
            applyProse(actHost);
            mirrorReturnIcons();
            nbspLocationNames();
            colorRestTravel();
            addActionBar();
            actionBarAnchor = actHost.firstElementChild;
        }
        // Re-compact in the SAME batch that translated the name. Restoring only
        // the name here left the bar flickering between two renderings rather
        // than between two languages: the game rewrites
        //     "Name : level 4/4" + "Max!"
        // and the compacted form is "Name" + "4/4", so a maxed bar whose skill
        // is gaining XP every tick - the equipped technique's skill and the
        // active stance's skill, which is exactly where it showed - was
        // un-compacted on every tick and only put back on the next throttled
        // scan. Its own toggles still gate it; this is only about WHEN it runs.
        compactMaxedSkillBars();
    }

    // ---- the family roster's scroll position across the daily rebuild ------
    //
    // v13.9 killed the Chinese frame and the view STILL crept one row upward
    // per rebuild, so the height difference was never the whole story. What is
    // left is the rebuild itself: update_displayed_family_members() empties the
    // table and recreates every <tr>, which destroys whichever node the browser
    // had picked as its scroll anchor, and an anchor that no longer exists
    // cannot be compensated for. The function is not on window (display.js
    // exports update_displayed_family and only that), so it cannot be wrapped
    // and the rebuild cannot be made non-destructive from out here. Put the
    // offset back instead.
    //
    // This is the "papering over it with scroll-position restoration" that the
    // v13.9 note talked down. That reasoning was right about the Chinese frame
    // and removing it at source was the correct fix; it simply does not reach
    // anchor destruction, which is a different problem in the same place.
    //
    // Not to be confused with the v14.0 experiment: overflow-anchor:none turns
    // anchoring OFF globally for the panel and made things worse, because
    // anchoring is also absorbing a per-second height change in the header
    // block above the table. Anchoring stays on. This only overrides the one
    // frame where it cannot do its job.
    let famHeadRow = null;      // the <tr> we translated last time
    let famScrollTop = -1;      // last known offset; -1 = never scrolled
    let famScrollBound = false;

    // The scroll event is the only place scrollTop can be read for free.
    // Everywhere else it forces a synchronous layout, and translateHot runs on
    // every mutation batch - the hot path is deliberately free of layout-
    // forcing reads, which uitest_order.js enforces. Bound lazily and once, off
    // the same visibility test that gates the roster, so a player who never
    // opens the tab never gets the listener at all.
    function watchFamilyScroll(famDiv) {
        if (famScrollBound || !FAMILY_SCROLL_RESTORE) return;
        famScrollBound = true;
        famDiv.addEventListener('scroll', () => {
            famScrollTop = famDiv.scrollTop;
        }, { passive: true });
    }

    // WRITING the offset, not reading it and deciding. A write flushes layout
    // and then sets the position, so whatever adjustment the browser was about
    // to make this frame is overwritten by ours - whereas a read would hand us
    // the value AFTER that adjustment, which is the number we are trying to
    // throw away. One forced layout per game day, with the tab open, and none
    // at all otherwise.
    //
    // The write itself fires a scroll event, so famScrollTop re-caches to
    // whatever the browser settled on. That is what keeps the drift from
    // accumulating if a rebuild ever outruns us: each restore is measured from
    // the last known-good position rather than from a running total.
    function restoreFamilyScroll(famDiv) {
        if (!FAMILY_SCROLL_RESTORE || famScrollTop <= 0) return;
        let found = 0, wasTall = 0;
        if (FAMILY_SCROLL_DEBUG) {
            found = famDiv.scrollTop;
            wasTall = famDiv.scrollHeight;
        }
        famDiv.scrollTop = famScrollTop;
        if (FAMILY_SCROLL_DEBUG) {
            console.log('[NekoRPG TL] family rebuild: wanted ' + famScrollTop +
                        ', found ' + found + ', settled at ' + famDiv.scrollTop +
                        ' (scrollHeight ' + wasTall + ' -> ' + famDiv.scrollHeight + ')');
        }
    }

    // Maxed skill bars waste their width. The game renders
    //     .skill_bar_name = `${skill.name()} : level 3/3`
    //     .skill_bar_xp   = `Max!`
    // and an English name is far longer than the Chinese it replaced, so the
    // name wraps onto a second line and the bar grows. Compact it:
    //   - drop " : level 3/3" from the name (the numbers move right)
    //   - put "3/3" in the Max! slot, which already says the same thing
    //   - join the name with NBSP so it stays on one line
    //
    // NBSP via textContent, not an &nbsp; entity via innerHTML: identical
    // rendering, and no escaping question for names containing [ ] or ·.
    //
    // Maxedness is read from the NAME (cur === max), not from "Max!", so this
    // still works on a bar we already rewrote. Runs after the prose pass, so
    // the name is English by the time we touch it; the game rewrites both
    // fields on every skill update, and the next scan simply redoes this.
    const MAXED_RE = /^([\s\S]*?)\s*:\s*level\s*(\S+)\/(\S+)\s*$/;

    // All 37 回到/返回 travel labels translate to "Return to …", so the label is
    // a reliable signal even though the markup is not.
    // \\b, not \b: this block is a PYTHON string, so escapes are consumed once
    // here and once by JS. A bare \b emits a literal backspace (0x08) and the
    // word boundary silently disappears - which is exactly what happened first
    // time round, and nothing matched.
    // Deliberately NOT (?:quick\\s+)?return: "Quick Return" is a jump, handled
    // by JUMP_LABEL_RE below, and must not fall into the backward group.
    const RETURN_LABEL_RE = /^return\\b/i;

    // Jumps: neither forward nor back. Both teleport you to a REMEMBERED place
    // rather than stepping one level through the map - Fast Travel between
    // acts, Quick Return to the last bed or the last combat zone. They keep the
    // game's own signpost and are never mirrored, because a signpost is exactly
    // what "pick a remembered destination" looks like.
    const JUMP_LABEL_RE = /^(?:fast\\s+travel|quick\\s+return)\\b/i;

    function mirrorReturnIcons() {
        if (!ENABLE_VISUAL_OVERRIDES) return;
        if (!MIRROR_RETURN_ICONS && !REPLACE_TRAVEL_ICON) return;
        const opts = document.querySelectorAll('.action_travel');
        for (let i = 0; i < opts.length; i++) {
            const icon = opts[i].querySelector('.material-icons');
            if (!icon) continue;
            // The label is the text node right after the glyph, in both
            // shapes the game builds (bare <i>…</i> text, and <span><i>…</i>
            // text</span>). Reading opts[i].textContent instead would include
            // the glyph NAME ("directions") and never match.
            const after = icon.nextSibling;
            const label = after ? (after.textContent || '').trim() : '';
            const isJump = JUMP_LABEL_RE.test(label);
            // Swap the signpost for an arrow. Two exceptions, both deliberate:
            // the combat options use 'warning_amber', a hazard marker rather
            // than a direction; and a jump is a destination menu, which is what
            // a signpost actually depicts.
            if (REPLACE_TRAVEL_ICON && TRAVEL_ICON && !isJump &&
                icon.textContent.trim() === 'directions') {
                icon.textContent = TRAVEL_ICON;
            }
            if (!MIRROR_RETURN_ICONS) continue;
            if (!isJump &&
                (RETURN_LABEL_RE.test(label) || BACKWARD_LABELS.has(label))) {
                // transform needs a block box; <i> is inline by default
                icon.style.display = 'inline-block';
                icon.style.transform = 'scaleX(-1)';
            } else if (icon.style.transform) {
                icon.style.transform = '';
            }
        }
    }

    function compactMaxedSkillBars() {
        if (!ENABLE_VISUAL_OVERRIDES) return;
        if (!COMPACT_MAXED_SKILL_BARS && !MAXED_BAR_HIGHLIGHT) return;
        const bars = document.querySelectorAll('.skill_bar_max');
        for (let i = 0; i < bars.length; i++) {
            const bar = bars[i];
            const text = bar.firstElementChild;          // .skill_bar_text
            if (!text) continue;
            const nameEl = text.children[0];
            const xpEl = text.children[1];
            if (!nameEl || !xpEl) continue;
            const m = MAXED_RE.exec(nameEl.textContent);
            if (!m || m[2] !== m[3]) continue;      // not maxed - leave alone
            if (COMPACT_MAXED_SKILL_BARS) {
                nameEl.textContent = m[1].replace(/ /g, '\u00a0');
                xpEl.textContent = m[2] + '/' + m[3];
            }
            if (MAXED_BAR_HIGHLIGHT) {
                // Inline styles, not a CSS rule: .skill_bar_max is shared by
                // every skill, so only the elements we have proven maxed may
                // be painted. Re-applying the same values is a no-op, which is
                // what keeps this safe to run on every scan.
                bar.style.backgroundColor = MAXED_BAR_BG;
                bar.style.borderColor = MAXED_BAR_BORDER;
                const fill = bar.querySelector('.skill_bar_current');
                if (fill) fill.style.height = '0px';
            }
        }
    }

    // #location_name_div is 250px and the name inside it wraps on any space, so
    // "Illusory Realm Core · Barrier Lake" could break as "…· Barrier" / "Lake".
    // Join the WHOLE name with NBSP so it stays on one line - separators
    // included, so it cannot break at the · or at the - in "Wildbeast Forest
    // - 1" either.
    //
    // A name wider than the box therefore overflows instead of wrapping.
    // #time_and_location sets 20px, so the longest name in the game ("Hunting
    // Tournament · Ancient Tomb Battle", 41 chars) runs to ~410px and reaches
    // past #location_types_div at left:292px. That is the accepted trade for
    // never breaking a name; nothing here resizes or clips it.
    function nbspLocationNames() {
        if (!ENABLE_VISUAL_OVERRIDES || !NBSP_LOCATION_NAMES) return;
        const el = document.getElementById('location_name_span');
        if (!el) return;
        const raw = el.textContent;
        if (!raw || raw.indexOf(' ') === -1) return;   // nothing to join
        // Re-runs on every scan: the game rewrites this on each location change,
        // and joining an already-joined name is a no-op.
        const joined = raw.replace(/ /g, '\\u00a0');
        if (joined !== raw) el.textContent = joined;
    }

    // The bestiary list mixes two kinds of row: enemies (a name and a kill
    // count) and ZONES, which display.js builds as
    //     <b><div onclick="change_location(…)">【Name】</div></b>
    // with the act number where the kill count would be. The zone rows are
    // clickable fast-travel links and look identical to the enemy rows they are
    // buried among, so they get a colour. The onclick div IS the signal - it is
    // what makes the row a link - so nothing here has to guess from the text.
    // Marks every zone row, and optionally colours it. Marking is NOT gated on
    // HIGHLIGHT_BESTIARY_LINKS: the Zones tab filters on that same marker, so
    // turning the colour off must not also empty the tab.
    const ZONE_ROW_CLASS = 'tl_zone_row';

    function highlightBestiaryLinks() {
        if (!ENABLE_VISUAL_OVERRIDES) return;
        if (!HIGHLIGHT_BESTIARY_LINKS && !ZONES_TAB) return;
        const rows = document.querySelectorAll('.bestiary_entry_div');
        for (let i = 0; i < rows.length; i++) {
            const name = rows[i].querySelector('.bestiary_entry_name');
            if (!name) continue;
            const link = name.querySelector('div[onclick]');
            if (!link) continue;                       // an enemy row; leave it
            // The onclick div IS the signal - it is what makes the row a
            // teleport link - so nothing here has to guess from the text.
            rows[i].classList.add(ZONE_ROW_CLASS);
            if (!HIGHLIGHT_BESTIARY_LINKS) continue;
            const color = bestiaryActColor(rows[i]);
            // Inline styles on the two cells only. Re-applying the same value
            // is a no-op, which is what makes this safe on every scan.
            link.style.color = color;
            link.style.cursor = 'pointer';
            const zone = rows[i].querySelector('.bestiary_entry_kill_count');
            if (zone) zone.style.color = color;
        }
    }

    // Which act a zone row belongs to, as a colour.
    //
    // Read from data-bestiary, which display.js sets to -100*(zone+1) for a
    // zone row - so -4200 is zone 41, and the act is the tens digit, 4. That is
    // structural: the alternative is parsing "Zone 4 - 1" out of the kill-count
    // cell, which is TRANSLATED text and would break with ENABLE_PROSE off.
    //
    // Enemy rows use -rank and never reach here (they have no onclick div), but
    // the multiple-of-100 test is kept as cheap insurance since the two key
    // spaces genuinely overlap - enemy ranks run to 4499, zone keys to -6900.
    function bestiaryActColor(row) {
        const raw = parseInt(row.getAttribute('data-bestiary'), 10);
        if (raw < 0 && raw % 100 === 0) {
            const act = Math.floor(((-raw / 100) - 1) / 10);
            if (BESTIARY_ACT_COLORS[act - 1]) return BESTIARY_ACT_COLORS[act - 1];
        }
        return BESTIARY_LINK_COLOR;
    }

    // The skill tooltip prints the XP multiplier as a plain decimal:
    //     XP Gain: x1704855.1
    // display.js builds it as Math.round(100*mult)/100, so it never picks up a
    // myriad unit and the number layer never sees it - past a few digits it is
    // unreadable at a glance. Append the scientific form rather than replacing
    // it: the exact figure still matters when comparing two skills.
    //
    // Matched on the NUMBER, not on the "XP Gain:" label, so this keeps working
    // with ENABLE_PROSE off (the label is still 经验获取: at that point).
    // Anchored at the end, which is also what makes it idempotent: once
    // " (x1.70e6)" has been appended the pattern no longer matches.
    const XP_GAIN_VALUE_RE = /(x)(\\d[\\d,]*(?:\\.\\d+)?)\\s*$/;

    // root is optional: translateHot passes the ONE open tooltip, so the
    // annotation is restored in the same batch that rewrote the line rather
    // than waiting for the throttled scan - otherwise the "(x1.70e6)" suffix
    // flickers on its own, which is the mistake v12.6 fixed for maxed bars.
    // Without a root it sweeps the lot, which is what the scan pass wants.
    function annotateXpGain(root) {
        if (!ENABLE_VISUAL_OVERRIDES || !XP_GAIN_SCIENTIFIC) return;
        const els = (root || document).querySelectorAll('.skill_xp_gain');
        for (let i = 0; i < els.length; i++) {
            // First child only: the element is `LABEL: xN<br><span>…</span>`,
            // and the span holds XP Cost Scaling, which is always small.
            const node = els[i].firstChild;
            if (!node || node.nodeType !== 3) continue;
            const text = node.textContent;
            const m = XP_GAIN_VALUE_RE.exec(text);
            if (!m) continue;
            const n = parseFloat(m[2].replace(/,/g, ''));
            // Below the threshold the scientific form is longer than the number
            // it explains ("x1.6" -> "x1.60e0"), so it is noise, not help.
            if (!(n >= XP_GAIN_SCI_MIN)) continue;
            node.textContent = text + ' (x' + sciShort(n) + ')';
        }
    }

    // Crafting's component list shows a part's NAME only, while its tier - the
    // thing you are actually choosing by - is buried in the hover tooltip:
    //     T16 · Skybreaker Wheel Hub
    //
    // The tier comes from partTiers, generated from items.js component_tier.
    // Reading it out of the tooltip does NOT work, in two different ways that
    // look identical in the DOM - both produce a tooltip with no tier line:
    //   - Armor-class parts (幻符背心, tier 16) take the equippable branch of
    //     the tooltip builder and never reach the tier line;
    //   - genuine tier-0 parts (铁剑刃) are skipped by `if(item.component_tier)`.
    // So "no line" cannot mean "tier 0", and the first attempt at this labelled
    // all 53 armour parts T0.
    const PART_TIER_DONE_RE = /^T\\d+\\s+·\\s/;

    function prefixCraftingTiers() {
        if (!ENABLE_VISUAL_OVERRIDES || !CRAFTING_TIER_PREFIX) return;
        const mats = document.querySelectorAll('.selectable_material');
        for (let i = 0; i < mats.length; i++) {
            const icon = mats[i].querySelector('.material-icons');
            if (!icon) continue;
            // display.js builds `<i…> check </i>${getName()}`, so the name is
            // the text node straight after the icon - same shape the travel
            // options use. Reading the div's textContent would swallow the
            // whole tooltip.
            const node = icon.nextSibling;
            if (!node || node.nodeType !== 3) continue;
            const name = node.textContent.trim();
            // The game rebuilds this list from scratch on every refresh, so the
            // prefix has to be re-applied - but never twice within one scan.
            if (!name || PART_TIER_DONE_RE.test(name)) continue;
            const tier = partTiers[name];
            // `=== undefined`, not a falsy test: tier 0 is a real tier and the
            // falsy version of this check is the bug being fixed here.
            if (tier === undefined) continue;
            node.textContent = 'T' + tier + ' · ' + name;
        }

        // GEAR crafting (.selectable_component) gets the same prefix, but the
        // tier does not need looking up: display.js sets
        //     item_div.dataset.component_tier = item.component_tier
        // unconditionally, so it is already on the element. The row here reads
        // "Name, 400%, x42834" - the prefix goes in front of the whole thing.
        const comps = document.querySelectorAll('.selectable_component');
        for (let i = 0; i < comps.length; i++) {
            const icon = comps[i].querySelector('.material-icons');
            if (!icon) continue;
            const node = icon.nextSibling;
            if (!node || node.nodeType !== 3) continue;
            const name = node.textContent.trim();
            if (!name || PART_TIER_DONE_RE.test(name)) continue;
            const tier = comps[i].getAttribute('data-component_tier');
            // Digits only. That assignment is unconditional, so an item with no
            // component_tier stringifies to "undefined" and would otherwise
            // render as "Tundefined · ".
            if (!/^\\d+$/.test(tier || '')) continue;
            node.textContent = 'T' + tier + ' · ' + name;
        }
    }

    // Bestiary loot names, but ONLY the ones that actually wrap.
    //
    // .loot_slot_div is a fixed 20px row and .loot_name is 200px wide - enough
    // for the 4-6 glyphs a Chinese drop name needs. English names run far
    // longer ("Intermediate Evolution Crystal Fragment"), wrap to two lines,
    // and overflow the row into the one below.
    //
    // line-height: 12px fixes those: two lines is 24px and .loot_name already
    // carries margin-top: -4px, so 24 - 4 lands exactly on the 20px row.
    //
    // Applying it as a plain CSS rule is what v11.9 did, and it was wrong: the
    // -4px margin was tuned against the DEFAULT line-height, so overriding it
    // on a name that fits in one line shifts that name off its baseline. Only
    // the wrapping ones may be touched, and CSS cannot select on text length.
    //
    // Whether a name wraps is a question about WIDTH, so measure the width.
    //
    // This used to count characters, on the reasoning that .loot_name is a
    // fixed width so length is a good enough proxy. It is not, and the failure
    // is not an off-by-one: "Dust · Ferocious Beast Meat" is exactly 27
    // characters, the same as "Intermediate Evolution Crys", and renders about
    // 203px against the other's ~180 - four capitals, a middle dot and four
    // spaces where the other has narrow lowercase. Any single character count
    // is wrong for one of the two.
    //
    // Measured through a canvas rather than the DOM because these elements
    // CANNOT be measured: .bestiary_entry_tooltip is display:none until its
    // row is hovered, so offsetHeight, clientWidth and getClientRects() all
    // report zero for every name in the list. measureText needs no layout at
    // all, which also means this still costs no reflow.
    //
    // 200 = .loot_name's width. It is content-box (the stylesheet's only
    // box-sizing:border-box is scoped to .selectable_component/_material), so
    // the 4px padding-left sits outside it and the full 200px is text.
    const LOOT_NAME_W = 200;
    // Fallback only, for a browser with no canvas: the old proxy, which is
    // right far more often than it is wrong.
    const LOOT_NAME_WRAP_LEN = 27;
    let lootCtx;            // undefined = not tried yet, null = unavailable
    let lootFont = '';

    // The font comes from getComputedStyle, which - unlike every layout
    // property - still answers for a display:none element. Read once from the
    // first name we see and cached, so this is one style flush per session.
    function lootWraps(el, text) {
        if (lootCtx === undefined) {
            const canvas = document.createElement('canvas');
            lootCtx = (canvas.getContext && canvas.getContext('2d')) || null;
            if (lootCtx) {
                const cs = window.getComputedStyle(el);
                lootFont = (cs.fontStyle || '') + ' ' + (cs.fontWeight || '') +
                           ' ' + (cs.fontSize || '16px') + ' ' +
                           (cs.fontFamily || 'Arial');
            }
        }
        if (!lootCtx) return text.length > LOOT_NAME_WRAP_LEN;
        lootCtx.font = lootFont;
        return lootCtx.measureText(text).width > LOOT_NAME_W;
    }

    function fitLootNames() {
        // :not([data-tl-fit]) keeps this cheap. The bestiary builds a tooltip
        // per enemy, so there are thousands of these elements, and each one
        // only ever needs deciding once.
        const names = document.querySelectorAll('.loot_name:not([data-tl-fit])');
        for (let i = 0; i < names.length; i++) {
            const el = names[i];
            const text = (el.textContent || '').trim();
            // Skip anything still untranslated: the Chinese name is short and
            // would be judged "fits", locking in the wrong answer forever. Let
            // a later scan decide it, once the prose pass has been past.
            if (!text || CJK_RE.test(text)) continue;
            el.dataset.tlFit = '1';
            if (lootWraps(el, text)) {
                el.style.lineHeight = '12px';
            }
        }
    }

    // A 5th journal tab: the bestiary, filtered to just the zone rows - a slim
    // teleport menu. The rows are NOT copied anywhere; the tab only adds a
    // class to #bestiary_list and one CSS rule hides everything that is not a
    // zone row. So tooltips, the game's re-sorts and the teleport clicks
    // themselves all keep working, and no undiscovered zone can appear:
    // add_bestiary_lines(zone) is only called from add_bestiary_entry() on
    // first meeting that zone's sentinel enemy.
    const ZONES_TAB_ID = 'tl_journal_show_zones';
    const ZONES_ONLY_CLASS = 'tl_zones_only';
    // Per-button widths, in DOM order. 103+58+73+73+83 = 390, plus the 1px
    // margin either side of five buttons = 400px, which is exactly #journal_div.
    // Sized for the game's own 18px font, so nothing has to shrink.
    const JOURNAL_TAB_W = [
        ['journal_show_quests', 103],
        [ZONES_TAB_ID, 58],
        ['journal_show_bestiary', 73],
        ['journal_show_levelary', 73],
        ['journal_show_data', 83],
    ];

    function addZonesTab() {
        if (!ENABLE_VISUAL_OVERRIDES || !ZONES_TAB) return;
        // Re-checked from the DOM rather than a flag, so the tab comes back if
        // the bar is ever rebuilt. A miss costs one getElementById per scan.
        if (document.getElementById(ZONES_TAB_ID)) return;
        const bar = document.getElementById('journal_control_div');
        const bestiary = document.getElementById('journal_show_bestiary');
        if (!bar || !bestiary) return;

        const btn = document.createElement('div');
        btn.id = ZONES_TAB_ID;
        btn.className = 'journal_control_button';
        // textContent, NOT innerHTML with a wrapper: the game's
        // set_active_button bails on `clicked_element.children.length == 0`, so
        // an element child here would silently cost the tab its highlighting.
        btn.textContent = ' Zones ';
        bar.insertBefore(btn, bestiary);

        // Widths inline rather than in styleOverrides: with the toggle off the
        // game's own 4x98px row has to be left exactly as it was.
        for (let i = 0; i < JOURNAL_TAB_W.length; i++) {
            const el = document.getElementById(JOURNAL_TAB_W[i][0]);
            if (el) el.style.width = JOURNAL_TAB_W[i][1] + 'px';
        }

        // ONE delegated listener for the whole bar. set_active_button is
        // delegated on this same container and was attached at load, so it
        // already handles highlighting for a child added later - only the
        // filtering is left to do here.
        bar.addEventListener('click', function (e) {
            const t = e.target;
            if (!t || t.parentNode !== bar) return;
            const list = document.getElementById('bestiary_list');
            if (!list) return;
            if (t.id === ZONES_TAB_ID) {
                if (typeof window.showBestiary === 'function') window.showBestiary();
                list.classList.add(ZONES_ONLY_CLASS);
            } else {
                list.classList.remove(ZONES_ONLY_CLASS);
            }
        });
    }

    // Wall-clock timestamps on log messages: 30.08.26-13:07:12.
    //
    // Written as a data- attribute and rendered by a CSS ::before, NOT as text
    // prepended to the message. Three reasons, in order of weight:
    //   - the log holds ~200 messages, and this adds no nodes to it at all
    //   - applyProse walks TEXT nodes, so a prepended span would put ~200 more
    //     of them in front of the tree walker on every pass over the log
    //   - the attribute is its own "already stamped" marker, so nothing has to
    //     be tracked separately
    // .message_common is display:inline-block, so ::before renders inline at
    // the head of the message rather than on a line of its own.
    //
    // Driven off the observer's RECORDS rather than by querying the log. The
    // records name the nodes that were just added, which is O(new messages);
    // any selector over #message_box_div is O(log size) on every batch, and
    // batches are frequent. It is also the only way to get the time right: a
    // throttled pass would stamp up to SCAN_MIN_MS late and could land in the
    // wrong second.
    const MSG_LOG_ID = 'message_box_div';
    const MSG_STACKED_CLASS = 'tl_ts_stacked';
    let msgLog = null;

    function pad2(n) { return n < 10 ? '0' + n : '' + n; }

    // Time only by default. With the date on, the two go on separate lines -
    // a real newline in the attribute, rendered by white-space:pre on the
    // ::before. Stacking is what makes the date affordable at all: inline,
    // "31.08.2026-11:58:24" eats 116px of a 395px line at 12px, where the two
    // stacked lines are 56px at 10px.
    //
    // FULL year, so the date line is deliberately wider than the time line
    // (56px vs 45px). An earlier draft used a 2-digit year to make the two
    // exactly equal; the ragged edge is the wanted look, so do not "fix" it
    // back to matching widths.
    function stampNow() {
        const d = new Date();
        const time = pad2(d.getHours()) + ':' + pad2(d.getMinutes()) + ':' +
                     pad2(d.getSeconds());
        if (!MESSAGE_TIMESTAMP_DATE) return time;
        return pad2(d.getDate()) + '.' + pad2(d.getMonth() + 1) + '.' +
               d.getFullYear() + '\\n' + time;
    }

    function stampMessages(records) {
        if (!ENABLE_VISUAL_OVERRIDES || !MESSAGE_TIMESTAMPS) return;
        // Re-looked-up until found rather than cached as null on the first
        // miss, so this still works if the observer beats the element.
        if (!msgLog) msgLog = document.getElementById(MSG_LOG_ID);
        if (!msgLog) return;
        // One reading per batch, taken lazily so a batch with no message at
        // all never constructs a Date. Messages added in the same batch were
        // logged in the same task, so they SHOULD share a timestamp.
        let now = '';
        for (let i = 0; i < records.length; i++) {
            if (records[i].target !== msgLog) continue;
            const added = records[i].addedNodes;
            for (let j = 0; j < added.length; j++) {
                const el = added[j];
                if (el.nodeType !== 1 || !el.classList) continue;
                if (!el.classList.contains('message_common')) continue;
                if (el.hasAttribute('data-tl-ts')) continue;
                let skip = false;
                for (let k = 0; k < MESSAGE_TIMESTAMP_SKIP.length; k++) {
                    if (el.classList.contains(MESSAGE_TIMESTAMP_SKIP[k])) {
                        skip = true;
                        break;
                    }
                }
                if (skip) continue;
                if (!now) now = stampNow();
                el.setAttribute('data-tl-ts', now);
                // A class, because CSS cannot ask whether an attribute value
                // contains a newline. The two layouts genuinely differ: the
                // one-line stamp stays INLINE, so it costs the message its
                // first line only, while the stacked one has to float and
                // therefore indents every line it spans. Inline is the
                // cheaper of the two and stays the default.
                if (MESSAGE_TIMESTAMP_DATE) el.classList.add(MSG_STACKED_CLASS);
            }
        }
    }

    // Break the family roster's realm names after the tier:
    //     "Sky-Tier Rank 1"  ->  "Sky-Tier"
    //                            "Rank 1"
    // The column is 84px at 10px, so most of these wrapped anyway - but they
    // wrapped wherever the text happened to run out, which put the break in a
    // different place on every row. Choosing it makes the column scan as two
    // aligned fields instead of ragged prose.
    //
    // A real newline plus white-space:pre-line, NOT an <br> through innerHTML:
    // identical rendering, and it keeps every write in this file textContent-
    // only, so there is no escaping question and no interaction with the prose
    // pass, which also works in textContent.
    //
    // Runs in translateHot, in the SAME batch as the roster's translation. On
    // the throttled pass instead it would add a line to ~37 rows one frame
    // after they were translated - a height change under the scrollbar, which
    // is the exact fault v13.9 and v14.5 were spent on.
    // U+00A0 and U+2011. Named because they are invisible in a diff and easy to
    // mistake for the ASCII pair when editing. U+2011 is the one to watch: it
    // is well covered by the fonts this game uses, but a font without it draws
    // a missing-glyph box rather than falling back to '-'. If that ever shows
    // up, the fix is to make NB_HYPHEN an ordinary '-' and accept the rank
    // wrapping - the non-breaking space alone still does most of the work.
    const NB_SPACE = '\\u00a0';
    const NB_HYPHEN = '\\u2011';

    function breakRealmNames() {
        if (!ENABLE_VISUAL_OVERRIDES || !FAMILY_REALM_BREAK) return;
        const cells = document.querySelectorAll(
            '#family_member_list .member_list_realm');
        for (let i = 0; i < cells.length; i++) {
            const el = cells[i];
            const text = el.textContent;
            if (!text || text.indexOf('\\n') !== -1) continue;   // already done
            const at = text.indexOf(' ');
            // No space: the 境界/Realm header, or a tier with no rank after it.
            if (at === -1) continue;
            const tier = text.slice(0, at);
            // Not a known tier means the prose pass has not been past yet -
            // the cell still says 天空级一阶. Leave it for a later batch rather
            // than breaking a Chinese name at a space it does not have.
            if (!REALM_TIERS.has(tier)) continue;
            if (FAMILY_REALM_BREAK_SKIP.indexOf(tier) !== -1) {
                // A skipped tier gets no line of its own - its name already
                // fills the column, so a break after it would cost a third
                // line. It still has to wrap SOMEWHERE though, and left alone
                // the browser picks the last opportunity that fits, which for
                // "All-Things-Tier High-Tier" is the hyphen inside the rank:
                //     All-Things-Tier High-
                //     Tier
                // Gluing the rank together moves the wrap back to the tier's
                // own hyphen and keeps the rank whole:
                //     All-Things-
                //     Tier High-Tier
                // A non-breaking space before the rank and non-breaking hyphens
                // inside it remove every break opportunity after the tier, so
                // the hyphens in the tier NAME are the only ones left.
                //
                // Idempotent by the same test that finds the work: once the
                // space is NB_SPACE, indexOf(' ') is -1 and the cell is skipped
                // above on every later batch.
                el.textContent = tier + NB_SPACE +
                    text.slice(at + 1).split('-').join(NB_HYPHEN);
                continue;
            }
            el.textContent = tier + '\\n' + text.slice(at + 1);
        }
    }

    // A shortcut row at the top of the location actions list.
    //
    // #location_actions_div scrolls, and a busy location fills it: Village has
    // 6 activities, 3 dialogues, a trader and a crafting station, so travel is
    // below the fold. The bar puts one icon per ACTION CATEGORY at the top.
    //
    // Per category, NOT per action, which is the only arrangement where the
    // positions can be fixed: the category set is fixed and small, the counts
    // are not. The game also gives every row in a category the same glyph
    // (all 6 of Village's jobs are work_outline, and .start_trade uses
    // work_outline too), so one icon per action would render seven identical
    // briefcases. One per category makes the slot itself the distinction.
    // Where a category has several rows the icon acts on the FIRST.
    //
    // Layout: navigation on the left, growing rightward with however many
    // destinations exist; everything else anchored to the RIGHT edge, so a
    // location with more exits cannot push the fixed slots around. Absent
    // slots are rendered as invisible placeholders rather than omitted -
    // omitting them would let the remaining icons slide, which is the thing
    // being avoided.
    //
    // Combat destinations are deliberately absent. They are one click from
    // starting a fight, and an icon-only control is exactly where a misclick
    // happens.
    const ACTION_BAR_ID = 'tl_action_bar';
    const BAR_TARGET_CLASS = 'tl_bar_target';
    // The first row we last saw in the container, for spotting a rebuild by
    // node identity. clear_action_div() removes every element child, so after
    // one the first child is a DIFFERENT node - the same trick the family
    // roster uses, and for the same reason: no measurement, no layout.
    let actionBarAnchor = null;
    // A travel row whose destination is somewhere you can sleep - the game's
    // own quick-return-to-bed link, or an ordinary exit that happens to lead
    // to one. REST_LOCATIONS is generated from locations.js and keyed by the
    // Chinese name, which is what data-travel holds, so this needs no
    // translation and is unaffected by ENABLE_PROSE.
    function isSafeZoneRow(r) {
        return r.classList.contains('travel_normal') &&
               !r.classList.contains('travel_combat') &&
               REST_LOCATIONS.has(r.getAttribute('data-travel'));
    }

    // The game's OWN quick-return-to-bed link, exactly. display.js builds only
    // that one row as
    //     <span style="color:#c0c0ff">…快速返回 [name]</span>
    // and c0c0ff appears exactly once in the whole game source, so an inner
    // span carrying it is a unique marker - no label parsing, and therefore
    // unaffected by ENABLE_PROSE.
    //
    // It has to be an INNER span. colorRestTravel paints the same colour, but
    // onto the ROW, so the row's own style attribute is not consulted here and
    // our tint can never be mistaken for the game's link.
    //
    // This replaces matching on the 'directions' glyph, which was wrong in one
    // real place: mirrorReturnIcons leaves the signpost on BOTH jump kinds, so
    // at the Act 2 camp the Fast Travel to Act 1 - whose destination 纳可的房间
    // is the one fast-travel hub that is also a rest location - outranked the
    // actual Quick Return and took the slot.
    function isGameQuickReturn(r) {
        return !!r.querySelector('span[style*="c0c0ff" i]');
    }

    // When a location has more than two of a kind, the game does not list them
    // - it collapses them into ONE button ("Find some work", "Train for a
    // bit", "Talk to someone", …), all sharing .location_choices with a
    // data-location attribute and a format_list_bulleted glyph. The only thing
    // separating them is the category in their onclick, which the game writes
    // as a literal, so this reads it rather than guessing from the label.
    function barChoiceCategory(r) {
        if (!r.classList.contains('location_choices')) return '';
        const m = /category:\s*"(\w+)"/.exec(r.getAttribute('onclick') || '');
        return m ? m[1] : '';
    }

    // The variable group: everything you can DO here, one icon per row, in the
    // game's own order. Not slots, because these are the kinds that legitimately
    // repeat - and they need no slots, since the game already gives each type
    // its own glyph: question_answer, work_outline for a job, fitness_center
    // for training, search for gathering. A collapsed category comes through as
    // its format_list_bulleted button, which is the only thing on screen for
    // that category, so leaving it out would hide the category entirely.
    // .start_trade is here as well as being a static slot. The slot takes one
    // trader and the loop below skips whatever it claimed, so this only ever
    // catches the EXTRAS - which would otherwise be dropped entirely.
    // 飞云阁 (Feiyun Pavilion) is the single location where that happens: it
    // stocks both 物品存储箱 (Item Storage Chest) and 百宝楼 (Treasure
    // Pavilion), so the chest fills the slot and the shop had no icon at all.
    // The other three static slots cannot repeat - one sleeping block and one
    // crafting station per location - and a second safe-zone route already
    // falls through to navigation.
    function isBarAction(r) {
        if (r.classList.contains('start_dialogue')) return true;
        if (r.classList.contains('start_activity')) return true;
        if (r.classList.contains('start_trade')) return true;
        const cat = barChoiceCategory(r);
        return cat === 'talk' || cat === 'work' || cat === 'train' ||
               cat === 'gather';
    }

    // Navigation. The travel collapse button belongs here and not with the
    // actions: past three exits the game replaces EVERY travel row with it, so
    // without it the navigation group would come out empty at exactly the
    // locations with the most places to go.
    function isBarNav(r) {
        if (r.classList.contains('travel_combat')) return false;
        if (r.classList.contains('travel_normal')) return true;
        return barChoiceCategory(r) === 'travel';
    }

    // In fixed left-to-right order: [name, match, basicGlyph, prefer].
    //
    // basicGlyph is the BASIC form - what the slot shows when the location has
    // nothing to put in it. A lit slot clones the row's own icon instead, so
    // it always matches the symbol sitting in the list below.
    //
    // That means the basic glyph does not have to be the game's: it only has
    // to say which action is missing. search reads as "no work here" better
    // than the work_outline the game puts on a job row, and shop covers the
    // slot's real span - the game files both traders and the storage chest as
    // .start_trade.
    //
    // .activity_unavailable is NOT .start_activity, so unavailable jobs are
    // excluded by construction rather than by a test that could be forgotten.
    // The crafting button is .location_choices without data-location; the
    // travel-list expander is the one WITH it, and is deliberately not a slot
    // here - it only appears on locations with more than three exits, so a
    // fixed slot for it would sit empty nearly everywhere.
    const ACTION_BAR_SLOTS = [
        // Covers both a real trader and the storage chest - the game files
        // both as .start_trade.
        ['trade', (r) => r.classList.contains('start_trade'), 'storefront'],
        ['sleep', (r) => r.id === 'start_sleeping_div', 'bed'],
        ['craft', (r) => r.classList.contains('location_choices') &&
                         !r.hasAttribute('data-location'), 'construction'],
        // 4th element: a PREDICATE marking the row to prefer when several
        // match, instead of taking the first. Several exits can lead to a bed;
        // the retreat slot should mean the game's own Quick Return wherever
        // one exists, and only fall back to walking somewhere restful.
        ['safezone', isSafeZoneRow, 'directions', isGameQuickReturn],
    ];

    // The row's own icon, cloned - so the mirrored return arrow (an inline
    // transform) and the rest-location tint come across without being
    // reapplied. The colour lives on a wrapper span in most rows, so it is
    // copied down from the nearest ancestor that carries one.
    function barIconFor(row) {
        const src = row.querySelector('.material-icons');
        if (!src) return null;
        // The ROW's icon wins whenever there is a row. The slot's own glyph is
        // only the basic form, for when the location has nothing to put here -
        // so a lit slot always shows exactly the symbol sitting in the list
        // below it, including the mirrored return arrow and the rest tint.
        const icon = src.cloneNode(true);
        if (!icon.style.color) {
            let el = src;
            while (el && el !== row) {
                if (el.style && el.style.color) {
                    icon.style.color = el.style.color;
                    break;
                }
                el = el.parentNode;
            }
            if (!icon.style.color && row.style.color) icon.style.color = row.style.color;
        }
        const cell = document.createElement('span');
        cell.className = 'tl_bar_icon';
        cell.appendChild(icon);
        // The row carries its handler as an inline onclick and the container
        // has no delegated click listener (only mousemove, for the activity
        // tooltip), so a synthetic click runs the game's own code exactly
        // once. Nothing here needs to know what any action does.
        cell.addEventListener('click', () => row.click());
        // Hovering an icon lights up the row it will act on. This is the
        // answer to "which of these two arrows is which" - the location rows
        // carry no tooltip of their own to inherit, and a title= attribute is
        // a second-long wait on a control whose whole point is speed. The
        // list is directly below the bar, so the answer is already on screen.
        if (ACTION_BAR_HOVER_HINT) {
            cell.addEventListener('mouseenter',
                () => row.classList.add(BAR_TARGET_CLASS));
            cell.addEventListener('mouseleave',
                () => row.classList.remove(BAR_TARGET_CLASS));
        }
        return cell;
    }

    function addActionBar() {
        if (!ENABLE_VISUAL_OVERRIDES || !LOCATION_ACTION_BAR) return;
        const host = document.getElementById('location_actions_div');
        if (!host) return;
        // Re-checked from the DOM, not a flag: clear_action_div() removes every
        // element child on each mode change, so the bar is destroyed and
        // rebuilt constantly and "add it when missing" is the whole lifecycle.
        // It also means rows are only ever collected while the bar is absent,
        // so it can never read its own icons back in.
        if (document.getElementById(ACTION_BAR_ID)) return;

        const rows = [];
        for (let i = 0; i < host.children.length; i++) {
            const r = host.children[i];
            if (r.id !== ACTION_BAR_ID) rows.push(r);
        }

        // The fixed slots are resolved FIRST, so the navigation group can skip
        // the exact row one of them took rather than a whole category. Only
        // the safe-zone slot ever claims a travel row, but claiming by node
        // keeps that a fact about this loop instead of a rule to remember.
        const claimed = [];
        const fixed = [];
        let found = 0;
        for (let s = 0; s < ACTION_BAR_SLOTS.length; s++) {
            const match = ACTION_BAR_SLOTS[s][1];
            const prefer = ACTION_BAR_SLOTS[s][3];
            let chosen = null;
            for (let i = 0; i < rows.length; i++) {
                if (!match(rows[i])) continue;
                if (!chosen) chosen = rows[i];          // first occurrence wins
                if (prefer && prefer(rows[i])) {
                    chosen = rows[i];                   // …unless one is preferred
                    break;
                }
            }
            if (chosen) claimed.push(chosen);
            let cell = chosen ? barIconFor(chosen) : null;
            if (cell) {
                found++;
            } else {
                // Shown greyed and unclickable rather than blank: the slot
                // still holds its position, and an inactive icon says WHICH
                // action is missing here, which a gap cannot. Same glyph as
                // the lit form above, so the symbol in a given position never
                // changes - only whether it is lit.
                cell = document.createElement('span');
                cell.className = 'tl_bar_icon tl_bar_empty';
                cell.innerHTML = '<i class="material-icons">' +
                                 ACTION_BAR_SLOTS[s][2] + '</i>';
            }
            fixed.push(cell);
        }

        // Every way out of here, in the order the game lists them - including
        // exits that happen to lead somewhere restful, which are ordinary
        // walking routes and belong with the rest. The single exception is the
        // row the safe-zone slot took: that one has a fixed home on the right,
        // and showing it twice would defeat the point of giving it one.
        // travel_combat is still absent - an encounter is not movement you
        // want one click away.
        const nav = [];
        const acts = [];
        for (let i = 0; i < rows.length; i++) {
            if (claimed.indexOf(rows[i]) !== -1) continue;
            const cell = isBarNav(rows[i]) ? barIconFor(rows[i])
                       : isBarAction(rows[i]) ? barIconFor(rows[i]) : null;
            if (!cell) continue;
            (isBarNav(rows[i]) ? nav : acts).push(cell);
        }

        // Nothing to show. During an activity start_activity_display() refills
        // this container with #action_status_div and friends, which are
        // innerText only - so this is decided by CONTENT, and holds for any
        // mode we have not thought about rather than only the ones we have.
        if (!nav.length && !acts.length && !found) return;

        // Three groups: navigation at the left edge, then actions and the four
        // static slots together at the right. The CSS puts the auto margin on
        // the ACTIONS group, so those two travel as one block and grow leftward
        // into the gap, while the static four stay last and therefore the same
        // distance from the right edge everywhere - which is the point of them.
        const bar = document.createElement('div');
        bar.id = ACTION_BAR_ID;
        const left = document.createElement('span');
        left.className = 'tl_bar_group';
        for (let i = 0; i < nav.length; i++) left.appendChild(nav[i]);
        const mid = document.createElement('span');
        mid.className = 'tl_bar_group tl_bar_actions';
        for (let i = 0; i < acts.length; i++) mid.appendChild(acts[i]);
        const right = document.createElement('span');
        right.className = 'tl_bar_group tl_bar_fixed';
        for (let i = 0; i < fixed.length; i++) right.appendChild(fixed[i]);
        bar.appendChild(left);
        bar.appendChild(mid);
        bar.appendChild(right);
        host.insertBefore(bar, host.firstChild);
    }

    // Raw spec numbers in bestiary tooltips, put into scientific form.
    //
    // display.js's spec_stat table formats SOME of its values and not others:
    // spec 18 and 55 go through format_money, 39/48/49 through format_number,
    // but 8, 21, 29, 35 and 43 are string-concatenated raw, so the tooltip
    // reads "1000000000000点魔法伤害" where every other figure on the same
    // card reads 9.50e13. That is an inconsistency in the game rather than a
    // decision - which is exactly what makes it safe to fix.
    //
    // Contrast the kill counter, which display.js renders as a bare
    // Math.round(get_enemy_killcount()) with NO formatter, deliberately: an
    // exact count is the point of it. This pass must never reach that, hence
    // the scope below.
    //
    // ---- scope ----
    // .bestiary_entry_tooltip and nothing else. spec_stat is consumed in one
    // place, add_bestiary_tooltip(), and both it and the levelary tooltip
    // carry that class, so it covers every occurrence. The counters live in
    // .data_entry_value in the Data tab, which this selector cannot reach.
    //
    // ---- which numbers ----
    // Only where the scientific form is LOSSLESS and SHORTER. The mantissa is
    // the digits with trailing zeros stripped, and the exponent puts them
    // back, so no digit is ever dropped - and a number carrying real precision
    // disqualifies itself by being longer:
    //     900000000000  -> 9e11           12 chars -> 4     rewritten
    //     1000000000000 -> 1e12           13 -> 4           rewritten
    //     63247689      -> 6.3247689e7    8 -> 11           left alone
    // So "you have killed 63247689 enemies" survives this rule even if such a
    // string ever appeared inside the scope, without needing a special case.
    const SCI_MIN_DIGITS = 7;               // 7 digits = 1e6 and up
    const BIG_INT_RE = /\\d+/g;

    function sciIfShorter(digits) {
        if (digits.length < SCI_MIN_DIGITS) return digits;
        let mantissa = digits.replace(/0+$/, '');
        if (!mantissa) return digits;       // all zeroes; not a real value
        const out = mantissa.charAt(0) +
                    (mantissa.length > 1 ? '.' + mantissa.slice(1) : '') +
                    'e' + (digits.length - 1);
        return out.length < digits.length ? out : digits;
    }

    function sciBigNumbers() {
        if (!ENABLE_VISUAL_OVERRIDES || !BESTIARY_SCI_NUMBERS) return;
        // Decided once per tooltip, like fitLootNames: the bestiary builds one
        // per enemy, so there are hundreds of these and re-walking them all on
        // every scan would not be affordable.
        const tips = document.querySelectorAll(
            '.bestiary_entry_tooltip:not([data-tl-sci])');
        for (let i = 0; i < tips.length; i++) {
            const tip = tips[i];
            // Runs AFTER the prose pass, and skips a tooltip that still holds
            // Chinese rather than marking it done. Order matters here: a node
            // rewritten before translation would no longer match its own
            // proseExact key - the key contains the original digits - and the
            // description would be stranded in Chinese permanently.
            if (CJK_RE.test(tip.textContent)) continue;
            tip.dataset.tlSci = '1';
            const walker = document.createTreeWalker(tip, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const text = node.textContent;
                if (text.length < SCI_MIN_DIGITS) continue;
                const out = text.replace(BIG_INT_RE, sciIfShorter);
                if (out !== text) node.textContent = out;
            }
        }
    }

    // The separator between a special attribute's NAME and its description.
    //
    // display.js builds each one as
    //     `<br><b><font color=…>${name} </font></b> ：${description} `
    // - a trailing space inside the bold, then a space and a FULLWIDTH colon
    // outside it. That spacing is right for Chinese, where the colon carries
    // its own half-em of air and sits away from both sides. Translated it
    // reads "Spirit Flash  :A light-element insight." - two spaces before the
    // colon and none after, so the colon binds to the description instead of
    // the title it belongs to.
    //
    // Both halves have to move, and they are in different nodes: the trailing
    // space belongs to the name's text node INSIDE the <b>, the colon to the
    // text node after it. A fragment can only ever reach one of them, which is
    // why this is a DOM pass and not a glossary entry.
    //
    // Nothing else in these tooltips matches the shape. The other colons
    // (Stats:, Loot:, HP:) are already tight against their labels and none of
    // them follows a <b>; the only other bold is the realm badge, whose next
    // sibling is a <br> element rather than a text node.
    const SPEC_COLON_RE = /^\s*[:：]\s*/;

    function fixSpecColons() {
        if (!ENABLE_VISUAL_OVERRIDES || !SPEC_COLON_FIX) return;
        // Once per tooltip, like sciBigNumbers and fitLootNames - the bestiary
        // builds one per enemy and there are hundreds of them.
        const tips = document.querySelectorAll(
            '.bestiary_entry_tooltip:not([data-tl-colon])');
        for (let i = 0; i < tips.length; i++) {
            const tip = tips[i];
            // Same ordering rule as sciBigNumbers, and the same reason: the
            // node being rewritten here is the one applyProse matches against
            // its own key, so a tooltip still holding Chinese is DEFERRED
            // rather than marked done.
            //
            // IDEO_RE, not CJK_RE: the wider set INCLUDES the fullwidth colon
            // this pass exists to rewrite, so a tooltip whose separator had not
            // yet been converted by the stranded-punctuation fragment would
            // defer itself forever - fully translated, and permanently skipped.
            // Only an ideograph means the prose pass still has work to do.
            if (IDEO_RE.test(tip.textContent)) continue;
            tip.dataset.tlColon = '1';
            const bolds = tip.querySelectorAll('b');
            for (let j = 0; j < bolds.length; j++) {
                const b = bolds[j];
                const sib = b.nextSibling;
                if (!sib || sib.nodeType !== 3) continue;
                const m = SPEC_COLON_RE.exec(sib.textContent);
                if (!m) continue;
                sib.textContent = ': ' + sib.textContent.slice(m[0].length);
                // The name's own trailing space lives in the DEEPEST last text
                // node of the bold - the game wraps the name in a <font> for
                // the colour, so b.lastChild is an element, not the text.
                let last = b;
                while (last.lastChild) last = last.lastChild;
                if (last.nodeType === 3) {
                    last.textContent = last.textContent.replace(/\s+$/, '');
                }
            }
        }
    }

    // Travel links that lead somewhere you can sleep, in the same #c0c0ff the
    // game already uses for its own quick-return-to-bed link (display.js hard-
    // codes that one inline). Somewhere to rest is the thing you scan a travel
    // list for, and it was the one destination with nothing to mark it.
    //
    // Keyed off data-travel, which holds the CHINESE location name and is
    // never translated, so this works identically with ENABLE_PROSE off and
    // cannot be confused by a re-worded English label.
    //
    // Scoped to .travel_normal: .travel_combat links carry data-travel too and
    // are already coloured #ffc0c0 by the game. No rest location is a combat
    // zone, so the two sets do not actually overlap - but the scope keeps that
    // a fact about the selector rather than a fact about the data.
    function colorRestTravel() {
        if (!ENABLE_VISUAL_OVERRIDES || !HIGHLIGHT_REST_TRAVEL) return;
        const links = document.querySelectorAll('.travel_normal[data-travel]');
        for (let i = 0; i < links.length; i++) {
            // Re-applying the same value is a no-op, which is what makes this
            // safe to run on every scan: #location_actions_div is rebuilt
            // whenever the location changes, so there is nothing to cache.
            // Only a handful of options exist at a time.
            if (REST_LOCATIONS.has(links[i].getAttribute('data-travel'))) {
                links[i].style.color = REST_TRAVEL_COLOR;
            }
        }
    }

    // A 5th trader category: Misc, without the Parts.
    //
    // The game buckets its four categories with three CSS variables, and Misc
    // is the catch-all:
    //     .trader_item_other, _loot, _material, _component, _book
    //         { display: var(--trader_other_display); }
    // so materials and Parts are filtered as one group and there is no way to
    // see the first without the second. Stocking up on crafting materials
    // means scrolling past the Parts every time, and they are the tall
    // expensive rows.
    //
    // Same shape as the Zones tab, and for the same reasons: no row is copied,
    // moved or rebuilt. The button sets the game's own three display variables
    // exactly as showOnlyTraderOther() does, then adds one class to
    // #trader_inventory_div for a CSS rule to hide the Parts. Every row stays
    // the game's own element, so the trade_ammount buttons, the tooltips, the
    // click-to-buy handler and the sort order are all untouched.
    const MATERIALS_BTN_ID = 'tl_trader_category_materials';
    const MATERIALS_ONLY_CLASS = 'tl_materials_only';
    // Five equal buttons: 78 + the 1px margin either side = 80, x5 = 400px,
    // which is exactly #location_related_div. The game's own four are 98px,
    // already filling the row, so a fifth at that width would wrap onto a
    // second line - all five have to come down together. 78px clears the
    // longest label ("Usable", ~48px in the inherited 16px Arial) with room to
    // spare, so nothing is tight and no font has to shrink.
    const TRADER_CAT_W = 78;
    const TRADER_CAT_IDS = [
        'trader_category_all',
        'trader_category_equipment',
        'trader_category_usable',
        'trader_category_other',
        MATERIALS_BTN_ID,
    ];

    function addMaterialsFilter() {
        if (!ENABLE_VISUAL_OVERRIDES || !TRADER_MATERIALS_FILTER) return;
        // Re-checked from the DOM rather than a flag, so the button comes back
        // if the row is ever rebuilt. A miss costs one getElementById per scan.
        if (document.getElementById(MATERIALS_BTN_ID)) return;
        const bar = document.getElementById('trader_category_buttons');
        if (!bar) return;

        const btn = document.createElement('div');
        btn.id = MATERIALS_BTN_ID;
        btn.className = 'trader_category_button';
        // textContent, NOT innerHTML with a wrapper: the game's
        // set_active_button bails on `clicked_element.children.length == 0`, so
        // an element child here would silently cost the button its highlight.
        btn.textContent = 'Mats';
        bar.appendChild(btn);

        // Widths inline rather than in styleOverrides: with the toggle off the
        // game's own 4x98px row has to be left exactly as it was.
        for (let i = 0; i < TRADER_CAT_IDS.length; i++) {
            const el = document.getElementById(TRADER_CAT_IDS[i]);
            if (el) el.style.width = TRADER_CAT_W + 'px';
        }

        // ONE delegated listener for the whole row. set_active_button is
        // delegated on this same container (it carries .activable_buttons) and
        // was attached at load, so it already highlights a child added later -
        // only the filtering is left to do here.
        //
        // The game's four buttons carry their filtering as inline onclick, and
        // a target-phase handler runs before a bubble-phase one on an ancestor,
        // so theirs has already set the variables by the time this clears the
        // class. Nothing to sequence by hand.
        bar.addEventListener('click', function (e) {
            const t = e.target;
            if (!t || t.parentNode !== bar) return;
            const list = document.getElementById('trader_inventory_div');
            if (!list) return;
            if (t.id === MATERIALS_BTN_ID) {
                // What showOnlyTraderOther() does; the CSS rule does the rest.
                const root = document.documentElement.style;
                root.setProperty('--trader_equipment_display', 'none');
                root.setProperty('--trader_consumable_display', 'none');
                root.setProperty('--trader_other_display', 'inline-block');
                list.classList.add(MATERIALS_ONLY_CLASS);
            } else {
                list.classList.remove(MATERIALS_ONLY_CLASS);
            }
        });
    }

    // "Add all": put every row currently ON SCREEN into the buy list.
    //
    // Displayed, deliberately, rather than "all materials". Paired with the
    // category buttons it means whatever you are looking at - Mats for a
    // crafting run, Gear for a shopping trip - instead of hard-coding one
    // answer into the button, and the two features stay independent.
    //
    // It adds nothing to the trade logic. Every row already carries an "all"
    // button, and #trader_inventory_div carries the game's delegated click
    // handler, so this is those buttons pressed for you: the same
    // add_to_buying_list() path, which clamps a count of Infinity to what the
    // trader actually holds. Nothing is bought here either - that is still
    // acceptTrade() behind the Trade button.
    const ADD_ALL_BTN_ID = 'tl_trade_add_all';
    const TRADE_ROW_SEL =
        '#trader_inventory_div > .trader_item_control:not(.item_to_trade)';
    const ALL_AMOUNT_SEL = '.trade_ammount_button[data-trade_ammount="Infinity"]';
    // Three equal buttons where the game had two: 131 + the 1px margin either
    // side = 133, x3 = 399 of the 400px row.
    const TRADE_BTN_W = 131;
    // A guard against a row that will not clear, not an expected limit: a
    // trader holds tens of items. Without it a row that survived its own click
    // would spin the browser.
    const ADD_ALL_MAX = 500;

    function tradeAddAllDisplayed() {
        for (let n = 0; n < ADD_ALL_MAX; n++) {
            // Re-queried EVERY pass, never cached. The game's click handler
            // ends in update_displayed_trader_inventory(), which does
            // `trader_inventory_div.textContent = ""` and rebuilds every row,
            // so a node held across one click is detached - and clicking a
            // detached node fails silently, since it is still a live element.
            const rows = document.querySelectorAll(TRADE_ROW_SEL);
            let btn = null;
            for (let i = 0; i < rows.length && !btn; i++) {
                // offsetParent is null for a display:none element, which is
                // exactly how the category buttons hide rows - they set CSS
                // variables the game's stylesheet reads. This forces a layout,
                // which is fine HERE and nowhere else: this runs on a click,
                // not on the scan or the mutation batch.
                if (rows[i].offsetParent !== null) {
                    btn = rows[i].querySelector(ALL_AMOUNT_SEL);
                }
            }
            if (!btn) return;
            btn.click();
            // Terminates because a row fully in the buy list is skipped
            // entirely on the rebuild (display.js: `if(item_count == 0)
            // return;`), so each pass removes one row from the match set.
        }
    }

    // :not(.item_to_trade) in TRADE_ROW_SEL is load-bearing, not tidiness. The
    // trader panel also renders the player's OWN to-sell items, with the same
    // trader_item_* classes plus item_to_trade (display.js appends them from
    // to_sell after the trader's own stock). Clicking one of those takes the
    // remove_from_selling_list branch instead - so an "add all" that missed
    // this would quietly un-sell the goods you had just staged.
    function addTradeAllButton() {
        if (!ENABLE_VISUAL_OVERRIDES || !TRADER_ADD_ALL) return;
        // Re-checked from the DOM rather than a flag, so the button comes back
        // if the row is ever rebuilt. A miss costs one getElementById per scan.
        if (document.getElementById(ADD_ALL_BTN_ID)) return;
        const bar = document.getElementById('trade_control_div');
        const accept = document.getElementById('accept_trade_button');
        const cancel = document.getElementById('cancel_trade_button');
        if (!bar || !accept || !cancel) return;

        const btn = document.createElement('div');
        btn.id = ADD_ALL_BTN_ID;
        btn.textContent = 'Add all';
        bar.insertBefore(btn, accept);

        // Inline, so with the toggle off the game's own 2x197px row is left
        // exactly as it was. Set by id: accept and cancel share their rule with
        // .trader_sorting_button, and widening that selector would resize the
        // two sorting buttons at the top of the panel as well.
        btn.style.width = TRADE_BTN_W + 'px';
        accept.style.width = TRADE_BTN_W + 'px';
        cancel.style.width = TRADE_BTN_W + 'px';

        // On the button itself, not delegated on the row: the game has no
        // handler here to share a container with, and Trade and Cancel are
        // wired as inline onclick attributes rather than through one listener.
        btn.addEventListener('click', tradeAddAllDisplayed);
    }

    // Shared by both annotators so their output cannot drift apart.
    //
    // Round to 2 decimals FIRST, then drop trailing zeroes. The two halves do
    // different jobs and both are needed: the rounding caps an awkward value
    // (1,234,567,890 -> 1.23e9) instead of printing every digit the way
    // toExponential() with no argument would, and the strip removes the noise
    // that rounding then adds to a round number (5.00e8 -> 5e8).
    // /\\.?0+e/ only fires on zeroes immediately before the exponent, so
    // 1.05e8 keeps its 5.
    function sciShort(n) {
        return n.toExponential(2).replace(/\\.?0+e/, 'e').replace('e+', 'e');
    }

    function translateEarlyContainers() {
        // These must run BEFORE the buttons pass - see the ordering note above.
        // The message log belongs here too: #message_box_div's pair list turns
        // 获取 into "Obtained:" and ，into ", ", which shreds longer entries like
        // 被打败,获取 before they can match. (It briefly lived in the per-panel
        // pass below, which runs after applySelector - that reintroduced the bug.)
        translateMessageLog();
        translateFishFont();
        EARLY_PROSE_FULL.forEach((id) => {
            const el = document.getElementById(id);
            if (el) applyProse(el, true);
        });
        EARLY_PROSE_EXACT.forEach((id) => {
            const el = document.getElementById(id);
            // exact + whole-node regexes, but only regexes that fully resolve
            if (el) applyProse(el, false, true, true);
        });
        document.querySelectorAll(EARLY_PROSE_EXACT_SEL).forEach((el) => {
            applyProse(el, false, true, true);
        });
    }

    // Main prose pass: only the panels that actually changed. The message log
    // is excluded because translateMessageLog() handles it incrementally.
    function applyProseToPanels() {
        if (!ENABLE_PROSE) return;
        // NB: the message log is handled in translateEarlyContainers(), which
        // runs before the buttons pass. Doing it here would be too late.
        const ids = proseAllDirty ? PANEL_IDS : dirtyPanels;
        ids.forEach((id) => {
            if (id === 'message_log_div') return;
            const el = document.getElementById(id);
            if (el) applyProse(el);
        });
        dirtyPanels.clear();
        proseAllDirty = false;
    }
    // ==== end generated ====""")
GEN = '\n'.join(block)

# ------------------------------------------------- splice into the userscript
src = open('../Script.txt', encoding='utf-8').read()

# drop a previous generated block if re-running
# \n+ (not \n) so the blank line we re-insert below is absorbed too; otherwise each
# re-run leaves one extra blank line behind and the file slowly grows.
src = re.sub(r'    // ==== GENERATED by translation/build\.py.*?    // ==== end generated ====\n+',
             '', src, flags=re.S)

anchor = "    // Escapes regex special characters"
if anchor not in src:
    print('!! anchor not found; aborting'); sys.exit(1)
src = src.replace(anchor, GEN + "\n\n" + anchor, 1)

# call applyProse at the end of scan()
# Migrate wiring emitted by an earlier version of this builder: the scan() call
# lines live outside the generated block, so a rename would otherwise leave a
# call to a function that no longer exists.
src = src.replace("        patchBestiaryLookups();\n",
                  "        patchNameLookups();\n        captureOriginalNames();\n", 1)

body = src.split(GEN)[-1]          # everything after the generated block
# NB: guard on the CURRENT function name. This used to test for 'applyProse(',
# which is not a substring of 'applyProseToPanels(' - so after that rename the
# guard passed on every run and appended another call each build.
if 'applyProseToPanels(' not in body:
    src = src.replace("        applyItemNames('#gathering_tooltip');",
                      "        applyItemNames('#gathering_tooltip');\n"
                      "        // Whole-game prose: descriptions, dialogue, system messages.\n"
                      "        applyProseToPanels();", 1)
if 'patchNameLookups(' not in body:
    # capture must run before anything translates the names we map back
    src = src.replace("        applyItemNames('#skill_list');",
                      "        patchNameLookups();\n"
                      "        captureOriginalNames();\n"
                      "        applyItemNames('#skill_list');", 1)

# Strip the 11.9/12.0 XP-bottleneck experiment. Both call sites live in scan(),
# which is hand-maintained and therefore NOT regenerated - without these the
# calls would survive every rebuild and reference functions that no longer
# exist. Kept as one-way migrations; harmless once no Script.txt has them.
src = src.replace("        patchNameLookups();\n        patchLogMessage();\n",
                  "        patchNameLookups();\n", 1)
src = src.replace("\n        capBottleneckMessages();", "", 1)
src = src.replace("\n        annotateBigNumbers();", "", 1)

# Nothing changed since the last pass => nothing to translate. Without this the
# v4.0 selector passes still ran on every tick (including a walk of the whole
# message log), so an idle screen kept paying for scans that could not find any
# new text. patchNameLookups() stays above it: it has to keep polling until the
# game defines the functions it wraps.
if 'nothing changed since last scan' not in body:
    src = src.replace("        captureOriginalNames();\n",
                      "        // nothing changed since last scan\n"
                      "        if (!proseAllDirty && dirtyPanels.size === 0) return;\n"
                      "        captureOriginalNames();\n", 1)
# The reactor readout, the rank line and the clock are rewritten by the game on
# a timer, faster than SCAN_MIN_MS - so the throttled scan leaves them showing
# Chinese most of the time. Run the hot list straight off the observer, outside
# the throttle. Guarded so repeated builds do not stack copies.
if 'translateHot();' not in body:
    src = src.replace("        markProseDirty(records);\n",
                      "        markProseDirty(records);\n"
                      "        // outside the throttle: rewritten faster than SCAN_MIN_MS\n"
                      "        translateHot();\n", 1)
# Needs the RECORDS, which is the whole point: it stamps the nodes that were
# just added instead of scanning a log of ~200 for unstamped ones, and it is
# the only place the time can be read without being up to SCAN_MIN_MS late.
if 'stampMessages(records);' not in body:
    src = src.replace("        markProseDirty(records);\n",
                      "        markProseDirty(records);\n"
                      "        stampMessages(records);\n", 1)

# Maxed skill bars are compacted AFTER the prose pass, so the name is already
# English when we strip " : level 3/3" off it and fold the numbers into the
# Max! slot. Guarded so repeated builds do not stack copies.
if 'compactMaxedSkillBars();' not in body:
    src = src.replace("        applyProseToPanels();",
                      "        applyProseToPanels();\n        compactMaxedSkillBars();", 1)

# Return-arrow mirroring runs after the prose pass, since it keys off the
# TRANSLATED label. Guarded so repeated builds do not stack copies.
if 'mirrorReturnIcons();' not in body:
    src = src.replace("        compactMaxedSkillBars();",
                      "        compactMaxedSkillBars();\n        mirrorReturnIcons();", 1)

# Both of these also run after the prose pass: the location name has to be
# English before it is joined with NBSP, and the bestiary rows have to exist.
if 'nbspLocationNames();' not in body:
    src = src.replace("        mirrorReturnIcons();",
                      "        mirrorReturnIcons();\n        nbspLocationNames();", 1)
if 'highlightBestiaryLinks();' not in body:
    src = src.replace("        nbspLocationNames();",
                      "        nbspLocationNames();\n        highlightBestiaryLinks();", 1)
if 'annotateXpGain();' not in body:
    src = src.replace("        highlightBestiaryLinks();",
                      "        highlightBestiaryLinks();\n        annotateXpGain();", 1)
# After the prose pass: the decision is made on the ENGLISH length, and a name
# still in Chinese is deliberately left undecided until it has been translated.
if 'fitLootNames();' not in body:
    src = src.replace("        annotateXpGain();",
                      "        annotateXpGain();\n        fitLootNames();", 1)
# Runs beside the other cosmetic passes; it early-returns on a getElementById
# once the tab exists, so the per-scan cost is one lookup.
if 'addZonesTab();' not in body:
    src = src.replace("        fitLootNames();",
                      "        fitLootNames();\n        addZonesTab();", 1)
# Beside addZonesTab and for the same reason: it early-returns on a
# getElementById once its button exists, so the per-scan cost is one lookup.
if 'addMaterialsFilter();' not in body:
    src = src.replace("        addZonesTab();",
                      "        addZonesTab();\n        addMaterialsFilter();", 1)
if 'addTradeAllButton();' not in body:
    src = src.replace("        addMaterialsFilter();",
                      "        addMaterialsFilter();\n        addTradeAllButton();", 1)
# Beside mirrorReturnIcons, which works on the same travel options - but this
# one keys off data-travel rather than the label, so it does not care whether
# the prose pass has been past.
if 'colorRestTravel();' not in body:
    src = src.replace("        addTradeAllButton();",
                      "        addTradeAllButton();\n        colorRestTravel();", 1)
# AFTER the prose pass, and that is load-bearing: rewriting a number before
# translation would stop the node matching its own proseExact key, which
# contains the original digits.
if 'sciBigNumbers();' not in body:
    src = src.replace("        colorRestTravel();",
                      "        colorRestTravel();\n        sciBigNumbers();", 1)
# Beside sciBigNumbers, on the same tooltips and for the same reason: it must
# run after the prose pass, because the node it rewrites is the one applyProse
# matches against its own key.
if 'fixSpecColons();' not in body:
    src = src.replace("        sciBigNumbers();",
                      "        sciBigNumbers();\n        fixSpecColons();", 1)
# LAST of the travel passes: it clones the rows' icons, so the mirrored return
# arrow and the rest-location tint have to be on them already.
if 'addActionBar();' not in body:
    src = src.replace("        sciBigNumbers();",
                      "        sciBigNumbers();\n        addActionBar();", 1)
# After the prose pass: the tier is read out of the tooltip, whose label is
# translated by then, and the part name must already be English when prefixed.
if 'prefixCraftingTiers();' not in body:
    src = src.replace("        annotateXpGain();",
                      "        annotateXpGain();\n        prefixCraftingTiers();", 1)

if 'indexOriginalNames(' not in body:
    src = src.replace("        applyProseToPanels();",
                      "        applyProseToPanels();\n        indexOriginalNames();", 1)

# The message log must be translated BEFORE the buttons pass. #message_box_div's
# pairs rewrite punctuation (，-> ", ") and short words (获取了 -> "Gained "),
# which shreds the longer, more specific prose fragments before they can match:
#   "搜刮废墟，获取了 500银钱" -> pairs first  => no fragment matches at all
#                             -> prose first  => "Scavenged the ruins and obtained ..."
# Scoped to that one container on purpose: running applyProse globally this early
# would translate shared fragments like 技能 and break "行动 技能" -> "Activity Skills".
# migrate the earlier single-container wiring to the container list
src = src.replace(
    "        const msgBox = document.getElementById('message_box_div');\n"
    "        if (msgBox) applyProse(msgBox);\n",
    "        translateEarlyContainers();\n", 1)
# migrate the whole-document prose pass to the per-panel dirty-tracked one
src = re.sub(r'^        applyProse\(\);$', '        applyProseToPanels();',
             src, flags=re.M)

# Repair runs of duplicated wiring left behind by the broken guard above.
_dup = ("        // Whole-game prose: descriptions, dialogue, system messages.\n"
        "        applyProseToPanels();\n")
while _dup * 2 in src:
    src = src.replace(_dup * 2, _dup)
for _line in ("        applyProseToPanels();\n", "        indexOriginalNames();\n",
              "        translateEarlyContainers();\n"):
    while _line * 2 in src:
        src = src.replace(_line * 2, _line)

# Migrate the early pass out of its old slot (just before the buttons loop):
# it now has to run before applyItemNames('#skill_list') too, since that rewrites
# bracketed names inside sentences the prose keys depend on.
src = src.replace(
    "        translateEarlyContainers();\n"
    "        for (const [selector, pairs] of Object.entries(buttons)) applySelector(selector, pairs);",
    "        for (const [selector, pairs] of Object.entries(buttons)) applySelector(selector, pairs);", 1)

body = src.split(GEN)[-1]
if 'translateEarlyContainers(' not in body:
    src = src.replace("        applyItemNames('#skill_list');",
                      "        translateEarlyContainers();\n"
                      "        applyItemNames('#skill_list');", 1)

# .item_tooltip and .recipe_tooltip appear BOTH in the buttons object and in an
# applyItemNames call further down, and the buttons loop runs first - so
# realmPairs rewrites 大地级魂魄 into "Earth-Tier魂魄" before the item-name lookup
# can match the whole name. Run the name pass for those two selectors first as
# well; applyItemNames is exact-match, so the later duplicate call simply finds
# nothing left to do.
if 'item names before the buttons pass' not in body:
    src = src.replace(
        "        for (const [selector, pairs] of Object.entries(buttons)) applySelector(selector, pairs);",
        "        // item names before the buttons pass (see builder notes)\n"
        "        applyItemNames('.recipe_tooltip');\n"
        "        applyItemNames('.item_tooltip');\n"
        "        for (const [selector, pairs] of Object.entries(buttons)) applySelector(selector, pairs);", 1)

# ---------------------------------------------------------------- versioning
# The @version / changelog lines live in Script.txt and are preserved as-is by a
# normal rebuild: re-running the builder is not a patch.
#
# BUMP FIRST. The version is raised when work on it STARTS, not when it ends:
#
#     python build.py --bump "what this version will do"   <- first thing
#     ... edit, python build.py, verify, repeat ...
#     python build.py --note "what it actually did"        <- amend, no bump
#
# Bumping last is what corrupted the whole back-catalogue. The release copy is
# named from @version and rewritten on every build, so while @version still read
# 11.4 every 11.5 build overwrote releases/…_11.4.txt. Each file ended up holding
# the NEXT version's body under its own header - file 11.3 shipped 11.4's code -
# and the mislabelling is invisible: the header says exactly what you expect.
# Bumping first means in-progress builds only ever write the OPEN version's file
# and the previous one is frozen the moment its successor is opened.
from decimal import Decimal

# Which version is currently open for writing. Written by --bump; consulted
# below so a plain build can tell "still working on 11.6" (overwrite freely,
# nobody has this file) from "11.5 went out and I forgot to bump" (refuse).
# Deliberately not inferable from the version number alone - both cases look
# identical in Script.txt, which is exactly why this went unnoticed for so long.
OPEN_VERSION_FILE = '.open_version'
open_version = None
if os.path.exists(OPEN_VERSION_FILE):
    open_version = open(OPEN_VERSION_FILE, encoding='utf-8').read().strip() or None


def set_changelog(text, version, note):
    """Insert or replace the changelog line for `version`. Newest-last, matching
    the existing 3.9/4.0/5.0 order. Entries may have wrapped continuation lines
    ("//      ..."), so the block ends at the first non-comment line."""
    lines = text.split('\n')
    start = end = None
    own = None                                   # this version's existing entry
    for n, ln in enumerate(lines):
        if re.match(r'^// \d+\.\d+:', ln):
            if start is None:
                start = n
            end = n
            if ln.startswith('// %s:' % version):
                own = n
        elif end is not None and ln.startswith('//'):
            end = n                              # continuation of the last entry
        elif end is not None:
            break                                # blank line ends the block
    if end is None:
        return text
    if own is not None:
        # Amending: drop the old entry and everything wrapped under it.
        stop = own + 1
        while stop < len(lines) and lines[stop].startswith('//') \
                and not re.match(r'^// \d+\.\d+:', lines[stop]):
            stop += 1
        lines[own:stop] = ['// %s: %s' % (version, note)]
    else:
        lines.insert(end + 1, '// %s: %s' % (version, note))
    return '\n'.join(lines)


_vm = re.search(r'(// @version\s+)(\d+\.\d+)', src)
current_version = _vm.group(2) if _vm else None

if '--bump' in sys.argv:
    i = sys.argv.index('--bump')
    note = sys.argv[i + 1] if len(sys.argv) > i + 1 else ''
    if not current_version:
        print('!! no @version line found; not bumping')
    else:
        old = current_version
        new = str(Decimal(old) + Decimal('0.1'))
        # A release file for the target already existing means that number has
        # been handed out. Re-using it would overwrite someone's copy in place.
        if os.path.exists('../releases/Neko_RPG_Localization_%s.txt' % new):
            print('!! releases/Neko_RPG_Localization_%s.txt already exists.' % new)
            print('!! Not bumping - that version number is already spoken for.')
        else:
            src = src.replace(_vm.group(0), _vm.group(1) + new, 1)
            if note:
                src = set_changelog(src, new, note)
            current_version = new
            open(OPEN_VERSION_FILE, 'w', encoding='utf-8').write(new + '\n')
            open_version = new
            print('version bumped: %s -> %s  (now the open version)' % (old, new))
elif '--note' in sys.argv:
    # Amend the open version's changelog line without bumping. Bumping first
    # means the note is written before the work is done, so it needs rewriting
    # afterwards - otherwise the changelog records the plan, not the patch.
    i = sys.argv.index('--note')
    note = sys.argv[i + 1] if len(sys.argv) > i + 1 else ''
    if not (current_version and note):
        print('!! --note needs a message and an @version line')
    else:
        src = set_changelog(src, current_version, note)
        print('changelog for %s rewritten' % current_version)

open('../Script.txt', 'w', encoding='utf-8').write(src)

# --------------------------------------------------------- installable copy
# The same bytes under a .user.js name. Violentmonkey and Tampermonkey only
# offer one-click install - and only honour @updateURL - when the URL ends in
# .user.js, so a .txt can be pasted but never installed or auto-updated.
#
# Written by the builder rather than copied by hand, and on EVERY build, not
# just the open version's: a hand-kept duplicate drifts, and this one carries
# the @version line that decides whether anybody's copy updates. A stale
# .user.js does not look stale - it just silently stops shipping releases.
#
# Content-identical to Script.txt on purpose. The update URLs sit in the shared
# header, where they are inert for the .txt and load-bearing here; keeping one
# header means there is no second place to forget to bump.
USERJS_NAME = 'NekoRPG-Localizer.user.js'
open('../' + USERJS_NAME, 'w', encoding='utf-8').write(src)

# ------------------------------------------------- versioned release artifact
# Script.txt is the working file; this is the copy to hand out, named for the
# version it contains. Written on every build of the OPEN version so the named
# file can never drift from Script.txt - a stale release carrying a fresh
# version number in its header would be worse than no release file at all.
#
# But once a version is closed (its successor has been opened) its file is
# frozen: whatever a player downloaded under that name must keep matching that
# name forever. Refusing here costs nothing - Script.txt is already written and
# every audit reads that, not the release copy.
release_version = current_version
rel_name = 'Neko_RPG_Localization_%s.txt' % release_version if release_version else None
wrote_release = False
if not release_version:
    print('!! no @version line; release copy not written')
else:
    rel_dir = '../releases'
    os.makedirs(rel_dir, exist_ok=True)
    rel_path = os.path.join(rel_dir, rel_name)
    frozen = os.path.exists(rel_path) and open_version != release_version
    if frozen:
        print('!! releases/%s exists and %s is not the open version.' % (rel_name, release_version))
        print('!! NOT overwriting it - that file has already been handed out.')
        print('!! Starting a new version? Bump FIRST:  python build.py --bump "..."')
    else:
        with open(rel_path, 'w', encoding='utf-8') as fh:
            fh.write(src)
        wrote_release = True

# ------------------------------------------------ archive + prune releases/
# Every release ever built is kept locally in archive/ (gitignored); releases/
# in the repo carries only the newest few, because a 1.3 MB snapshot per version
# outgrows the rest of the project within a year.
#
# Done here rather than by hand so the split cannot decay: two versions after
# anyone stops remembering, releases/ is back to holding everything. Deletion is
# guarded - a file leaves releases/ only once its archived copy is confirmed
# present AND the same size, so a failed copy prunes nothing.
RELEASES_KEPT = 10
_arc_dir = '../archive/releases'
_rel_re = re.compile(r'^Neko_RPG_Localization_(\d+\.\d+)\.txt$')
if wrote_release:
    os.makedirs(_arc_dir, exist_ok=True)
    _names = sorted((f for f in os.listdir(rel_dir) if _rel_re.match(f)),
                    key=lambda f: Decimal(_rel_re.match(f).group(1)))
    _archived = _pruned = 0
    for _f in _names:
        _s, _d = os.path.join(rel_dir, _f), os.path.join(_arc_dir, _f)
        if not os.path.exists(_d) or os.path.getsize(_d) != os.path.getsize(_s):
            shutil.copy2(_s, _d)
            _archived += 1
    for _f in _names[:-RELEASES_KEPT]:
        _s, _d = os.path.join(rel_dir, _f), os.path.join(_arc_dir, _f)
        if os.path.exists(_d) and os.path.getsize(_d) == os.path.getsize(_s):
            os.remove(_s)
            _pruned += 1
    if _archived or _pruned:
        print('archive/releases        : %d archived, %d pruned from releases/'
              % (_archived, _pruned))

# ------------------------------------------------------------------- report
print('pairs loaded            : %d' % len(pairs))
for k, v in srcs.most_common():
    print('    %-26s %d' % (k, v))
print('exact-match entries     : %d' % len(exact))
print('template regexes        : %d' % len(regexes))
print('substring fragments     : %d' % len(frag))
print('<br> lines rebalanced   : %d' % rebalanced)
print('dropped (unpairable)    : %d' % len(skipped))
# Write them out rather than leaving a bare count: these are strings we
# deliberately REFUSE to emit (a wrong guess garbles text in-game), so they need
# to be readable to be fixed. Reason 'structure' = the English splits its lines
# differently from the Chinese; fix by moving <br> in the done_*.tsv English.
with open('_dropped.tsv', 'w', encoding='utf-8') as fh:
    fh.write('reason\tcjk\tzh\ten\n')
    for zs, why, es in sorted(skipped, key=lambda t: (t[1], t[0])):
        fh.write('%s\t%s\t%s\t%s\n'
                 % (why, 'Y' if cjk(zs) else 'n', zs.strip(), (es or '').strip()))
print('component tiers         : %d parts, %d lookup keys'
      % (_tier_parts, len(part_tiers)))
# Loud: a CJK part name with no itemNames entry gets no display key, so that
# row would silently show no tier prefix at all.
if _tier_missing:
    print('!!  %d component names have no itemNames entry - no tier prefix:'
          % len(_tier_missing))
    for _zh in _tier_missing[:10]:
        print('      %s' % _zh)
print('chunk padding kept      : %d keys (space restored at a tag boundary)' % len(pad_kept))
# Loud: each of these renders two words glued together, and the only reason we
# are not fixing it is that the key is ambiguous. It wants a hand-written
# entry, not silence.
if pad_refused:
    print('!!  %d padded chunk keys REFUSED - shared key, padding dropped:'
          % len(pad_refused))
    for _k in pad_refused:
        print('      %-18s %s' % (_k[:18], sorted(repr(x)[:38] for x in _chunk_vals[_k])))
print('merge-exposed promoted  : %d textline_special leading chunks' % len(merge_promoted))
print('backward travel labels  : %d' % len(backward_labels))
# Loud, because the failure is silent otherwise: an untranslated leave_text
# would put Chinese into a Set that is only ever compared against English, and
# that option would simply never mirror.
if _backward_missing:
    print('!!  %d leave_text/custom_text with NO translation - these will never mirror:'
          % len(_backward_missing))
    for _zh in _backward_missing:
        print('      %s' % _zh)
print('conflicts (kept first)  : %d' % len(conflicts))
for zh, a, b, o in conflicts[:8]:
    print('    %s | %s | %s  <-%s' % (zh[:28], a[:34], b[:34], o))
print('\nScript.txt written, %d lines' % src.count('\n'))
print('installable copy        : %s  (identical bytes)' % USERJS_NAME)
if wrote_release:
    print('release copy            : releases/%s  (open)' % rel_name)
elif release_version:
    print('release copy            : NOT written - %s is closed, bump first' % release_version)
