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

        phone_node = pick(["iphone", "ios", "phone"])
        peloton_node = pick(["peloton"])
        output_node = pick(["airpods", "headphones", "buds"])

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
        cmd = (
            f"timeout 0.25s pw-record --target {target} --format s16 --rate 16000 --channels 1 - 2>/dev/null "
            "| head -c 4096"
        )
        res = subprocess.run(["bash", "-lc", cmd], capture_output=True, check=False)
        raw = res.stdout or b""
        if len(raw) < 4:
            return None

        # little-endian signed 16-bit mono
        samples = []
        for i in range(0, len(raw) - 1, 2):
            v = int.from_bytes(raw[i:i+2], byteorder="little", signed=True)
            samples.append(v / 32768.0)
        if not samples:
            return None

        # Remove DC offset so constant bias/noise floor doesn't look like active audio.
        mean = sum(samples) / len(samples)
        variance = sum((s - mean) ** 2 for s in samples) / len(samples)
        rms = math.sqrt(variance)

        # Convert to dBFS and gate low-level noise.
        db = 20.0 * math.log10(max(rms, 1e-6))
        min_db = -35.0
        max_db = 0.0
        if db <= min_db:
            return 0.0

        level = (db - min_db) / (max_db - min_db)
        return max(0.0, min(1.0, level))

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
