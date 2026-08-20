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
| `testcontroller/BM78xBT.txt` | TestController device definition (SingleValue driver) |
| `tools/simulate_meter.py` | Act as the bridge with fake readings — configure/test TestController without a meter |

## Setup

### 1. Install the bridge

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

`requirements.txt` installs `brymenble` in editable mode from `../brymenble`
(the sibling SDK repo), which pulls in `bleak`. If the repos aren't siblings,
edit `requirements.txt` to point at the real path (or `pip install ../brymenble`).

### 2. Run the bridge

```powershell
.venv\Scripts\python -m bridge 12:34:56:78:9A:BC
```

Without a MAC, the first BM78xBT found by scanning is used:

```powershell
.venv\Scripts\python -m bridge
```

The bridge listens on `localhost:6000` by default and reconnects to the meter
forever if it powers off, so it can run unattended for long logs.

### 3. Connect TestController

1. Copy `testcontroller/BM78xBT.txt` into TestController's `Devices` folder.
2. Start TestController.
3. Go to the **Load devices** page.
4. Select **Brymen BM78xBT** from the drop-down list.
5. Press **Add**.
6. Press **Reconnect** — TestController jumps to the **Commands** page.
7. Press **Run**.

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

- The meter's function **cannot be switched over BLE/TestController.**
- **TestController does not auto-reconnect its socket.** After a meter power cycle you must reconnect manually in TestController.

## Known limitations

- **Mode tokens must be letters-only.** TestController's SingleValue driver
  absorbs any digit in the leading token into the value, so a token like
  `T1` would corrupt the reading (e.g. `T1 25.60` parses as `125.60`). The
  bridge therefore maps the temperature functions to letters-only tokens
  (`T1`→`TEMPONE`, `T2`→`TEMPTWO`, `T1-T2`→`TEMPDIFF`).

## Temperature (°C / °F)

The meter reads temperature in either Celsius or Fahrenheit. The bridge
encodes the unit in the mode token's last letter so TestController selects
the correct `#value` row:

| Function | °C token | °F token |
| --- | --- | --- |
| T1 | `TEMPONEC` | `TEMPONEF` |
| T2 | `TEMPTWOC` | `TEMPTWOF` |
| T1-T2 | `TEMPDIFFC` | `TEMPDIFFF` |

The value is emitted as-is (temperature has no SI prefix, so no scaling is
applied). The `testcontroller/BM78xBT.txt` def has matching `C` and `F`
rows for each token.