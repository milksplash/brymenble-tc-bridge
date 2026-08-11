# brymen-tc-bridge

Bridge a **Brymen BM78xBT** BLE multimeter into
[**TestController**](https://lygte-info.dk/project/TestControllerIntro%20UK.html)
(lygte-info.dk's freeware multi-device test & logging tool).

TestController has no native BLE transport, and the BM78xBT exposes no
documented remote-control commands — so this project does the only thing the
protocol supports: it connects over BLE with the
[`brymenble`](https://github.com/your-org/brymenble) SDK, decodes the meter's
stream, and re-emits each reading as an ASCII **SingleValue** line that
TestController logs like any other instrument.

```
BM78xBT ──BLE──▶ brymen-tc-bridge ──TCP socket──▶ TestController (SingleValue driver)
                      │
              brymenble SDK decodes
              value, unit, prefix, function, flags
```

Because the BM78xBT *reports* its current function/unit in every frame, the
bridge can tag each line with a **mode token**, so TestController shows the
correct column and unit as you turn the rotary switch — no meter control
required (see `testcontroller/BM78xBT-MultiMode.def`).

## Layout

| Path | Purpose |
| --- | --- |
| `bridge/` | Python package: `emitter` (SingleValue formatting), `transports` (TCP server), `bridge` (reconnect loop), `cli` (entry point) |
| `testcontroller/` | TestController device definition files (SingleValue driver) |
| `tools/simulate_meter.py` | Act as the bridge with fake readings — configure/test TestController without a meter |
| `docs/setup.md` | Full step-by-step setup and troubleshooting |

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m bridge --mac 12:34:56:78:9A:BC
```

Without `--mac`, the first BM78xBT found by scanning is used. Then, in
TestController: **Load devices** → pick *Brymen BM78xBT* → connect to
`localhost:6000`.

See [`docs/setup.md`](docs/setup.md) for the full walkthrough, the multi-mode
option, and how to verify the mode letters in TestController's debug mode.

## Tests

Offline unit tests (no meter or TestController needed):

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

These cover the SingleValue emitter (`bridge/emitter.py` — ASCII-safe units,
base-unit scaling, mode tokens, overload/ASCII text) and the TCP line server
(`bridge/transports.py` — framing and the `*IDN?` handshake).

## Notes

- The meter's function **cannot be switched over BLE** (documented protocol
  has no control commands). The person turns the rotary switch; the bridge
  follows and TestController logs the right units.
- TestController reads one line per reading; the bridge reconnects
  automatically if the meter powers off, and never crashes.
- Units are emitted ASCII-safe (`Ω` → `Ohm`, `µ` → `u`) because TestController
  reads lines as ISO-8859-1.

Unofficial / community project — not affiliated with Brymen or lygte-info.
