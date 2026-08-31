# Resolved translation decisions (ambiguities settled from game source)

These were flagged uncertain (by DeepSeek / the user) and resolved by reading the
actual in-game descriptions in NekoRPG/src/locations.js. Recorded here as the single
source of truth; apply on Script.txt rebuild.

## Locations

| 中文 | English | Verdict | Evidence |
|---|---|---|---|
| 赫尔沼泽 | **Hull Swamp** | keep | 赫尔 appears only as this place name — pure phonetic proper noun, no lexical meaning. Transliteration correct. |
| 声律城 | **Shenglü City** | keep | 声律 is a fief name (声律领), city = its 领主城, parallel to 燕岗领/清波领/圣荒领/兰陵领. Proper name, NOT "Melody City". |
| 幻境核心·现世 | **Illusory Realm Core · Reality** | keep | "五层幻境全部破碎，此地即是幻境的真正核心" — the layer where illusion breaks and reality shows. "Reality" > Present/Mortal World. |
| 鲜血峰 | **Blood Peak** | keep | "争斗不断，血流漂杵" (bloodbath idiom). 血=Blood convention. Clean name. |
| 天外飞船 | **Alien Spaceship** | CHANGED (was Extraterrestrial Spaceship) | B-arc is hard sci-fi (lasers, mechs, B9 warship). User chose concise register. |
| 毬毬山谷 | **Furball Valley** | CHANGED (was Qiuqiu Valley) | Whimsical proper name (毬=play-ball; Furball enemies live there). User chose cute/thematic. NB: "Furball" now intentionally covers both 茸茸 (creatures) and 毬毬 (valley) — different words, same English, OK in context. |

## Script.txt entries to update on rebuild (spelled-out variants)
- `天外飞船 - 右上房间` → Alien Spaceship - Upper Right Room
- `天外飞船 - 歧路` → Alien Spaceship - Fork
- `天外飞船` → Alien Spaceship
- `毬毬山谷 - 歧路` → Furball Valley - Fork
- `毬毬山谷` → Furball Valley

(Sub-zones like `天外飞船 - 1..5/X` inherit via the substring matcher once the base is updated.)
