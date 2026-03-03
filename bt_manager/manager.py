"""Bluetooth manager skeleton.

Responsibilities:
- discover adapters/devices
- pair/connect known devices by role (phone, peloton, headphones)
- expose connection state + reconnect actions
"""

from dataclasses import dataclass

@dataclass
class DeviceRole:
    name: str
    mac: str | None = None
    connected: bool = False

class BTManager:
    def __init__(self) -> None:
        self.phone = DeviceRole(name="phone")
        self.peloton = DeviceRole(name="peloton")
        self.headphones = DeviceRole(name="headphones")

    def status(self) -> dict:
        return {
            "phone": self.phone,
            "peloton": self.peloton,
            "headphones": self.headphones,
        }
