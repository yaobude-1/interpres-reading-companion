# Third-party notices

Interpres is MIT-licensed (see `LICENSE`). It bundles or depends on the
following third-party components. Their licenses apply to those components.

## Runtime — bundled into the executable

| Component | Version | License | Source |
|---|---|---|---|
| [pystray](https://github.com/moses-palmer/pystray) | 0.19.5 | LGPL-3.0 | `vendor/pystray/` |
| [edge-tts](https://github.com/rany2/edge-tts) | 7.3.1 | LGPL-3.0 | `vendor/edge_tts/` |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14.5 | Apache-2.0 | `vendor/aiohttp/` |
| [aiohappyeyeballs](https://github.com/aio-libs/aiohappyeyeballs) | 2.7.1 | PSF-2.0 | `vendor/aiohappyeyeballs/` |
| [aiosignal](https://github.com/aio-libs/aiosignal) | 1.4.0 | Apache-2.0 | `vendor/aiosignal/` |
| [attrs](https://github.com/python-attrs/attrs) | 26.1.0 | MIT | `vendor/attrs/` |
| [certifi](https://github.com/certifi/python-certifi) | 2026.10.23 | MPL-2.0 | `vendor/certifi/` |
| [frozenlist](https://github.com/aio-libs/frozenlist) | 1.8.0 | Apache-2.0 | `vendor/frozenlist/` |
| [idna](https://github.com/kjd/idna) | 3.20 | BSD-3-Clause | `vendor/idna/` |
| [multidict](https://github.com/aio-libs/multidict) | 7.2.1 | Apache-2.0 | `vendor/multidict/` |
| [propcache](https://github.com/aio-libs/propcache) | 0.5.4 | Apache-2.0 | `vendor/propcache/` |
| [tabulate](https://github.com/astanin/python-tabulate) | 0.10.0 | MIT | `vendor/tabulate/` |
| [typing_extensions](https://github.com/python/typing_extensions) | 4.16.0 | PSF-2.0 | `vendor/typing_extensions.py` |
| [yarl](https://github.com/aio-libs/yarl) | 1.25.1 | Apache-2.0 | `vendor/yarl/` |
| [Pillow](https://python-pillow.org/) | 12.x | HPND | installed Python environment |
| [lxml](https://lxml.de/) | 6.x | BSD-3-Clause | installed Python environment |
| [six](https://github.com/benjaminp/six) | 1.17.0 | MIT | installed Python environment |

## Build-time only

| Component | License |
|---|---|
| [PyInstaller](https://pyinstaller.org/) | GPL-2.0-or-later with a special exception that permits building and distributing proprietary executables |

## LGPL compliance

`pystray` and `edge-tts` are licensed under **LGPL-3.0**. Their complete
sources are pure Python and are installed locally into `vendor/` from PyPI via
`requirements.txt` (the same versions pinned there). The repository does not
commit `vendor/`. The full license texts are included in `licenses/`:

- `licenses/pystray-LGPL-3.0.txt`
- `licenses/pystray-COPYING.txt`
- `licenses/edge-tts-LICENSE.txt`
- `licenses/aiohttp-Apache-2.0.txt`
- `licenses/certifi-MPL-2.0.txt`

Exact upstream source versions:

- pystray 0.19.5 — https://github.com/moses-palmer/pystray/tree/v0.19.5
- edge-tts 7.3.1 — https://github.com/rany2/edge-tts/tree/v7.3.1

The packaged portable build freezes these modules into the PyInstaller
archive, so they are not individually replaceable inside the installed
`_internal` folder without rebuilding. To exercise LGPL modification rights,
run from source with a local `vendor/` directory, or obtain the exact upstream
source version and rebuild the application. This notice does not claim that
the frozen executable can be relinked by replacing a single file.

## Content

MDX/MDD dictionaries, book text, covers and audio are **not** part of this
project. Users are responsible for obtaining and using them legally.

DeepSeek API, Microsoft Edge TTS and AnkiConnect are external services with
their own terms.
