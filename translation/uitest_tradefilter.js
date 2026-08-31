// addMaterialsFilter(): the 5th trader category button and the rule it drives.
// Run against a BUILT script:  node uitest_tradefilter.js ../Script.txt
//
// Like the Zones tab, this ADDS UI rather than restyling it, so most of the
// assertions are about fitting into machinery we do not own: set_active_button's
// no-child-elements rule, the 400px button row, and the game's own three
// display variables. The one that matters most is the last: the rule has to
// hide Parts and ONLY Parts, since hiding materials too would leave the button
// showing an empty list and looking broken rather than wrong.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8').split('\r\n').join('\n');

function slice(name) {
  const s = src.slice(src.indexOf('    function ' + name + '() {'));
  const end = s.indexOf('\n    }\n');
  if (end === -1) throw new Error('could not slice ' + name);
  return s.slice(0, end + 7);
}
const consts = ['MATERIALS_BTN_ID', 'MATERIALS_ONLY_CLASS', 'TRADER_CAT_W',
                'ADD_ALL_BTN_ID', 'TRADE_ROW_SEL', 'ALL_AMOUNT_SEL',
                'TRADE_BTN_W', 'ADD_ALL_MAX'].map(
    // [\s\S]*?; rather than [^\n]+: TRADE_ROW_SEL is long enough to be wrapped
    // onto its own line, and a line-based grab would silently miss it.
    (n) => src.match(new RegExp('const ' + n + ' =[\\s\\S]*?;'))[0]).join('\n');
const catIds = src.slice(src.indexOf('    const TRADER_CAT_IDS = ['),
                         src.indexOf('];', src.indexOf('const TRADER_CAT_IDS')) + 2);
const filterSrc = consts + '\n' + catIds + '\n' + slice('addMaterialsFilter');
const addAllSrc = consts + '\n' + slice('tradeAddAllDisplayed') + '\n' +
                  slice('addTradeAllButton');

// The eval'd blocks declare these with const, and a const inside eval does NOT
// leak to the enclosing scope the way a function declaration does - so the
// harness has to read the values for itself rather than borrow them.
function strConst(n) {
  return src.match(new RegExp('const ' + n + " =\\s*'([^']+)'"))[1];
}
const ADD_ALL_BTN_ID = strConst('ADD_ALL_BTN_ID');
const TRADE_ROW_SEL = strConst('TRADE_ROW_SEL');
const ALL_AMOUNT_SEL = strConst('ALL_AMOUNT_SEL');
const ADD_ALL_MAX = Number(src.match(/const ADD_ALL_MAX = (\d+)/)[1]);

// CSS assertions must look inside the styleOverrides template ONLY. Searching
// the whole file matches the changelog header too - every rule discussed there
// appears verbatim - and a regex that runs off into prose reports nonsense
// rather than failing cleanly. This cost a debugging round; hence the slice.
const CSS = (function () {
  const start = src.indexOf('styleOverrides.textContent = `');
  return src.slice(start, src.indexOf('`;', start));
})();

let bad = 0;
function expect(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) bad++;
  console.log('  ' + (ok ? 'ok  ' : 'FAIL') + ' ' + String(what).padEnd(42) +
              JSON.stringify(got) + (ok ? '' : '  want ' + JSON.stringify(want)));
}

// --- a mock trader category row ---------------------------------------------
function mkEl(id) {
  return { id: id, style: {}, className: '', children: [], childNodes: [],
           classList: { _s: new Set(), add(c) { this._s.add(c); },
                        remove(c) { this._s.delete(c); },
                        contains(c) { return this._s.has(c); } } };
}
function harness(env) {
  env = env || { master: true, on: true };
  const ids = ['trader_category_all', 'trader_category_equipment',
               'trader_category_usable', 'trader_category_other'];
  const els = {};
  ids.forEach((i) => { els[i] = mkEl(i); });
  const bar = mkEl('trader_category_buttons');
  bar.children = ids.map((i) => els[i]);
  bar._listeners = [];
  bar.addEventListener = (t, fn) => bar._listeners.push(fn);
  bar.appendChild = (node) => {
    bar.children.push(node);
    node.parentNode = bar;
    els[node.id] = node;
  };
  ids.forEach((i) => { els[i].parentNode = bar; });
  const list = mkEl('trader_inventory_div');
  // The game sets its filters through CSS custom properties on <html>, and the
  // Materials button has to drive the same three - not a private mechanism of
  // ours - or the game's own buttons could not take the panel back afterwards.
  const vars = {};
  const document = {
    documentElement: { style: { setProperty: (k, v) => { vars[k] = v; } } },
    getElementById: (i) => (i === 'trader_category_buttons' ? bar
                          : i === 'trader_inventory_div' ? list : (els[i] || null)),
    createElement: () => mkEl(''),
  };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const TRADER_MATERIALS_FILTER = env.on;
  eval(filterSrc);
  addMaterialsFilter();
  addMaterialsFilter();            // idempotency: must not append twice
  return { bar: bar, els: els, list: list, vars: vars };
}

console.log('addMaterialsFilter');
let h = harness();
const order = h.bar.children.map((c) => c.id);
expect('appended once, after the game four', order,
       ['trader_category_all', 'trader_category_equipment',
        'trader_category_usable', 'trader_category_other',
        'tl_trader_category_materials']);
// set_active_button requires `clicked_element.children.length == 0` - an
// element child here would silently cost the button its active highlighting.
const btn = h.els['tl_trader_category_materials'];
expect('no element children (set_active_button)', btn.children.length, 0);
expect('carries the game button class', btn.className, 'trader_category_button');
expect('label is already English', btn.textContent, 'Mats');

// The row is exactly 400px: 5 widths + 1px margin either side of each. The
// game ships four at 98px, which already fills it, so a fifth cannot simply be
// added - all five have to come down together or the row wraps to two lines.
const w = h.bar.children.map((c) => parseInt(c.style.width, 10));
expect('all five widths equal', w, [78, 78, 78, 78, 78]);
expect('widths + margins == 400px panel',
       w.reduce((a, b) => a + b, 0) + 2 * w.length, 400);

// --- the filter, driven through the delegated listener ----------------------
const fire = (target) => h.bar._listeners.forEach((fn) => fn({ target: target }));
fire(btn);
expect('Materials click filters the list',
       h.list.classList.contains('tl_materials_only'), true);
// Exactly what showOnlyTraderOther() sets. If these drifted, the button would
// hide the Parts but leave Gear and Usables on screen.
expect('drives the game\'s own display variables', h.vars,
       { '--trader_equipment_display': 'none',
         '--trader_consumable_display': 'none',
         '--trader_other_display': 'inline-block' });
fire(h.els['trader_category_other']);
expect('Misc click clears the filter',
       h.list.classList.contains('tl_materials_only'), false);
fire(btn);
fire(h.els['trader_category_all']);
expect('any other category clears it too',
       h.list.classList.contains('tl_materials_only'), false);
// A click on something that is not a direct child must be ignored.
fire(mkEl('unrelated'));
expect('stray click ignored', h.list.classList.contains('tl_materials_only'), false);

// The class lands on #trader_inventory_div and not on a row, which is what
// makes it survive the game's rebuild: update_displayed_trader_inventory does
// `trader_inventory_div.textContent = ""`, which clears the children and
// leaves the container - and its class - standing.
fire(btn);
expect('class is on the container, not a row',
       h.list.id, 'trader_inventory_div');

console.log('\nthe CSS rule');
// Parts and materials share one bucket in the game's stylesheet:
//   .trader_item_other, _loot, _material, _component, _book
//       { display: var(--trader_other_display); }
// so the whole feature is this one rule subtracting Parts from that set.
const rule = CSS.match(/#trader_inventory_div\.tl_materials_only ([^{]+)\{([^}]*)\}/);
expect('rule exists', Boolean(rule), true);
if (rule) {
  expect('hides Parts', rule[1].trim(), '.trader_item_component');
  expect('  and hides them', rule[2].replace(/\s+/g, ' ').trim(), 'display: none;');
  // The point of the button. A selector that caught _material as well would
  // leave an empty list, and a list that renders nothing reads as a broken
  // script rather than a wrong filter.
  expect('  does NOT hide materials',
         rule[1].indexOf('trader_item_material') === -1, true);
  expect('  does NOT hide loot or books',
         rule[1].indexOf('trader_item_loot') === -1 &&
         rule[1].indexOf('trader_item_book') === -1, true);
  // No !important: an id + class already outranks the game's class-only rule,
  // and staying at plain specificity leaves the game able to hide these rows
  // for its own reasons.
  expect('  no !important', rule[2].indexOf('!important') === -1, true);
}

// --- "Add all" --------------------------------------------------------------
// The button is trivial; the LOOP behind it is not, and nothing else in the
// suite can see the two ways it goes wrong. Both are modelled here:
//   - the row list is rebuilt after every click, so a cached list means
//     clicking detached nodes, which fails silently rather than throwing
//   - the trader panel also shows the player's own to-sell items, and clicking
//     one of those un-sells it instead of buying anything
function addAllHarness(env) {
  env = env || { master: true, on: true, rows: null, sticky: false };
  // The trader's list, as a store the mock queries against. Clicking a row's
  // "all" button removes it, which is what the game does: a row fully in the
  // buy list is skipped entirely on the next rebuild.
  const store = (env.rows || [
    { id: 'gold_ingot', visible: true, toTrade: false },
    { id: 'ancient_chestplate', visible: false, toTrade: false },   // filtered out
    { id: 'bone_cotton', visible: true, toTrade: false },
    { id: 'my_own_sword', visible: true, toTrade: true },           // staged to SELL
  ]).slice();
  const clicked = [];
  let queries = 0;
  function wrap(rec) {
    // A FRESH wrapper every query, so a cached list cannot keep working: this
    // is what makes the re-query assertion below meaningful rather than
    // decorative.
    return {
      offsetParent: rec.visible ? {} : null,
      querySelector: (sel) => (sel === ALL_AMOUNT_SEL ? {
        click: () => {
          clicked.push(rec.id);
          if (!env.sticky) store.splice(store.indexOf(rec), 1);
        },
      } : null),
    };
  }
  const accept = mkEl('accept_trade_button');
  const cancel = mkEl('cancel_trade_button');
  const bar = mkEl('trade_control_div');
  bar.children = [accept, cancel];
  bar.insertBefore = (node, ref) => {
    bar.children.splice(bar.children.indexOf(ref), 0, node);
    node.parentNode = bar;
    made[node.id] = node;
  };
  const made = { accept_trade_button: accept, cancel_trade_button: cancel,
                 trade_control_div: bar };
  const document = {
    getElementById: (i) => made[i] || null,
    createElement: () => {
      const e = mkEl('');
      e._listeners = [];
      e.addEventListener = (t, fn) => e._listeners.push(fn);
      return e;
    },
    querySelectorAll: (sel) => {
      queries++;
      // The mock honours :not(.item_to_trade) the way the browser would, so a
      // selector that dropped it would show up here as an un-sold sword.
      return store.filter((r) => !(r.toTrade &&
             sel.indexOf(':not(.item_to_trade)') !== -1)).map(wrap);
    },
  };
  const ENABLE_VISUAL_OVERRIDES = env.master;
  const TRADER_ADD_ALL = env.on;
  eval(addAllSrc);
  addTradeAllButton();
  addTradeAllButton();             // idempotency: must not insert twice
  return { bar: bar, made: made, clicked: clicked,
           queries: () => queries, fire: () => {
             const b = made[ADD_ALL_BTN_ID];
             if (b) b._listeners.forEach((fn) => fn());
           } };
}

console.log('\naddTradeAllButton');
let a = addAllHarness();
expect('inserted once, before Trade', a.bar.children.map((c) => c.id),
       ['tl_trade_add_all', 'accept_trade_button', 'cancel_trade_button']);
expect('label', a.made['tl_trade_add_all'].textContent, 'Add all');
const tw = a.bar.children.map((c) => parseInt(c.style.width, 10));
expect('all three widths equal', tw, [131, 131, 131]);
expect('widths + margins fit the 400px row',
       tw.reduce((x, y) => x + y, 0) + 2 * tw.length <= 400, true);

console.log('\ntradeAddAllDisplayed');
a.fire();
// Hidden rows are skipped (that is what makes Mats + Add all a materials-only
// restock), and the player's own staged sale is never touched.
expect('clicks only the displayed, buyable rows', a.clicked,
       ['gold_ingot', 'bone_cotton']);
// One query per click plus the final one that finds nothing left. If the list
// were collected once and iterated, this would be 1 - and the second click
// would land on a detached node and do nothing at all.
expect('re-queries after every click', a.queries(), a.clicked.length + 1);

// A row that refuses to clear must stop at the cap rather than spin the
// browser. This cannot happen through the game's own path, which is exactly
// why it needs asserting: nothing else would catch the guard being removed.
a = addAllHarness({ master: true, on: true, sticky: true,
                    rows: [{ id: 'stuck', visible: true, toTrade: false }] });
a.fire();
expect('a row that will not clear stops at the cap',
       a.clicked.length, ADD_ALL_MAX);

console.log('\nselectors');
expect('row selector excludes staged sales',
       TRADE_ROW_SEL.indexOf(':not(.item_to_trade)') !== -1, true);
expect('  and is scoped to the trader panel',
       TRADE_ROW_SEL.indexOf('#trader_inventory_div') === 0, true);
expect('amount selector is the game\'s own "all"', ALL_AMOUNT_SEL,
       '.trade_ammount_button[data-trade_ammount="Infinity"]');

console.log('\ntoggles');
a = addAllHarness({ master: true, on: false });
expect('toggle off: no Add all button', a.bar.children.length, 2);
expect('toggle off: Trade/Cancel widths untouched',
       a.bar.children.map((c) => c.style.width), [undefined, undefined]);
a = addAllHarness({ master: false, on: true });
expect('master off: no Add all button', a.bar.children.length, 2);

h = harness({ master: true, on: false });
expect('toggle off: no button', h.bar.children.length, 4);
expect('toggle off: widths untouched',
       h.bar.children.map((c) => c.style.width),
       [undefined, undefined, undefined, undefined]);
h = harness({ master: false, on: true });
expect('master off: no button', h.bar.children.length, 4);

console.log('\n' + (bad ? bad + ' FAILURES' : 'all correct'));
process.exit(bad ? 1 : 0);
