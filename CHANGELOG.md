# Changelog

User-visible changes per release. Engineering-only work is summarised briefly too,
so the repository history is not the only record of what changed.

## 1.0.8 — 2026-11-24

### Added
- Screenshot OCR: `Ctrl+Alt+T` opens a full-screen region picker and sends
  recognized text through the same dictionary/translation path. Uses Windows
  OCR locally; no screenshot or OCR text is uploaded.
- Clipboard lookup: copying text in a reading app (`Ctrl+C` or right-click
  Copy) automatically opens a dictionary card or translation. The old
  selection button was removed; `Ctrl+Alt+T` is now screenshot OCR, and the
  clipboard trigger and reading-app whitelist can be disabled in Settings.
- Dictionary lookup now returns every configured dictionary as a source bar above
  the definitions, ranked by match quality (exact → accent → lemma → redirect);
  the book's language only breaks ties.
- Accent-insensitive exact lookup: `creer` finds French `créer`, marked as an
  accent match instead of a redirect.
- User word forms and user conjugation tables: add `form → lemma` mappings or
  import a table; every table row becomes a reverse-lookup form automatically,
  and user data overrides dictionary/built-in matches with a visible badge.
- Extract inflected forms from a dictionary's own `@@@LINK` redirects: scan once,
  review the candidates, and add the real inflections to the user form list.
  Results are cached per dictionary. A bulk mode adds all candidates above a
  similarity threshold at once.
- Experimental WebView2 original-layout renderer: a Tk frame hosts a WinForms
  WebView2, raw MDX HTML is served through a local resource endpoint, and the
  dictionary's own CSS/MDD images/audio are preserved. The dictionary tab has a
  精简/原版 toggle; the default is configurable in Settings → 词典与发音.
- Read unencrypted MDX 1.2 dictionaries (LZO and zlib blocks), so older
  Oxford/Longman-style releases open again.
- Read StarDict `.ifo` / `.idx` / `.dict[.dz]` dictionaries as a fallback for
  non-MDX sources such as the Liddell-Scott Greek lexicon. Original HTML and
  plain-text lookup both work; StarDict has no MDD audio.
- A language can now hold an ordered list of dictionaries, not just one. The
  dictionary settings page supports multi-select import, per-dictionary
  “显示” checkboxes, reordering and removal. Hidden dictionaries stay in the
  config but are not loaded or queried; the source bar and original view follow
  the selected dictionary's stable `dict_id`.
- Dictionaries now live in one global library and can be assigned to several
  language groups. Each group has its own order, muted set and default
  dictionary. Imports start unassigned; assignment happens after import or from
  the group page. A group's default dictionary is selected first when it hits.
- The dictionary group page supports drag handles (and ↑/↓) for ordering,
  separate “面板 / 弹窗” visibility toggles, a default-dictionary star, and
  display-name renaming in the library.
- The lookup popup now uses the same popup mute set, default-dictionary
  selection and `dict_id` source switching as the panel. It has an inline
  精简/原版 toggle and embeds the WebView2 original page directly in the popup
  instead of opening a separate window.
- WebView2 resizing now follows the popup and panel dimensions; move-only Tk
  configure events no longer call `MoveWindow`, avoiding native-child ghosting
  while dragging the main window.
- Panel dictionary lookups run off the Tk main thread and deliver results
  through a queued poller; full-entry and raw-HTML results are cached per
  dictionary, and the popup reuses its inline WebView2 host when moving between
  words.
- Logging rotates at 2 MB with three backups and foreground book-change logs
  are DEBUG-only; the WebView2 message pump runs at 15 ms while active and
  45 ms when idle. Idle dictionaries are released after five minutes, and the
  panel/popup share raw-headword and original-URL helpers.
- Each language group can choose a separate Anki definition dictionary
  (defaulting to the group's ★ dictionary). Saved words now record their
  `dict_id`, used as a fallback when the Anki choice is unavailable.
- English localization covers the new Anki/group controls, inline original
  view and lookup failure messages; `rc/locales` is now included in both
  onefile and portable builds.
- A whole language group can be muted from its header; muting disables all of
  its dictionaries for both the panel and popup until unmuted.
- The 查询 tab now keeps a deduplicated recent-lookup history behind the clock
  icon, with a full history window, re-query, delete and clear actions. It is
  separate from the vocabulary list and is stored locally.
- Lookup history adds inline star save/unsave, source-dictionary preference
  when reopening, language/book filters, total/frequency stats and a
  configurable retention limit.

### Fixed
- Translation history now keeps its limit per book instead of trimming the
  global table, so reading one book no longer evicts another book's history.
- Custom TTS commands accept `{text}`; concurrent synthesis is serialized;
  SoundPlayer paths escape single quotes.
- The WebView2 profile/SDK directories are unique per process, dangerous
  navigation schemes are blocked, and initialization timeout is 10 seconds.
- Config writes are serialized, LLM streaming failures are logged, and the
  LLM User-Agent now uses the real version.
- Oxford-Hachette entries: senses are grouped under their real part of speech
  (`nm`, `vtr`, `vi`, …) instead of all landing under `nm`.
- French `-re` verbs: `vends / vend / vendent / vendu / vendrai → vendre`.
- French noun/adjective forms: `chevaux → cheval`, `heureuse → heureux`,
  `travaux → travail`, etc.
- German/Spanish/Italian no longer borrow the French conjugator (Italian words
  ending in `-re` used to display a French conjugation table).

## 1.0.8 — 2026-11-23

### Added
- The selection popup can be resized by dragging any edge or corner. Size and
  position are remembered; a manually chosen height persists across openings
  (double-click the top/bottom edge to restore automatic height). Sizes are
  DPI-aware.
- Fade-in/out animations for the popup, selection bubble and toast, plus a
  reduced-motion-aware fade for the original-entry view. They can be disabled in
  Appearance → Animations.
- English UI: the language dialog, dictionary mapping editor and dictionary
  settings are fully translated; long English labels wrap instead of being
  clipped; the dictionary mapping template follows the UI language.

### Fixed
- Fast or top-edge resizing no longer leaves blank or ghosted frames: the popup
  repaints immediately, the area it vacates is repainted, and DWM recomposes on
  release.
- Reflowing wrapped labels while resizing no longer crashes on Tcl objects, so
  the new size and position always stick.
- Original dictionary entries: internal `entry://` links such as Longman's
  “您是否要查找：know” now open the target entry in the same viewer instead of
  doing nothing.
- Dictionary cards: the “按原形 X 查到” hint is now a link to the base form
  (previously only the separate 原形 line was clickable).
- The narrow vocabulary toolbar keeps “Move to…” in English instead of falling
  back to Chinese.

### Internal
- Tk callback exceptions are written to app.log instead of only stderr.
- The entry view's CSP uses a SHA-256 script hash (no `unsafe-inline`).
- Continued exception cleanup, UIA contract test, incremental mypy gate,
  PyInstaller 6.22.3 pin, and a CI build job that checks the EXE FileVersion and
  SHA256SUMS.

## 1.0.7 — 2026-11-22

- Settings prompt editors now have vertical scrollbars and mouse-wheel scrolling;
  the outdated “must keep JSON” hint was replaced with “plain text or JSON”.
- Default translation prompt now returns plain translation text only: no
  AI-selected vocabulary, glossary, grammar notes or source-language detection.
  Word/phrase queries still get dictionary-style senses separated by “；”.
  Existing custom JSON prompts remain supported.
- Vocabulary tree borders now use the panel colour instead of a light ttk
  outline.
- Vocabulary table no longer shows a horizontal scrollbar (columns fit the
  table width); the vertical bar hides when the rows fit and uses a subtle dark
  thumb instead of a light strip.
- Vocabulary tab: word actions now form one row under the word table (full
  labels on wide windows; short labels and a gear for Anki settings when
  narrow), while new/rename/delete for word books stay in the left pane.
- A new selection no longer closes the open translation popup; the “译/聊”
  quick button is raised above it, and the popup is replaced when a new result
  arrives.
- New Appearance settings page: dark/light theme, accent colour presets, popup
  width/height/opacity and panel opacity. Theme and accent apply after a restart
  (the save dialog offers to restart); sizes and opacity apply when the windows
  next open.
- Dictionary entries reached through an MDX `@@@LINK` redirect are labelled:
  inflections show "按原形 X 查到"; lexical redirects (e.g. decomposition →
  composition) show a notice with "查看目标词条" and "用 AI 译" actions instead of
  presenting the other word's senses as the query's own.

## 1.0.6 — 2026-11-22

### Added
- `uninstall.ps1`: stops running instances, removes shortcuts/icon copies, asks
  whether to delete the data folder, and deletes the program folder.
- Double-click a saved word in the vocabulary tab to open its dictionary card
  (or the saved fields when no dictionary is configured).
- Sort the word table by clicking a column header; the choice is remembered.
- Chat reads the paragraph around the selection automatically in Edge/Chrome
  (HTML and the built-in PDF viewer). Other readers fall back to a
  "补充上下文" dialog; the feature can be turned off in settings.
- "对话原文上限" now defaults to 4000 characters and stays user-adjustable.

### Changed
- Language names follow the UI language; new default wordbooks are named
  "英语词本" or "English wordbook" accordingly. Existing wordbooks are unchanged.
- Dictionary cards show the dictionary's own name (MDX `Title`) instead of a
  translated short alias with a language prefix.
- Column widths can be dragged one divider at a time with min-width cascading;
  the proportions are saved and restored across window sizes.

### Fixed
- `Ctrl+Alt+S` is described as opening the panel (it never opened settings);
  the missing-API-key hint and the custom-endpoint notice are worded correctly.
- `install.ps1` and `build_exe.ps1` now carry a UTF-8 BOM so PowerShell 5.1
  does not decode their Chinese text as ANSI.

### Internal
- Settings window and vocabulary panel split into focused modules.
- The UX scenario helper no longer records `False` assertions as passes.
- Added an opt-in live UIA test (`tests/test_uia_live.py`).

## 1.0.5 — 2026-11-21

This release brings the published build in line with the source tree; the downloadable
zip had been 19 commits behind since 1.0.4.

### Fixed
- Fuzzy dictionary search honours the selected language again (a French lookup no
  longer returns English words).
- Multi-dictionary lookup ranks exact headwords first, so a French word is not hidden
  behind an English prefix match.
- The Latin word-ending table had duplicate keys, so some candidate forms were never
  generated.
- The portable build no longer drops `使用说明.txt` (PowerShell 5.1 decoded the
  BOM-less build script as ANSI).
- The saved main-panel size and position are applied again; they used to be restored
  before the panel existed.
- An API key copied from another machine reports "cannot be decrypted" instead of
  looking unconfigured.
- Dictionary HTML sanitization is fail-closed: if parsing fails, the entry is shown
  as escaped text instead of raw HTML.
- The local API token comparison is constant-time.

### Changed
- A ruff lint gate runs in CI before the tests.
- The service, panel, popup and app modules were split into focused modules; method
  bodies were verified with AST comparison so behaviour is unchanged.
- CI runs 11 scripts, including 6 Tk GUI regressions, and uses `actions/checkout@v7`
  plus `actions/setup-python@v7`.

## 1.0.4 — 2026-11-20

### Fixed
- Popup chat no longer gets stuck when the first streaming update arrives.
- Long conversations keep the newest 200 messages instead of the oldest.
- Re-adding a saved word no longer clears its book/dictionary fields.
- Translation cache keys include model, prompt and glossary.
- MDX reads are serialized and decompression size is capped.
- Anki template sync updates only the first template.
- Duplicate chunks are translated once.

### Security and privacy
- The API key is encrypted at rest with Windows DPAPI.
- Dictionary HTML is stripped of scripts, inline events and `javascript:` links; a CSP
  blocks external resources.
- Logs no longer contain selected text, words or spoken passages.
- Selection capture preserves text, files and DIB clipboard formats.
- Removed the external Youdao speech URL from Anki cards.
- `/api/config` validates endpoint URLs; the local API stays token-protected and
  loopback-only.
