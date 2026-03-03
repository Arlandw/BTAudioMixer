"""PipeWire-backed audio engine.

Phase 1 implementation:
- track two input gains + master
- apply volume by PipeWire node name via `wpctl`
- keep state in-memory for UI/API use
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import subprocess
from typing import Any


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

    def _set_node_volume(self, node_name: str | None, value: float) -> None:
        if not node_name:
            return
        subprocess.run(["wpctl", "set-volume", node_name, f"{value:.3f}"], check=False)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
