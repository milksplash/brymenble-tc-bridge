# Setup & usage

This page walks through installing the bridge, connecting TestController, and
tuning the multi-mode option. Everything here assumes the repo layout:

```
brymenble/                    <- SDK (sibling repo, editable-installed)
brymenble-bridge/             <- this repo
```

## 1. Create the environment

```powershell
cd brymenble-bridge
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

`requirements.txt` installs `brymenble` in editable mode from `../brymenble`,
which pulls in `bleak`. If the repos aren't siblings, edit `requirements.txt`
to point at the real path (or `pip install ../brymenble`).

## 2. Test without a meter (optional but recommended)

Before touching BLE, verify the whole TestController side works with the
simulator — it serves the exact same lines the bridge will send:

```powershell
.venv\Scripts\python tools\simulate_meter.py --port 6000
```

Then in TestController:

1. Open the **Load devices** page.
2. In the device combobox select **Brymen BM78xBT** (the baseline def) and
   add it to your inventory, or load the `.def` file directly.
3. Connect it — it should show up as a Socket device on `localhost:6000`.
4. Open the **Current values** page and check that readings appear and change
   once per second.

Stop the simulator when done.

## 3. Run the bridge with a real meter

```powershell
.venv\Scripts\python -m bridge --mac 12:34:56:78:9A:BC
```

Without `--mac` the bridge scans and uses the first BM78xBT it finds:

```powershell
.venv\Scripts\python -m bridge
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--password 0000` | 4-digit connection password (default `0000`) |
| `--host 127.0.0.1` | listen only on this machine (default is all interfaces) |
| `--port 6000` | TCP port (must match `#port` in the `.def`) |
| `--format "{mode} {si_value}"` | default; deterministic mode token + base-unit value |
| `--sync-rtc` | sync the meter RTC to the host clock on connect |
| `--stale 10` | seconds without a frame before checking link state |
| `--pause-cap 60` | seconds of BLE-link-up silence before forcing a reconnect anyway |
| `-v` / `-vv` | more logging |

Then connect TestController to the same port. The bridge reconnects forever
if the meter powers off, so it can run unattended for long logs.

> **Transport note:** the bridge is a TCP *server*; TestController is the
> *client* (Socket interface). A virtual COM port is not needed — the Socket
> interface is the simplest transport and works over LAN/WSL too.

## 4. Baseline vs multi-mode

### Baseline (`testcontroller/BM78xBT.def`)

One generic **Reading** column; the value travels with each line
(`"0.0073"`, `"OL"`). Use the plain form: `--format "{value} {unit}"`.

### Multi-mode (`testcontroller/BM78xBT-MultiMode.def`) — the default

Per-function columns with the correct unit. This is what
`--format "{mode} {si_value}"` (the default) produces, and it's the
recommended setup:

```powershell
.venv\Scripts\python -m bridge
```

Because the BM78xBT *reports* its current function in every frame, the bridge
tags each line with a mode token (`ACV`, `DCmV`, `RES`, ...) and TestController
picks the matching `#value` row — so columns/units follow the rotary switch
without any meter control.

### How the mode is matched (verified from the driver bytecode)

TestController's SingleValue driver builds the mode from the **letters in the
line**: letters before the number plus any unit letters after it (SI-prefix
letters like `k`/`m`/`u` following a number are absorbed into the value, not
the mode). That is why the bridge emits `<mode> <si_value>` with **no trailing
unit** — the mode is then exactly the leading letters, and the selectors in
`BM78xBT-MultiMode.def` match deterministically. (An earlier draft emitted
"`ACV 0.0073 V`", whose mode became `ACVV`, matching nothing — the symptom was
"no value in TC".)

Tokens must be **letters only**: a digit in the leading token is absorbed into
the value by the driver, so temperature uses `TC`/`TD`/`TCD`, not `T1`/`T2`.

You can confirm a line's parsed mode with TC's debug: `#debug BM78x` then
look at the "Mode reported: <...>" line.

## 5. Overload / ASCII states

Overload is emitted as `OL` (negative overload as the `-OL` text) and ASCII
states (`Auto`, `InEr`, `EF-H`/`EF-L`, `-----` for NCV) as bare text. Both
`.def` files include `#valueText` rows mapping them. Add more as needed.

## 6. Units

Units are emitted ASCII-safe because TestController reads lines as
ISO-8859-1: `Ω` → `Ohm`, `µ` → `u` (`°C`/`°F` are fine). This is handled in
`bridge/emitter.py` (`UNIT_ASCII` / `PREFIX_ASCII`); disable with
`Emitter(..., unit_ascii=False, prefix_ascii=False)` if you prefer raw symbols.

## Troubleshooting

- **No readings in TestController** — is the simulator/bridge running and is
  the port right? `Test-NetConnection localhost -Port 6000` (PowerShell), or
  `telnet localhost 6000` — the lines should appear.
- **Bridge can't find the meter** — check the meter is powered and not
  connected to another app (Android/PC). Bluetooth on Windows: remove a stale
  pairing in *Bluetooth & other devices* if the connection loops.
- **Wrong password** — the SDK fails the connect with a clear `CommandError`;
  pass `--password`.
- **`RuntimeError: BrymenClient not connected`** — transient during a
  reconnect; the bridge handles it and retries.
- **Mode column wrong in multi-mode** — see *Verify / tune the mode letters*
  above.
