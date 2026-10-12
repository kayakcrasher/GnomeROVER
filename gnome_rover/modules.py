"""Pluggable modules for GnomeROVER."""
import math
import time
from typing import Dict, Any, Optional
from abc import ABC


class RoverModule(ABC):
    def __init__(self, name: str):
        self.name = name
        self.rover: Optional["Rover"] = None
        self.enabled = False
        self._data: Dict[str, Any] = {}

    def on_attach(self, rover):
        self.rover = rover
        print(f"[MODULE] '{self.name}' attached to rover.")

    def on_detach(self):
        print(f"[MODULE] '{self.name}' detached.")
        self.rover = None

    def update(self, dt: float):
        pass

    def read(self) -> Dict[str, Any]:
        return self._data


class CameraModule(RoverModule):
    def __init__(self):
        super().__init__("Camera")
        self.pan = 0.0
        self.tilt = 0.0
        self.recording = False

    def update(self, dt: float):
        if self.enabled:
            self.pan = (self.pan + 30 * dt) % 360
            self._data = {"pan": round(self.pan, 1),
                          "tilt": self.tilt,
                          "recording": self.recording}

    def look_at(self, pan: float, tilt: float):
        self.pan = pan
        self.tilt = max(-90, min(90, tilt))
        print(f"[CAMERA] pan={pan} tilt={tilt}")


class SensorModule(RoverModule):
    def __init__(self):
        super().__init__("Sensor")
        self.temperature = 22.5
        self.distance_cm = 100.0
        self.battery_pct = 100.0

    def update(self, dt: float):
        if self.enabled:
            self.temperature += math.sin(time.time()) * 0.01
            self._data = {
                "temp_c": round(self.temperature, 2),
                "distance_cm": round(self.distance_cm, 1),
                "battery": round(self.battery_pct, 1),
            }


class ArmModule(RoverModule):
    def __init__(self):
        super().__init__("Arm")
        self.base_angle = 0.0
        self.elbow_angle = 0.0
        self.gripper_open = True

    def update(self, dt: float):
        if self.enabled:
            self._data = {"base": round(self.base_angle, 1),
                          "elbow": round(self.elbow_angle, 1),
                          "grip_open": self.gripper_open}

    def grab(self):
        self.gripper_open = False
        print("[ARM] Gripper closed.")

    def release(self):
        self.gripper_open = True
        print("[ARM] Gripper opened.")
