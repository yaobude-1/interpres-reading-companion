# Changelog

User-visible changes per release. Engineering-only work is summarised briefly too,
so the repository history is not the only record of what changed.

## Unreleased

- Vocabulary tab: word actions (sync/move/delete/export/Anki settings) now sit
  under the word table, while new/rename/delete for word books stay in the left
  pane; the buttons no longer float under the book list.
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
