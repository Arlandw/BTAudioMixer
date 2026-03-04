"""PipeWire-backed audio engine.

Phase 1 implementation:
- track two input gains + master
- apply volume by PipeWire node name via `wpctl`
- expose lightweight source activity state (running/idle)
- keep state in-memory for UI/API use
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import subprocess
from typing import Any
import re
import math
import shlex
import struct


@dataclass
class AudioState:
    phone_gain: float = 0.5
    peloton_gain: float = 0.5
    master_gain: float = 0.8
    phone_node: str | None = None
    peloton_node: str | None = None
    output_node: str | None = None


class AudioEngine:
    def __init__(self) -> None:
        self.state = AudioState()
        self._level_smooth: dict[str, float] = {}

    def discover_nodes(self) -> dict[str, Any]:
        result = subprocess.run(["wpctl", "status", "--name"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "wpctl status failed")
        lines = result.stdout.splitlines()

        def pick(patterns: list[str]) -> str | None:
            for line in lines:
                l = line.lower()
                if any(p in l for p in patterns):
                    m = re.search(r"\b(\d+)\.\s", line)
                    if m:
                        return m.group(1)
            return None

        # Pull connected Bluetooth MACs to match bluez_input lines reliably
        bt = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, check=False)
        connected_macs = []
        if bt.returncode == 0:
            for line in bt.stdout.splitlines():
                m = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s+", line.strip())
                if m:
                    connected_macs.append(m.group(1).replace(":", "_").lower())

        phone_node = None
        for line in lines:
            l = line.lower()
            if "bluez_input." not in l:
                continue
            if connected_macs and not any(mac in l for mac in connected_macs):
                continue
            m = re.search(r"\b(\d+)\.\s", line)
            if m:
                phone_node = m.group(1)
                break

        if phone_node is None:
            phone_node = pick(["bluez_input", "iphone", "ios", "phone"])

        peloton_node = pick(["peloton"])

        # Output defaults to active sink; fallback to named headphone sinks.
        output_node = None
        for line in lines:
            if "sinks:" in line.lower():
                continue
            m = re.search(r"\*\s*(\d+)\.\s", line)
            if m:
                output_node = m.group(1)
                break
        if output_node is None:
            output_node = pick(["bluez_output", "airpods", "headphones", "buds", "auto_null"])

        if phone_node:
            self.state.phone_node = phone_node
        if peloton_node:
            self.state.peloton_node = peloton_node
        if output_node:
            self.state.output_node = output_node
        self.apply_all_gains()
        return self.status()

    def set_nodes(self, phone_node: str | None, peloton_node: str | None, output_node: str | None) -> dict[str, Any]:
        self.state.phone_node = phone_node
        self.state.peloton_node = peloton_node
        self.state.output_node = output_node
        self.apply_all_gains()
        return self.status()

    def set_gains(self, phone: float, peloton: float, master: float) -> dict[str, Any]:
        self.state.phone_gain = self._clamp(phone)
        self.state.peloton_gain = self._clamp(peloton)
        self.state.master_gain = self._clamp(master)
        self.apply_all_gains()
        return self.status()

    def apply_all_gains(self) -> None:
        self._set_node_volume(self.state.phone_node, self.state.phone_gain)
        self._set_node_volume(self.state.peloton_node, self.state.peloton_gain)
        self._set_node_volume(self.state.output_node, self.state.master_gain)

    def status(self) -> dict[str, Any]:
        return asdict(self.state)

    def activity(self) -> dict[str, Any]:
        return {
            "phone_active": self._is_node_running(self.state.phone_node),
            "peloton_active": self._is_node_running(self.state.peloton_node),
            "master_active": self._is_node_running(self.state.output_node),
        }

    def levels(self) -> dict[str, float | None]:
        return {
            "phone_level": self._sample_level(self.state.phone_node),
            "peloton_level": self._sample_level(self.state.peloton_node),
            "master_level": self._sample_level(self.state.output_node),
        }

    def _set_node_volume(self, node_name: str | None, value: float) -> None:
        if not node_name:
            return
        subprocess.run(["wpctl", "set-volume", node_name, f"{value:.3f}"], check=False)

    def _sample_level(self, node_name: str | None) -> float | None:
        if not node_name:
            return None
        target = shlex.quote(str(node_name))
        cmds = [
            (
                f"timeout 0.25s pw-cat --record --target {target} --format f32 --rate 16000 --channels 1 - 2>/dev/null "
                "| head -c 4096"
            ),
            (
                f"timeout 0.25s pw-record --target {target} --format f32 --rate 16000 --channels 1 - 2>/dev/null "
                "| head -c 4096"
            ),
        ]
        raw = b""
        for cmd in cmds:
            res = subprocess.run(["bash", "-lc", cmd], capture_output=True, check=False)
            if res.stdout:
                raw = res.stdout
                break
        if len(raw) < 4:
            return None

        # little-endian float32 mono
        usable = len(raw) - (len(raw) % 4)
        if usable < 8:
            return None
        try:
            samples = list(struct.unpack("<" + "f" * (usable // 4), raw[:usable]))
        except struct.error:
            return None
        if not samples:
            return None

        # sanitize and remove DC offset so constant bias/noise floor doesn't look active.
        samples = [s for s in samples if math.isfinite(s)]
        if not samples:
            return None
        mean = sum(samples) / len(samples)
        centered = [s - mean for s in samples]
        variance = sum(s * s for s in centered) / len(centered)
        rms = math.sqrt(variance)
        peak = max(abs(s) for s in centered)

        # Hard gate for idle/noise floor.
        if peak < 0.0008 and rms < 0.00025:
            level_raw = 0.0
        else:
            # Blend RMS + peak for visibly responsive meters without constant saturation.
            level_raw = max(rms * 18.0, peak * 4.5)

        key = str(node_name)
        prev = self._level_smooth.get(key, 0.0)
        # Attack faster, release slower for natural meter motion.
        if level_raw > prev:
            smooth = prev * 0.45 + level_raw * 0.55
        else:
            smooth = prev * 0.82 + level_raw * 0.18
        smooth = max(0.0, min(1.0, smooth))
        self._level_smooth[key] = smooth
        return smooth

    def _is_node_running(self, node_name: str | None) -> bool:
        if not node_name:
            return False
        result = subprocess.run(["wpctl", "inspect", node_name], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return False
        text = result.stdout.lower()
        if "state" in text and "running" in text:
            return True
        # fallback for some pipewire versions
        return bool(re.search(r"\bactive\b", text))

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
