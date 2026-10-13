"""Example plugin: a simple beacon that reports position periodically."""
from gnome_rover.modules import RoverModule


class BeaconModule(RoverModule):
    def __init__(self):
        super().__init__("Beacon")
        self.pulses = 0

    def update(self, dt: float):
        if self.enabled:
            self.pulses += 1
            self._data = {"pulses": self.pulses}
