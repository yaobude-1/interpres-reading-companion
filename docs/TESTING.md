# Testing and release checks

Interpres is a Windows desktop app. Tests fall into two groups: automated
checks that run in CI, and manual probes that need a real desktop.

## Automated gate

```powershell
python tests\run_checks.py
```

This is the command used by `.github/workflows/checks.yml`, after the
`ruff check .` lint step. It covers:

- config and key handling
- local HTTP API authentication, limits, and mocked translation
- dictionary parsing and morphology
- vocabulary storage and TSV export
- AnkiConnect round trips against a mock server
- pronunciation fallbacks
- endpoint policy
- chunk deduplication
- P0 regressions: newest chat messages, non-destructive vocabulary
  updates, cache-key inputs, Anki single-template updates, MDX size limits
- P1 regressions: DPAPI key storage (including the "cannot decrypt" case),
  dictionary HTML sanitization with a fail-closed fallback, no external speech
  URLs, and an ASCII-only portable build script (PS 5.1 decodes BOM-less
  scripts as ANSI, which silently dropped the Chinese quick-start file)
- panel geometry restore, so a saved window size is actually applied

The gate must pass before a release. It does not require a visible desktop,
though some pronunciation checks are skipped when the machine has no matching
voice pack.

## Static checks

`ruff.toml` pins the rule set (syntax errors, pyflakes, flake8-bugbear). The
baseline is clean, so any finding is a regression:

```powershell
python -m pip install -r requirements-dev.txt
ruff check .
```

The gate intentionally enables only defect-finding rules: no formatting, no
import sorting, no style rewrites. When a warning is a false positive, prefer
restructuring the code; if that is not practical, add a narrow `# noqa: <code>`
with a one-line reason.

## Script tests

`tests/test_*.py` are standalone assert-style scripts, not pytest tests. Most
can run directly:

```powershell
python tests\test_panel.py
python tests\test_ux_flows.py
```

Some need a real Tk desktop, Windows clipboard, or Anki. They are run locally
before publishing; they are not all part of CI.

## Manual probes

`tests/ui_*.py`, `tests/make_doc_screenshots.py`, and capture helpers are
diagnostic tools and screenshot generators. They are not expected to pass in a
headless environment.

## Release checklist

Before replacing a release asset, verify on Windows:

- [ ] App starts from source and from the packaged portable folder.
- [ ] Settings open without a white flash; changing and saving a setting
      persists after restart.
- [ ] Selection capture returns the selected text and restores the previous
      clipboard content.
- [ ] A selection shows the popup near the cursor and does not jump off-screen.
- [ ] A bad API key / unreachable endpoint shows an error instead of hanging on
      “Thinking…” or “翻译中…”.
- [ ] A local dictionary lookup renders grouped senses and the original entry
      opens.
- [ ] Favourite toggles in both the panel and popup, and the state is restored
      after a new lookup.
- [ ] AnkiConnect push adds notes and skips duplicates (if Anki is installed).
- [ ] Closing/restarting leaves no second instance and no stale tray icon.
- [ ] The packaged EXE has the same version and behaviour as the source build.

## CI limitations

CI runs on GitHub's `windows-latest` image (Windows Server), not desktop
Windows 10/11. GUI-heavy checks therefore stay manual. A true 10/11 matrix
would need self-hosted runners.
