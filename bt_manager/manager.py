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
import re


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

        # role -> controller MAC (adapter pinning)
        self.controller_map: dict[str, str | None] = {
            "phone": None,
            "peloton": None,
            "headphones": None,
        }

        self._load()
        self.refresh_status()

    def _run_btctl(self, commands: list[str], controller: str | None = None) -> str:
        script = "\n".join(commands + ["quit", ""])
        cmd = ["bluetoothctl"]
        if controller:
            cmd += ["--controller", controller]
        result = subprocess.run(
            cmd,
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "bluetoothctl command failed")
        return result.stdout

    def controllers(self) -> list[dict[str, Any]]:
        out = self._run_btctl(["list"])
        ctrls: list[dict[str, Any]] = []
        for line in out.splitlines():
            m = re.match(r"^Controller\s+([0-9A-Fa-f:]{17})\s+(.+?)(\s+\[default\])?$", line.strip())
            if not m:
                continue
            ctrls.append({
                "mac": m.group(1).upper(),
                "name": m.group(2).strip(),
                "default": bool(m.group(3)),
            })
        return ctrls

    def set_role_controller(self, role: str, controller_mac: str | None) -> dict[str, Any]:
        slot = self._slot(role)
        _ = slot  # validate role
        self.controller_map[role] = controller_mac.upper() if controller_mac else None
        self._save()
        return self.status()

    def _role_controller(self, role: str) -> str | None:
        return self.controller_map.get(role)

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
        ], controller=self._role_controller(role))
        self.refresh_status()
        return self.status()

    def connect(self, role: str) -> dict[str, Any]:
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl(["power on", f"connect {slot.mac}"], controller=self._role_controller(role))
        self.refresh_status()
        return self.status()

    def quick_connect(self, role: str) -> dict[str, Any]:
        """One-tap flow for assigned device: trust/pair/connect best-effort."""
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl([
            "power on",
            "agent on",
            "default-agent",
            f"trust {slot.mac}",
            f"pair {slot.mac}",
            f"connect {slot.mac}",
        ], controller=self._role_controller(role))
        self.refresh_status()
        return self.status()

    def disconnect(self, role: str) -> dict[str, Any]:
        slot = self._slot(role)
        self._require_mac(slot)
        self._run_btctl([f"disconnect {slot.mac}"], controller=self._role_controller(role))
        self.refresh_status()
        return self.status()

    def reconnect_all(self) -> dict[str, Any]:
        for role in ("phone", "peloton", "headphones"):
            slot = self._slot(role)
            if slot.mac:
                try:
                    self._run_btctl([f"connect {slot.mac}"], controller=self._role_controller(role))
                except RuntimeError:
                    continue
        self.refresh_status()
        return self.status()

    def _connected_devices(self) -> list[dict[str, str]]:
        out = self._run_btctl(["devices Connected"])
        devices: list[dict[str, str]] = []
        for line in out.splitlines():
            m = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line.strip())
            if m:
                devices.append({"mac": m.group(1).upper(), "name": m.group(2).strip()})
        return devices

    def refresh_status(self) -> dict[str, Any]:
        connected_devices = self._connected_devices()
        connected_macs = {d["mac"] for d in connected_devices}

        for slot in (self.phone, self.peloton, self.headphones):
            if slot.mac:
                try:
                    info = self._parse_info(self._device_info(slot.mac))
                    slot.paired = bool(info.get("paired"))
                    slot.alias = info.get("alias") or slot.alias
                except RuntimeError:
                    pass
                slot.connected = slot.mac.upper() in connected_macs
            else:
                slot.connected = False

            if not slot.connected and slot.alias:
                slot.connected = any(slot.alias.lower() in d["name"].lower() for d in connected_devices)

            if not slot.connected and not slot.mac:
                keywords = {
                    "phone": ["iphone", "ios", "phone"],
                    "peloton": ["peloton"],
                    "headphones": ["airpods", "headphone", "buds", "nothing"],
                }[slot.name]
                match = next((d for d in connected_devices if any(k in d["name"].lower() for k in keywords)), None)
                if match:
                    slot.connected = True
                    slot.alias = match["name"]

        return self.status()

    def enable_pairing_mode(self, seconds: int = 120) -> dict[str, Any]:
        seconds = max(15, min(int(seconds), 300))
        controllers = [c["mac"] for c in self.controllers()]
        if not controllers:
            # fallback default controller path
            cmd = (
                "bluetoothctl power on; "
                "bluetoothctl pairable on; "
                "bluetoothctl discoverable on; "
                f"sleep {seconds}; "
                "bluetoothctl pairable off; "
                "bluetoothctl discoverable off"
            )
            subprocess.Popen(["bash", "-lc", cmd])
            return {"pairing_mode": True, "seconds": seconds, "controllers": []}

        for ctrl in controllers:
            self._run_btctl(["power on", "pairable on", "discoverable on"], controller=ctrl)

        def disable_all() -> None:
            import time
            time.sleep(seconds)
            for ctrl in controllers:
                try:
                    self._run_btctl(["pairable off", "discoverable off"], controller=ctrl)
                except Exception:
                    pass

        import threading
        threading.Thread(target=disable_all, daemon=True).start()
        return {"pairing_mode": True, "seconds": seconds, "controllers": controllers}

    def scan(self, seconds: int = 6) -> list[dict[str, str]]:
        seconds = max(2, min(int(seconds), 20))
        cmd = (
            f"timeout {seconds}s bluetoothctl --timeout {seconds} scan on >/tmp/bt_scan.out 2>&1; "
            "bluetoothctl devices"
        )
        result = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, check=False)
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(result.stderr.strip() or "Bluetooth scan failed")

        devices: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in result.stdout.splitlines():
            m = re.match(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+)$", line.strip())
            if not m:
                continue
            mac, name = m.group(1).upper(), m.group(2).strip()
            if mac in seen:
                continue
            seen.add(mac)
            devices.append({"mac": mac, "name": name})
        return devices

    def status(self) -> dict[str, Any]:
        return {
            "phone": asdict(self.phone),
            "peloton": asdict(self.peloton),
            "headphones": asdict(self.headphones),
            "controllers": self.controllers(),
            "controller_map": self.controller_map,
            "connected_devices": self._connected_devices(),
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
        if isinstance(payload.get("controller_map"), dict):
            for role in ("phone", "peloton", "headphones"):
                if role in payload["controller_map"]:
                    value = payload["controller_map"].get(role)
                    self.controller_map[role] = value.upper() if isinstance(value, str) else None
