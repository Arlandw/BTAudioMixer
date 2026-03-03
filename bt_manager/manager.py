"""Bluetooth manager for role-based device pairing and connection.

This module wraps `bluetoothctl` with predictable role slots:
- phone (input A)
- peloton (input B)
- headphones (output)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(os.getenv("BTMIXER_CONFIG", "./config/devices.json"))


@dataclass
class DeviceRole:
    name: str
    mac: str | None = None
    alias: str | None = None
    connected: bool = False
    paired: bool = False


class BTManager:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        self.phone = DeviceRole(name="phone")
        self.peloton = DeviceRole(name="peloton")
        self.headphones = DeviceRole(name="headphones")

        self._load()
        self.refresh_status()

    def _run_btctl(self, commands: list[str]) -> str:
        script = "\n".join(commands + ["quit", ""])
        result = subprocess.run(
            ["bluetoothctl"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "bluetoothctl command failed")
        return result.stdout

    def _device_info(self, mac: str) -> str:
        return self._run_btctl([f"info {mac}"])

    def _parse_info(self, info_text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "connected": "Connected: yes" in info_text,
            "paired": "Paired: yes" in info_text,
            "alias": None,
        }
        for line in info_text.splitlines():
            line = line.strip()
            if line.startswith("Alias:"):
                payload["alias"] = line.split("Alias:", 1)[1].strip()
                break
        return payload

    def assign_role(self, role: str, mac: str) -> dict[str, Any]:
        slot = self._slot(role)
        info = self._parse_info(self._device_info(mac))
        slot.mac = mac
        slot.alias = info.get("alias")
        slot.paired = bool(info.get("paired"))
        slot.connected = bool(info.get("connected"))
        self._save()
        return self.status()

    def pair(self, role: str) -> dict[str, Any]:
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl([
            "power on",
            "agent on",
            "default-agent",
            f"pair {slot.mac}",
            f"trust {slot.mac}",
        ])
        self.refresh_status()
        return self.status()

    def connect(self, role: str) -> dict[str, Any]:
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl(["power on", f"connect {slot.mac}"])
        self.refresh_status()
        return self.status()

    def disconnect(self, role: str) -> dict[str, Any]:
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl([f"disconnect {slot.mac}"])
        self.refresh_status()
        return self.status()

    def reconnect_all(self) -> dict[str, Any]:
        for role in ("phone", "peloton", "headphones"):
            slot = self._slot(role)
            if slot.mac:
                try:
                    self._run_btctl([f"connect {slot.mac}"])
                except RuntimeError:
                    continue
        self.refresh_status()
        return self.status()

    def refresh_status(self) -> dict[str, Any]:
        for slot in (self.phone, self.peloton, self.headphones):
            if not slot.mac:
                continue
            try:
                info = self._parse_info(self._device_info(slot.mac))
            except RuntimeError:
                continue
            slot.connected = bool(info.get("connected"))
            slot.paired = bool(info.get("paired"))
            slot.alias = info.get("alias") or slot.alias
        return self.status()

    def status(self) -> dict[str, Any]:
        return {
            "phone": asdict(self.phone),
            "peloton": asdict(self.peloton),
            "headphones": asdict(self.headphones),
        }

    def _slot(self, role: str) -> DeviceRole:
        role = role.lower().strip()
        if role not in {"phone", "peloton", "headphones"}:
            raise ValueError(f"Unknown role: {role}")
        return getattr(self, role)

    @staticmethod
    def _require_mac(slot: DeviceRole) -> None:
        if not slot.mac:
            raise ValueError(f"Role '{slot.name}' has no assigned MAC")

    def _save(self) -> None:
        payload = self.status()
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self.config_path.exists():
            return
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        for role in ("phone", "peloton", "headphones"):
            if role in payload:
                slot = self._slot(role)
                slot.mac = payload[role].get("mac")
                slot.alias = payload[role].get("alias")
                slot.connected = bool(payload[role].get("connected", False))
                slot.paired = bool(payload[role].get("paired", False))
