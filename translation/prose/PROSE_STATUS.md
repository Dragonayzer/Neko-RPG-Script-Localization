# Prose translation status — ✅ COMPLETE

All prose translated. Source dumps: `_todo_<file>.tsv` (frozen). Output: `done_*.tsv`.
Keying: item/enemy/location/character/skills files key by SOURCE LINE; dialogues & main & display
key by _todo ROW NUMBER (their srclines collide — multiple fragments per line). Headers note which.

| file | output | status |
|---|---|---|
| items.js | done_items.tsv (87) + items_desc.tsv (264 earlier) | ✅ |
| enemies.js | done_enemies_1..6.tsv (590) | ✅ |
| locations.js | done_locations.tsv (331) | ✅ |
| dialogues.js | done_dialogues_1/2/3.tsv (438) | ✅ |
| main.js | done_main.tsv (277) | ✅ |
| display.js | done_display.tsv (164) | ✅ |
| character.js | done_character.tsv (32) | ✅ |
| skills.js | done_skills.tsv (31) + glossary/03_skills.tsv | ✅ |
| traders/activities/crafting/misc | done_smalltails.tsv (8) | ✅ |
| combat_stances.js | (terminology only) | ✅ |

Realm-tier badge dyn lines in enemies.js (~85) intentionally skipped — they auto-compose from
00_morphemes. Dynamic (${}) strings are translated with the ${...} preserved verbatim; at Script.txt
rebuild they need regex/substring wiring (rendered value replaces the interpolation), NOT exact-match.

TRANSLATION COMPLETE. Terminology (glossary/*.tsv) + prose (done_*.tsv) both done.
Next project phase: rebuild Script.txt from all glossaries + done files (apply DECISIONS.md; respect
ordering/scoping warnings; ${}-strings → regex pairs).
