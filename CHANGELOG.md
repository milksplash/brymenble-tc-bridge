# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - Unreleased

### Fixed

- **`"Hz of Line Signal"` now emits the `LINEHz` mode token** — it previously
  emitted `LINE`, which had no matching `#value` row in
  `testcontroller/BrymenBM78xBT.txt`, so TestController couldn't map the
  line-frequency function to a value row.
- **`tools/simulate_meter.py --skip-bare` now actually skips bare-text
  samples** — the filter previously checked `value is not None`, but no sample
  stores `None`, so it was a no-op. It now filters on whether the value looks
  numeric, correctly dropping the `OL`/`Auto`/`InEr` samples.
- **`bridge.__version__` no longer drifts from the release** — it is now
  derived from `importlib.metadata.version("brymenble-tc-bridge")` (with a
  fallback for bare source checkouts) instead of a hardcoded stale literal.

### Changed

- **A stalled TCP client can no longer stall the whole bridge** — each client
  now gets its own bounded outbound queue drained by a background task, so a
  slow reader fills its queue and is dropped instead of blocking the event
  loop (and with it the BLE frame loop, keep-alive, and every other client).
- **Removed dead temperature-mode entries** from `FUNCTION_TO_MODE` — the
  `TEMPONE`/`TEMPTWO`/`TEMPDIFF` tokens were unreachable (temperature
  functions are handled by the `TEMP_MODE_C`/`TEMP_MODE_F` tables) and absent
  from the `.txt` selectors.
- **`tools/build_exe.py` always passes `--clean`** to PyInstaller so a build
  never silently reuses a stale cache.
- **`upx` is disabled** in the PyInstaller spec — it was a silent no-op on CI
  (no UPX installed) and can trigger antivirus false positives.
- **Added a `[project.scripts]` entry point** — `brymenble-tc-bridge` is now
  installable as a console command, not only via `python -m bridge` or the
  built EXE.
- **CI now tests Python 3.9** (matching `requires-python = ">=3.9"`) and the
  checkout path was renamed from `bridge` to `bridge-repo` to avoid colliding
  with the package directory name.

### Added

- **Emitter-token consistency test** — `tests/test_emitter.py` now parses the
  `#value` selectors from `testcontroller/BrymenBM78xBT.txt` and asserts the
  symmetric difference with the emitter's mode tokens is empty, so a token
  mismatch (like the `LINE` vs `LINEHz` bug) can't slip through again.

### Docs

- **README "Tests" section** now mentions the keep-alive reconnect loop
  (`bridge/bridge.py`) coverage.

## [0.1.1] - 2026-08-22

### Added

- **PyInstaller single-file Windows EXE** packaging and a release workflow
  that builds and attaches the binary to GitHub Releases.
- **`testcontroller/BrymenBM78xBT.txt`** is attached to the release alongside
  the EXE.

### Changed

- **`bridge.__version__` bumped to `0.1.1`** to match the release.

## [0.1.0] - 2026-08-20

### Added

- **Initial bridge** — connect a Brymen BM78xBT BLE multimeter and re-emit its
  parsed readings as TestController SingleValue lines over TCP.
- **`Emitter`** — formats parsed readings as SingleValue lines (ASCII-safe
  units, base-unit `si_value` scaling, letters-only mode tokens, overload/ASCII
  trailing-space handling).
- **`TcpLineServer`** — TCP server TestController connects to via the Socket
  interface, with `*IDN?` identity handshake.
- **`tools/simulate_meter.py`** — acts as the bridge with fake readings so
  TestController can be configured/tested without a meter.
- **`testcontroller/BrymenBM78xBT.txt`** — TestController device definition.
- **Offline test suite** — emitter, transports, and keep-alive loop, no meter
  or TestController needed.
