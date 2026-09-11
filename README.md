# NekoRPG Game Text Localizer

A userscript that plays **[NekoRPG](https://btly0711.github.io/NekoRPG/) in English.**

NekoRPG is a Chinese idle RPG — a deep-modified mod of Yet-Another-Idle-RPG, by
[btly0711](https://github.com/btly0711/NekoRPG). This script translates it in the
page, as you play: the UI, every item, enemy, skill and location name, and all of
the prose — descriptions, dialogue, combat log, system messages.

It is a **translation layer, not a fork.** The game is loaded from its own site and
runs its own code; nothing here is a copy of it, and it keeps working when the game
updates — unrecognised text simply stays Chinese until the glossary catches up.

Current script: **v17.6**, tracking game version **V3.46**.

---

## Install

1. Install a userscript manager — [Violentmonkey](https://violentmonkey.github.io/)
   or [Tampermonkey](https://www.tampermonkey.net/).
2. **[Click here to install the script.](https://raw.githubusercontent.com/Dragonayzer/Neko-RPG-Script-Localization/main/NekoRPG-Localizer.user.js)**
   Your manager should open its own install page; confirm it.
3. Open [the game](https://btly0711.github.io/NekoRPG/). It should come up in English.

It updates itself from there. Your manager re-checks this repo periodically —
daily by default — and reinstalls when the version here is newer than yours. To
pull one immediately, hit **Check for updates** on the script in your manager.

None of this touches your save. The save is the game's own, kept by the game.

---

## Troubleshooting

### The game is still in Chinese

The browser is probably blocking user scripts, rather than anything being wrong
with the script. Chromium-based browsers — Chrome, Edge, Opera, Brave — require
you to allow them explicitly:

- Open your extensions page (`chrome://extensions`, `edge://extensions`).
- Find your userscript manager, open its **Details**, and turn on
  **Allow user scripts**.
- On older builds there is no such toggle and the switch is **Developer mode**,
  at the top right of the extensions page instead.

Violentmonkey and Tampermonkey both detect this and show a warning on their
dashboard telling you which one your browser wants. Firefox needs neither.

If the toggle is already on, check that the script is enabled in your manager and
that you are on `btly0711.github.io/NekoRPG/` — those are the only addresses it
matches.

### Some of it is in Chinese

Expected, briefly, after the game updates: new text stays in its original
language until the glossary catches up, which is the design rather than a
failure. If it persists past the next release, **please open an issue** — a
screenshot or the Chinese text itself is enough to find it.

The one thing that is *not* a bug: renaming your character. Lines the game builds
around her name match on the default, so a custom name will show through in
English text.

### Going back to an older version

The **ten most recent** builds live in [`releases/`](releases/) — plain `.txt`
snapshots, byte-identical to what shipped. (Older ones are archived outside the
repo; open an issue if you need one.)

Paste one over the script body in your manager's editor **and delete the
`@updateURL` and `@downloadURL` lines from its header.** Leave them in and the
manager will notice this repo is newer and pull you forward again, which is the
opposite of pinning.

### A change you made keeps disappearing

Updating replaces the whole script body, edited toggles included. See
[Turning things off](#turning-things-off).

---

## What you get

**The translation.** ~4,700 whole-string matches, ~3,900 name and term fragments,
and ~240 templates for lines the game assembles at runtime (`Neko delayed Vastshaker
Wild Bear's attack by 0.5 rounds!`). Chinese myriad units are converted to notation
that reads at a glance — `276.47万` becomes `2.765e6`.

**Quality-of-life, on top of the translation.** These are the parts that fix things
English exposed, or that the game's own UI leaves to memory:

| | |
|---|---|
| **Location action bar** | A shortcut row above the location list: exits on the left, things you can *do* in the middle, and four pinned slots on the right — shop, rest, crafting, return to safe zone — dimmed where the location has none, so the controls you reach for most never move. |
| **Zones tab** | A fifth journal tab: the bestiary filtered to just its clickable zone rows. A slim teleport menu instead of scrolling ~560 entries. |
| **Mats filter + Add all** | A fifth trader category — the Misc bucket with the bulky Parts rows hidden — and a button that puts everything currently on screen into the buy list. Mats + Add all is a one-click crafting restock. |
| **Message timestamps** | Real local time on every log line, stamped as it arrives. Combat and loot are skipped, since those arrive in bulk. |
| **Maxed skill bars** | A maxed bar goes flat dark green with its progress strip collapsed; a bar that is always 100% full carries no information by being full. |
| **Bestiary zone links** | The clickable zone rows get one colour per act, so they stop looking identical to the hundreds of enemy rows around them. |
| **Rest destinations** | Travel links leading somewhere you can sleep are painted the same colour the game already uses for its own return-to-bed link. |
| **Directional arrows** | Return options get an arrow that actually points back. The game gives every exit the same right-pointing signpost. |
| **Readable numbers** | Bestiary tooltips put raw spec integers into scientific form, but only where it is *lossless and shorter* — a number carrying real precision is left exactly as it is. |
| **Layout repairs** | Several screens — the Deepfrost engine especially — were sized for Chinese, which is about two characters where English needs a word. Those are re-tuned with CSS. |

Every one of these can be switched off individually, and
`ENABLE_VISUAL_OVERRIDES = false` turns off the whole category at once, leaving a
script that only translates and a game that looks exactly as it shipped.

---

## Turning things off

Near the top of the script, after the changelog, is a block of toggles. Edit them
in your userscript manager and save.

```js
// ---- TRANSLATION ----
const ENABLE_ITEM_NAMES  = true;   // item-name layer
const ENABLE_PROSE       = true;   // descriptions, dialogue, messages — the bulk
const ENABLE_NUMBER_FORMAT = true; // 972万 -> 9.72e6

// ---- VISUAL OVERRIDES ----
const ENABLE_VISUAL_OVERRIDES = true;   // master switch for everything below
```

Each toggle has a comment above it explaining what it does and why it is set the
way it is. A few worth knowing about:

- `MESSAGE_TIMESTAMP_DATE` — off by default. The log is chronological, so the date
  is the same on nearly every line, and including it costs vertical space.
- `MESSAGE_TIMESTAMP_SKIP` — which message groups go unstamped. Defaults to combat
  and loot.
- `TRAVEL_ICON` — any Material Icons ligature; `'forward'` by default.
- `BESTIARY_ACT_COLORS` — the six per-act colours.
- `FAMILY_SCROLL_DEBUG` — diagnostic logging for the family roster's scroll
  restore. Off; turn it on only if the drift comes back.

⚠️ **An update overwrites your edits**, since it replaces the whole script body.
If you keep a customised set of toggles, either note them down somewhere before
updating, or turn auto-update off for this script in your manager's settings and
pull new versions by hand.

---

## How it works

The script watches the page with a `MutationObserver` and rewrites text nodes.
Matching runs in three stages, in this order:

1. **Exact** — the whole text node is one known string. Most of the corpus.
2. **Template regex** — anchored patterns for lines the game interpolates values
   into. Ordered by hint length, longest first, so the most specific wins.
3. **Fragment** — substring replacement for names and terms, longest first.

Ordering is the whole game. A name that is a substring of a longer name has to lose
to it, and a fragment that fires before the exact match for the line it sits in
shreds that line. Most of the complexity in the builder is about guaranteeing that
order.

**Performance** matters here: this is an idle game that redraws constantly. The hot
path contains **zero layout-forcing reads** — no `offsetHeight`, no
`getBoundingClientRect`, no `getComputedStyle` — which is asserted by a test rather
than left to discipline. Panels that must be translated before the first paint run
off the observer as a microtask; everything else is throttled.

---

## Building from source

`Script.txt` and `NekoRPG-Localizer.user.js` are both **generated**, and are the
same bytes. Do not edit the translated dictionaries inside them — they are
overwritten on the next build. Edit the glossary or prose files and rebuild:

```sh
cd translation
python build.py --bump "what this version will do"   # bump FIRST, always
python build.py                                      # build
python build.py --note "what it actually did"        # amend the changelog
```

Bumping first is enforced: the builder refuses to overwrite a released version.

Python 3 with no third-party dependencies; Node is needed only for the JS tests.

### Layout

```
NekoRPG-Localizer.user.js   what people install — generated
Script.txt                  the same bytes, the working copy — generated, ~13.7k lines
releases/                   the ten newest .txt snapshots
archive/releases/           every release ever built — local, gitignored
translation/
  build.py              the assembler; also holds the runtime JS
  glossary/*.tsv        terminology, in application order (00 → 12)
  prose/                _todo_*.tsv (frozen source dumps) + done_*.tsv (English)
  audit_*.py            coverage checks against the game source
  uitest_*.js           behavioural tests for the visual layers
  verify_screenshot.py  end-to-end cases: Chinese in, English out
```

Glossary files are `zh <TAB> en <TAB> optional note`, with `␣` standing in for a
literal space. The number prefix is the order they are applied in, and it is
load-bearing.

The `prose/` pairs are **frozen and positional** — `done_*.tsv` keys are source
line numbers or row indices into the matching `_todo_*.tsv`. When the game rewords
a string, fix the `_todo` row *in place*. Regenerating a `_todo` file renumbers it
and silently re-pairs every English string to a neighbouring Chinese one.

### Tests

```sh
cd translation
python verify_screenshot.py        # end-to-end: real strings in, English out
python audit_coverage.py           # every CJK literal in the game source
python audit_dialogue.py           # dialogue names + text chunks
python audit_locations.py          # travel text, activities, dialogue entries
python audit_messages.py           # log-message renderings
python audit_skills.py             # skill names, descriptions, milestones
python audit_embedded.py           # names the game reads back out of the DOM
node uitest_actionbar.js ../Script.txt      # and the other six uitest_*.js
node jscheck.js ../Script.txt "some 中文"    # what the built script does to one string
```

`jscheck.js` is the tiebreaker. Every other checker is a Python re-implementation
of the matcher, and those have been wrong before; `jscheck` runs the actual
generated tables in a real JS engine against one string.

---

## Keeping up with game updates

The game updates every week or two. The process:

1. `git fetch` the game repo, read `changelog.html`.
2. **Grep the diff against our DOM hooks.** The UI tests run against mocks and stay
   green through a renamed class or id — the diff is the only thing that catches it.
3. Merge, translate what is new, fix what went stale.
4. Run the suite above; every audit should end at zero.

New content goes into a **new** frozen `_todo_v<version>.tsv` / `done_v<version>.tsv`
pair, never by regenerating an existing corpus.

---

## Known limitations

- **A clean coverage report means every string the extractor *found* is covered —
  not that it found everything.** Five of Sayuki's lines went untranslated for
  months because they are `log_message` calls inside an inline click handler in
  `index.html`, somewhere the prose extractor never reached. They surfaced only
  when the game reworded them.
- A few strings are assembled from pieces at runtime in ways no single template can
  match. Those are handled case by case, and a line that reads oddly at a seam is
  usually one of them.
- Renaming your character stops `${character.name}` lines from matching her name.
  The fragment is the default name, so a custom one simply falls through — correct
  behaviour for a name, and the reason for the note under
  [Troubleshooting](#some-of-it-is-in-chinese).

---

## License

[MIT](LICENSE), for the translation and the tooling in this repository.

That covers this repository's own work — the English text, the glossaries, the
builder and the tests. It does not and cannot cover NekoRPG itself: the game, its
Chinese text and its assets belong to its author, and none of them are reproduced
here. What is here is a rendering of that text into English, applied to the game in
your own browser as you play.

---

## Credits

**NekoRPG** is by [btly0711](https://github.com/btly0711/NekoRPG), a deep-modified
mod of Yet-Another-Idle-RPG. All game text, names and story are theirs; this
repository holds only the English rendering of it and the tooling that produces it.

Translation and tooling by [Dragonayzer](https://github.com/Dragonayzer), with
[Claude Code](https://claude.com/claude-code).
