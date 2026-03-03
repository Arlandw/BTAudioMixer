# BTAudioMixer

Touchscreen Bluetooth audio mixer appliance for Raspberry Pi.

## Goal
Mix two Bluetooth audio inputs (iPhone + Peloton) into one output stream for Bluetooth headphones, with a touchscreen UI for live control.

## Planned architecture
- **bt-manager**: BlueZ device pairing/connection state machine
- **audio-engine**: PipeWire routing, gain, limiter, output assignment
- **api**: local FastAPI server for control/state
- **ui**: touchscreen-first web UI (faders, mute, connect buttons)

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

## Quick start (dev)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m api.main
```

## Status
Initial scaffold in progress.
