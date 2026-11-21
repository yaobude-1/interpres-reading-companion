# Changelog

User-visible changes per release. Engineering-only work is summarised briefly too,
so the repository history is not the only record of what changed.

## Unreleased

Internal only, no behaviour change:
- The settings window was split into modules (`settings_pages`, `settings_actions`,
  `settings_common`); the 560-line `_build` is now a small dispatcher plus one
  builder per page section.
- `tests/test_ux_scenarios.py` had a check helper that recorded every boolean
  assertion as a pass; it now fails on `False`, and the chat-empty case exercises
  the real `Service.ask` path.

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
