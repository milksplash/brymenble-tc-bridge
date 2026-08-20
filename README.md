# brymen-tc-bridge

> **⚠️ Unofficial.** This is an independent, community-developed project. It is
> **not affiliated with, endorsed by, or sponsored by** Brymen Technology Corporation. "Brymen" and the device model names are trademarks of their
> respective owners.

Bridge a **Brymen BM78xBT** BLE multimeter into
[**TestController**](https://lygte-info.dk/project/TestControllerIntro%20UK.html)
(lygte-info.dk's freeware multi-device test & logging tool).


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
- **TestController does not auto-reconnect its socket.** If the meter powers
  off mid-test, the bridge reconnects to the meter on its own — but
  TestController's Socket connection to the bridge is not re-established by
  TestController. After a meter power cycle you must reconnect manually in
  TestController.
