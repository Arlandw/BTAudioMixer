# BTAudioMixer

Touchscreen Bluetooth audio mixer appliance for Raspberry Pi.

## Goal
Mix two Bluetooth audio inputs (iPhone + Peloton) into one output stream for Bluetooth headphones, with a touchscreen UI for live control.

## Phase 1 (implemented)
- Role-based Bluetooth device manager (`phone`, `peloton`, `headphones`)
- Assign/pair/connect controls via API
- Basic audio gain controls for 2 inputs + master via PipeWire (`wpctl`)
- Touchscreen-friendly web UI with:
  - MAC assign fields
  - Pair/connect buttons
  - 3 faders (phone/peloton/master)
  - per-source + master activity meters (active/idle visualizer)
  - 2 presets (Ride / Podcast Focus)

## Repo layout
```
.
├── bt_manager/
├── audio_engine/
├── api/
├── ui/
├── scripts/
└── docs/
```

## Requirements (Pi)
- Raspberry Pi OS Bookworm
- `bluetoothctl` (BlueZ)
- `wpctl` (PipeWire)
- Python 3.11+

## Quick start (dev)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m api.main
# or
uvicorn api.main:app --host 0.0.0.0 --port 8787 --reload
```
Open UI:
- `http://<pi-ip>:8787/`

## Notes
- Phase 1 uses command wrappers around `bluetoothctl` and `wpctl`.
- Robust adapter pinning/reconnect policy is planned for Phase 2.
