"""Shared spatial map: landmarks, units, positions."""
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class Landmark:
    name: str
    x: float
    y: float
    kind: str = "generic"


@dataclass
class Unit:
    name: str
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    battery: float = 100.0
    status: str = "stowed"      # stowed | deployed | returning | dead
    role: str = "generic"


class World:
    def __init__(self):
        self.landmarks: Dict[str, Landmark] = {}
        self.units: Dict[str, Unit] = {}

    def add_landmark(self, name, x, y, kind="generic"):
        self.landmarks[name] = Landmark(name, x, y, kind)

    def add_unit(self, name, role="generic"):
        self.units[name] = Unit(name=name, role=role)

    def move_unit(self, name, x, y, heading=None):
        u = self.units.get(name)
        if not u:
            return
        u.x, u.y = x, y
        if heading is not None:
            u.heading = heading

    def distance(self, name_a, name_b):
        a = self.units.get(name_a) or self.landmarks.get(name_a)
        b = self.units.get(name_b) or self.landmarks.get(name_b)
        if not a or not b:
            return None
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    def pretty(self):
        print(f"--- LANDMARKS ({len(self.landmarks)}) ---")
        for l in self.landmarks.values():
            print(f"  {l.kind:>8}  {l.name:<14} ({l.x:>7.1f}, {l.y:>7.1f})")
        print(f"--- UNITS ({len(self.units)}) ---")
        for u in self.units.values():
            print(f"  {u.role:>10}  {u.name:<14} ({u.x:>7.1f}, {u.y:>7.1f})"
                  f"  bat={u.battery:>5.1f}  [{u.status}]")
