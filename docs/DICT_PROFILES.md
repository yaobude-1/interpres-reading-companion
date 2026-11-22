# Dictionary profiles (declarative mapping)

Interpres reads MDX/MDD containers generically, but entry HTML differs between
dictionaries. Profiles let you map a dictionary's HTML with JSON + XPath —
without touching the code.

## Where profiles live

```
%USERPROFILE%\.reading-companion\dict_profiles\*.json
```

Open the editor from **Settings → Dictionary & audio → Dictionary settings →
Dictionary mapping…**. Profiles are loaded when a dictionary is opened; saving
from the editor reloads dictionaries immediately.

Matching order: files are loaded in filename order and the **first** profile
whose `match` rule hits the entry HTML is used. If parsing yields no senses, the
app falls back to the built-in parser, so a broken profile cannot break lookup.

## Schema

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | lowercase id; also the filename (`<id>.json`) |
| `name` | yes | display name |
| `match` | yes | how to recognise this dictionary's entry HTML |
| `senses` | yes | XPath selecting one node per sense (absolute) |
| `definition` | yes | XPath **relative to each sense** |
| `definition_cn` | no | relative XPath |
| `example` | no | relative XPath selecting one node per example |
| `example_cn` | no | relative XPath inside the example node |
| `headword` | no | absolute XPath |
| `phonetic` | no | absolute XPath |
| `pos` | no | absolute XPath |
| `audio` | no | absolute XPath to `<a href="sound://...">` nodes |
| `audio_attr` | no | attribute holding the sound key (default `href`) |

`match` supports:

```json
{"contains": ["token-a", "token-b"]}     // all tokens must appear
{"contains_any": ["token-a", "token-b"]} // any token
{"regex": "class=\"sense\""}             // regular expression
```

## Example: Longman DOCE 6th

```json
{
  "id": "ldoce6",
  "name": "Longman DOCE 6th",
  "match": {"contains": ["class=\"def\""]},
  "headword": "//span[@class='hwd']",
  "phonetic": "//span[@class='pron']",
  "pos": "//span[@class='pos']",
  "senses": "//span[@class='sense']",
  "definition": ".//span[@class='def']",
  "definition_cn": ".//span[@class='defcn']",
  "example": ".//span[@class='example']",
  "example_cn": ".//expcn",
  "audio": "//a[starts-with(@href,'sound://')]",
  "audio_attr": "href"
}
```

This profile reproduces the built-in Longman parsing (verified against the
full dictionary): headword, IPA, POS, definitions (EN/CN), paired examples and
audio keys.

## Finding the right XPath

1. Use any MDX viewer/documentation tool that can dump the **HTML of a single
   entry**.
2. Find a class/id that is unique to this dictionary's entries and use it in
   `match.contains` (e.g. `class="entry"`, `lm6-entry`).
3. Build `senses` first: one node per numbered sense. Then add relative
   `definition`, `definition_cn`, `example`, `example_cn`.
4. Start minimal — if `definition` works, the app already gives useful output;
   add the rest incrementally.
5. Save from the editor and look up a word. Wrong XPath simply falls back to
   the built-in parser.

## Notes and limits

- `example_cn` must be **inside** the `example` node; the parser removes the
  translated part from the source text before pairing.
- Only the first 12 senses and 4 examples per sense are used.
- Profiles do not affect Anki rich-card extraction (`rc/rich.py`), which has
  its own structure-aware extractors.
- Keep profiles small and trust their source; XPath is evaluated on local HTML.
