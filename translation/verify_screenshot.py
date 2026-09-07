# -*- coding: utf-8 -*-
"""Simulate applyProse against the exact strings from the reference screenshot."""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

s = open('../Script.txt', encoding='utf-8').read()

def grab(name):
    body = s.split("const %s = Object.assign(Object.create(null), {" % name)[1]
    body = body.split("\n    });")[0]
    out = {}
    for line in body.split('\n'):
        m = re.match(r"^\s+'(.*)': '(.*)',$", line)
        if m:
            out[m.group(1).replace("\\'", "'")] = m.group(2).replace("\\'", "'")
    return out

exact, frag = grab('proseExact'), grab('proseFrag')
keys = sorted(frag, key=len, reverse=True)      # longest-first, as the regex does

# [pattern, replacement, hint] triples
rx_block = s.split('const proseRegex = [')[1].split('\n    ].map(')[0]
RX = []
for line in rx_block.split('\n'):
    m = re.match(r"^\s+\['(.*)', '(.*)', '(.*)'\],$", line)
    if m:
        pat, rep, hint = (g.replace("\\'", "'").replace('\\\\', '\\') for g in m.groups())
        RX.append((re.compile(pat), rep, hint))

FRAG_RE = re.compile('|'.join(re.escape(k) for k in keys))

def apply_prose(t):
    """Mirror applyProse's three stages: exact whole-node match, then whole-node
    template regexes, then curated substrings on whatever Chinese is left."""
    if t.strip() in exact:
        return exact[t.strip()], 'EXACT'

    text = t.strip()

    # applyProse retries the exact lookup with leading separators and wrapping
    # quotes stripped. Missing this here made the tool report false failures on
    # every quoted dialogue option.
    core = re.sub(r'^["\u201c\u201d\'\uff1a:\u3001\uff0c,\uff0e\-\u2013\u2014\s]+', '', text)
    core = re.sub(r'["\u201c\u201d\'\s]+$', '', core)
    if core and core != text and core in exact:
        return exact[core], 'EXACT'

    how = 'frag'
    # Dialogue options render as `"name"`; the anchored regexes must see past
    # the quotes, so strip them for this stage and re-attach after.
    qm = re.match(r'^(["\u201c\u201d\']+)([\s\S]*)(["\u201c\u201d\']+)$', text)
    q_pre, q_post = (qm.group(1), qm.group(3)) if qm else ('', '')
    rx_text = qm.group(2) if qm else text
    for pat, rep, hint in RX:
        if hint not in rx_text:
            continue
        nxt = pat.sub(lambda m: re.sub(r'\$(\d)',
                                       lambda g: m.group(int(g.group(1))), rep), rx_text)
        if nxt != rx_text:
            rx_text, how = nxt, 'REGEX'
            break
    t = q_pre + rx_text + q_post

    def cb(m):
        out = frag[m.group(0)]
        src, start, end = m.string, m.start(), m.end()
        if out.startswith(' ') and start > 0 and src[start - 1] == ' ':
            out = out[1:]
        if out.endswith(' ') and end < len(src) and src[end] == ' ':
            out = out[:-1]
        return out

    t = FRAG_RE.sub(cb, t)
    return format_myriad(t), how


MYRIAD = {'万': 4, '亿': 8, '兆': 12, '京': 16, '垓': 20, '秭': 24,
          '穣': 28, '沟': 32, '涧': 36, '正': 40, '载': 44, '极': 48}
MYRIAD_RE = re.compile(r'(\d+(?:\.\d+)?)\s*([' + ''.join(MYRIAD) + r'])')

def format_myriad(t):
    def cb(m):
        v, e = float(m.group(1)), MYRIAD[m.group(2)]
        if v == 0:
            return m.group(0)
        while v >= 10:
            v /= 10.0; e += 1
        while v < 1:
            v *= 10.0; e -= 1
        v = round(v, 3)
        if v >= 10:
            v /= 10.0; e += 1
        return '%ge%d' % (v, e)
    return MYRIAD_RE.sub(cb, t)

cases = [
    '百方[荒兽森林 ver.][BOSS] 受到了 567419 伤害[暴击][x2.8688]',
    'Neko受到了57967 伤害[反戈]',
    'Neko 未命中',
    '燕岗领排名: 23,436,458,629',
    '脉冲 剑',
    '回到营地',
    '前往 [清野江畔]',
    '荒兽森林',
    '【纳家秘境】',
    '[ 进入 荒兽森林 ]',
    '进入 [荒兽森林 - 1]',
    # --- the corruption cases from the second report ---
    '有一定生命活性的耐极端环境混合物。其类似物曾被用于制造【黑神】套装。',
    '极为珍贵的晶体，使用时随机增加攻击/防御/敏捷1000点或生命5万',
    '制造了 铁锭 x5',
    '解锁新技能: 挖掘',
    # --- second report: untranslated UI bits ---
    '31698纪元 1380年 19日 052:06',
    '大地级六阶 +',
    '属性:',
    '战利品:',
    '= 心之境界 =',
    '燕岗银行 - 提现',
    '纳家练兵场 - 7',
    '合成 : level 24/999',
    '黑暗 I : 一个永远和清朗夜晚一般昏暗的地方',
    '用镐子破坏光环',
    '预期收益/敌人：',
    # --- number formatting ---
    '毛茸茸 吸取了 1.2万 攻击，800防御 ，300 敏捷 [同调]',
    '276.47万',
    '4.489垓',
    '167.24京',
    '1120兆',
    '万载冰髓锭',          # no digit -> must stay a name, not become a number
    # --- degenerate-regex class (v8.9) ---
    # '^(.+?)！$' -> '$1!' matched any node ending in ！, swapped the punctuation
    # and broke, so no fragment key ending in ！ could ever match again - 287 of
    # them. Every audit passed throughout. These pin the class: if a pattern
    # with no ideograph ever gets emitted again, these fail first.
    '青花鱼 上钩了！',
    '瞄准有用的物品，点击纳可驱动钩爪，抓上来！',
    '更好地收割绝音蕨！',
    # --- HTML-producing ${} slots ---
    # format_money() (v8.4) and lvl_display (v9.2) expand to MARKUP, which splits
    # the text node - so the whole-node regex built from the template can never
    # match, and only the literal fragments can save it.
    'Neko 境界突破，达到',
    # --- display quotes vs anchored regexes (v9.3) ---
    # display.js renders every dialogue option as `"${name}"`. Every template
    # regex is anchored ^...$, so the quotes alone stopped them matching and
    # silently disabled "和 X 对话" -> "Talk with X" for the whole game.
    '"和 枫杏红 对话"',
    '"使用 [核心反应堆]"',
    # --- combat spec tag inside a concatenated literal (v9.4) ---
    # main.js builds "...点伤害[领域]" as one literal, so the tag shares a text
    # node with the words around it and only a fragment can reach it. 领域 is
    # typed `slot` in 00_morphemes, which makes it EXACT-only - fine on its own,
    # useless inside a longer node. 66 of the 67 spec tags were bare fragments
    # already; this was the one that wasn't.
    'Neko受到了1230000点伤害[领域]',
    # --- anchored regex vs an APPENDED node (v9.6) ---
    # type_tooltip.innerHTML += ` [基础值: x${...}]` glues onto the text already
    # in the node, so ^\[基础值: x(.+?)\]$ can never match. Only a fragment
    # reaches it. Test the FULL line, not the bracket on its own.
    '攻击速度 x0.785 [基础值: x0.5]',
    # --- optional trailing interpolation (v9.7) ---
    # `经验${E_modi==1?"":`(压级-…)`}` renders EMPTY in the normal case, but the
    # generated pattern ended in (.+?) and demanded a character - so the rule
    # never fired and v4.0 chewed the line into "Used了 … Gained … 经验".
    # BOTH branches must pass. Uses 铁锭 because it is a prose fragment;
    # 基础进化结晶 is resolved by applyItemNames, which this tool does not model.
    '使用了 铁锭 , 获取了 1.00e11 经验',
    '使用了 铁锭 , 获取了 1.00e11 经验(压级-50%)',
    # --- crafting component categories (v9.9) ---
    # `选择一个[${ComponentNameMap[...]}]` splices the category into a longer
    # node. All 13 category names are `component` rows in 00_morphemes.tsv, i.e.
    # EXACT-only, so none could resolve and EVERY crafting dropdown read
    # "Select one [轮锋]". Bracket-scoped fragments; the compound item names
    # (凝胶轮芯 = Gel Wheel Hub) must keep working alongside them.
    '选择一个[轮锋]',
    '选择一个[头部外甲]',
    '凝胶轮芯',
    # --- name inserted as $2 by a generic rule (v10.0) ---
    # `x${mult} ${MulNameMap[k]} 经验获取` - the generic rule captures the NAME
    # and inserts it verbatim, and fragments run too late to rescue it. Fixed
    # with scoped rules carrying a LONGER hint so they sort ahead of it.
    'x2 全部 经验获取',
    'x2 技能 经验获取',
    ', x8411.01 全部 经验获取',
    '[无]',
    # --- regexMustComplete vs myriad units (v10.1) ---
    # The v9.1 early-pass guard rejected any substitution that still held an
    # ideograph - but format_number emits "972万", which stage 4 converts. So
    # the milestone rule was accepted for SMALL values and rejected for large
    # ones, and "基础Attack,Defense,Agility + 9.72e6" survived the v9.1 "fix".
    # Testing with "+ 8000" is what hid it: pin a MYRIAD value.
    '基础攻击,防御,敏捷 + 972万',
    '基础攻击,防御,敏捷 + 4.89垓',
    # --- several XP awards sharing ONE node (v10.4) ---
    # A dialogue can grant multiple skills, and the lines are appended without a
    # <br>, so the whole-node exact entry for the first can never match. Only
    # bracket-scoped fragments reach it. Pin the COMPOSITE, not one line.
    '【水元素亲和】获取了3997万经验！【焰海霜天[领域二重]】获取了1.68e24经验！',
    # --- display strings held in plain ARRAYS (v10.5) ---
    # `目前的时段为 ${MM1[C_time]}，` - MM1 is a let-array, not an object, so
    # the *Map scan never saw it and all 8 periods printed in Chinese.
    '目前的时段为 23-45点，',
    '目前的月相为 满月，',
    # --- two halves of ONE sentence sharing a merged node (v11.2) ---
    # Nabu's dialogue tail 我找你们找了 plus the appended ${age}年了呐！！ land in
    # the same text node. Each had been translated as a COMPLETE thought, so
    # they concatenated into "…for you—It's been 41 years!!" - the sentence
    # said twice. Halves that share a node have to compose, not each stand
    # alone; this case fails the moment one of them is rewritten as a sentence.
    '我找你们找了41年了呐！！',
    # --- family roster: single-character labels that are WHOLE nodes (v11.5) ---
    # <th>境界</th>, <th>突破</th> and the strategy <select>. These are the
    # dangerous shape: two-character words that also live inside dozens of
    # longer phrases (境界突破, 突破思路), so they may only ever be EXACT entries.
    # If any of these five starts resolving as a fragment, this file is the
    # wrong place to notice - but if one stops resolving at all, it is the
    # right place, because nothing else in the suite reads index.html headers.
    '境界',
    '人数',
    '突破',
    '死亡',
    '培养策略',
    '[3]秘境探险',
    '[5]九死一生',
    # The bankruptcy line splits at format_money(), so the two literals either
    # side must each stand on their own. The English used to put the money slot
    # first, which silently disabled add_html_slot_frags() and left the whole
    # sentence Chinese - pin BOTH halves as the DOM actually delivers them.
    '因无力负担 500 个新生儿产生的',
    '费用，纳可破产了！',
    # --- activity status line, WITH the animated dots (v11.6) ---
    # #action_status_div is set to activities.js action_text, then
    # start_activity_animation() appends "." every 600ms up to "..." and starts
    # over. So the node the player sees is the phrase PLUS 0-3 dots, and any
    # exact entry for the bare phrase can never match it - all six of these have
    # to work as fragments. Pinned with dots for exactly that reason.
    #
    # 收集木头 reached a player as "Collect木头": 收集 is a fragment ("Collect")
    # and consumed the front, and 木头 occurs exactly ONCE in the whole game
    # source, so nothing else had ever given it an entry. The whole phrase is
    # the entry now. Nothing audits activities.js - the prose extractor pulled
    # 2 of its 8 Chinese strings - so this list is the only thing watching it.
    # --- gem sci-notation, baked into the TEXT (v13.5) ---
    # Was a runtime pass; now part of the translation, so it is greppable in
    # the shipped English. Pinned because a re-translation of these rows could
    # silently drop the annotation and nothing else would notice.
    '仅仅一颗就可以掀起小范围的腥风血雨，使用时随机增加攻击/防御/敏捷5亿或生命1000亿',
    # The currency lines must NOT gain one: the number is glued to its unit
    # (1,000,000C), so an annotation would split the token.
    "血洛大陆的通用钱币。1Z=1000X=1'000'000C.",
    # --- V3.41c new content (v13.1) ---
    # The new 反击 spec tag is the v9.4 class arriving again: display.js splices
    # spec tags into combat-log lines, so an exact-only entry could never fire
    # inside the longer node. It lives in 05_ui.tsv (FORCED_FRAG) for that
    # reason - pinned in a full log line, not bare, because bare is exactly the
    # form that would pass either way.
    'Neko受到了1230000点伤害[反击]',
    '红宝石近卫 受到了 8.72e11 伤害[反击]',
    # --- skill TOOLTIP contents, now hot while hovered (v13.0) ---
    # update_displayed_skill_bar() rewrites these on every tick, so they
    # flickered back to Chinese while the tooltip was open. Being on the hot
    # list only helps if each resolves in ONE applyProse pass - otherwise it
    # just re-renders Chinese faster. NOT pinned here: 已满级, which is
    # v4.0-only and written once when a skill maxes, so it never stutters.
    '经验获取: x1704855.1',
    '经验消耗蠕变: x1.6',
    # --- stance descriptions that quote a stance NAME (v12.9) ---
    # #stance_list_div lists the stance names BEFORE the descriptions that
    # quote them, and applySelector applies every pair in order - so the name
    # pair fired inside the sentence and the whole-sentence pair could never
    # match. Pinned as the raw source text: if the early exact pass stops
    # resolving these, the buttons loop shreds them again.
    '强大的单体攻击秘法。0级状态即为【映星花·巨星】的极限。',
    '群体攻击秘法。0级即为【映星花·繁星】的极限，且不存在无法命中4个目标的虚弱期。',
    # --- skill bar names, now on the no-stutter list (v12.4) ---
    # update_displayed_skill_bar() rewrites `${skill.name()} : level N/M` on
    # every XP update, so the Chinese name reappeared between scans. Being on
    # the hot list only helps if the whole node resolves in ONE pass - otherwise
    # it just re-renders Chinese faster. Evolving names included: those are the
    # ones that change as the skill levels, so they get re-rendered most.
    '银霜月轮·二重 : level 51/120',
    '砍伐 : level 12/60',
    '战斗 : level 18/100',
    # --- textline_special merged onto the dialogue line (v12.2) ---
    # main.js: `let displayed_text = textline.text;` then
    # `displayed_text += textline_special(spec);` with NO <br> between, so the
    # dialogue's last segment and the special's first segment share one text
    # node. The special's exact entry could never match, and the fragment stage
    # translated only the speaker tag and the punctuation - which is the tell
    # for this class: fluent English with one Chinese island.
    # Pinned WITH a speaker prefix, because bare is exactly the form that
    # already worked and would hide a regression.
    '[枫杏红]我说，“饵料”已经布下！！',
    '[纳布]你姐姐的事，不用太担心。',
    # --- realm line, now on the no-stutter list (v12.1) ---
    # #character_level_div. Rewritten only `if(did_level)`, which is rare until
    # you hit an XP cap - at the cap add_xp() returns the bottleneck string
    # instead of nothing, that truthy value is passed straight in as did_level,
    # and the line is rewritten every tick. It has to keep resolving in one
    # pass or the hot-list entry just re-renders Chinese faster.
    '境界 : 天空级一阶',
    '境界 : 云霄级巅峰',
    '收集木头..',
    '练习奔跑.',
    '练习游泳..',
    '感应水元素...',
    '抡着镐子.',
    '钓鱼...',
    # --- V3.42 / V3.43 (game update merged at script v15.3) ---
    # New 4-5 drops and the Blood Diamond line. Compositional, so these are
    # really a check that the new morphemes compose the way the glossary says.
    'C4·能量核心',
    '灰暗军魂',
    '血凝晶',
    '亮青碎片',
    '鲜红碎片',
    '血钻锭',
    '血钻轮锋',
    'C6·吹火药剂',
    'C6·压制药剂',
    '血峰限制器',
    '血峰增幅器',
    '精英炼金药剂-吹火',
    '熔炼血钻(x2)',
    # The three interpolated V3.43 log lines, rendered with real values. A
    # template that never matches is silent - it just leaves Chinese on screen -
    # so these are here rather than trusted from the pattern alone.
    '[3x限制器]本区光环已被降低60%!',
    '[100x增幅器]本区光环已被增幅2.00!',
    '纳可 将 撼瀚野熊 的攻击 延迟了0.5轮![吹火 C6].',
    # 撼瀚野熊 gained a rank plus in V3.42, so its realm line changed.
    '云霄级四阶 ++',
    # --- V3.44 (game update merged at script v16.8) ---
    # Ranks from 云霄级四阶 up are split into an early and a late phase. Keyed
    # WITH the separator so the spacing matches the game's other dot-joined
    # names, and so a bare 前期/后期 cannot fire inside ordinary prose.
    '云霄级四阶·前期',
    '云霄级巅峰·后期',
    '境界 : 云霄级四阶·前期',
    # The family power-unlock readout, and its log line. The realm name in the
    # log arrives inside a coloured span, so the template matches only the
    # leading chunk - anchoring on the whole sentence would never fire.
    '解锁家族的',
    '需求战力',
    '对应排名',
    '因 纳可 的战力超过了 6660亿 , 家族系统开放了 ',
    # Two soft-cap exponents were rebalanced, which staled their keys.
    '新生儿超过1亿，花费受到二重软上限限制(^2.0)',
    '新生儿超过1兆，花费受到三重软上限限制(^2.5)',
    # The TAIL of the unlock line. index.html splits the sentence around
    # <span id='family_next_realm'>, so this is a text node of its own and the
    # bare 境界 entry cannot reach it: applyProse strips trailing quotes from a
    # node, but not a trailing colon, so it never reduces to 境界.
    '境界:',
    # --- reported: 清野瀑布 wf2 after DeathCount-1 (script v17.2) ---
    # main.js splices the death count into the middle of the sentence and the
    # <br> ends the text node, so the prose entry written across the <br> could
    # never match and the tail rendered as "3次生死呢，". Both the counted form
    # and the count-of-one form are here, since English needs plural agreement
    # and each is a separate rule.
    '如今也算是历经了1次生死呢，',
    '如今也算是历经了3次生死呢，',
    '也知道了父亲大人的话是什么意思。',
    # The STATIC wf2 line, which was never broken - kept so a change to the
    # rules above cannot quietly capture it.
    '如今也算是历经了一次生死呢，',
]
ok = 0
for c in cases:
    out, how = apply_prose(c)
    clean = not re.search(r'[一-鿿]', out)
    ok += clean
    print('%s %-6s %s\n        -> %s\n' % ('OK ' if clean else '*** ', how, c, out))
print('%d/%d fully translated' % (ok, len(cases)))
