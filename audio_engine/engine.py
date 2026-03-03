"""Audio engine skeleton for PipeWire graph management."""

class AudioEngine:
    def __init__(self) -> None:
        self.phone_gain = 0.5
        self.peloton_gain = 0.5
        self.master_gain = 0.8

    def set_gains(self, phone: float, peloton: float, master: float) -> None:
        self.phone_gain = max(0.0, min(1.0, phone))
        self.peloton_gain = max(0.0, min(1.0, peloton))
        self.master_gain = max(0.0, min(1.0, master))
