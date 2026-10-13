"""Wave 1 infrastructure: home base, weather, relay, depot."""
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from .power import PowerMode, drain_for, can_move, describe
from .compass import name_of, bearing_between, distance_between


class Deployable:
    """Base for any static infra the rover places on the surface."""
    def __init__(self, name: str, kind: str, x: float, y: float):
        self.name = name
        self.kind = kind
        self.x = x
        self.y = y
        self.deployed_at = time.time()
        self.battery = 100.0
        self.mode = PowerMode.NORMAL
        self.status = "deployed"

    def tick(self, dt: float):
        # passive solar recharge / drain
        if self.kind in ("home", "repeater", "weather"):
            self.battery = min(100.0, self.battery + 0.02 * dt * 10)  # trickle
        else:
            self.battery = max(0.0, self.battery - 0.005 * dt * 10)

    def report(self):
        return {"name": self.name, "kind": self.kind,
                "x": round(self.x, 2), "y": round(self.y, 2),
                "battery": round(self.battery, 1),
                "status": self.status}


class HomeBase(Deployable):
    """The mother node. Charger pad + comms hub + origin of all roads."""
    def __init__(self, name: str, x: float, y: float):
        super().__init__(name, "home", x, y)
        self.charger_capacity_kwh = 50.0
        self.solar_area_m2 = 8.0
        self.docked_units: List[str] = []

    def tick(self, dt: float):
        super().tick(dt)
        # charge docked units at faster rate than they would on their own
        # (their own tick handles it, this is just bookkeeping)

    def report(self):
        r = super().report()
        r.update({"kwh": self.charger_capacity_kwh,
                  "solar_m2": self.solar_area_m2,
                  "dock": len(self.docked_units)})
        return r


class WeatherStation(Deployable):
    """Mast with wind, temp, pressure, radiation sensors."""
    def __init__(self, name: str, x: float, y: float):
        super().__init__(name, "weather", x, y)
        self.readings: List[dict] = []
        self.sample_interval = 30.0   # seconds
        self._last_sample = 0.0

    def tick(self, dt: float):
        super().tick(dt)
        now = time.time()
        if now - self._last_sample >= self.sample_interval:
            self._last_sample = now
            # deterministic pseudo-weather based on position + time
            phase = (now / 3600.0) % 1.0
            self.readings.append({
                "t": round(now, 1),
                "wind_ms": round(abs(3.0 + 4.0 * math.sin(phase * 6.28)), 2),
                "temp_c": round(-60.0 + 40.0 * phase, 1),
                "pressure_pa": round(610.0 + 20.0 * math.cos(phase * 6.28), 1),
                "rad_usv": round(0.15 + 0.05 * abs(math.sin(phase * 12.56)), 3),
            })
            if len(self.readings) > 200:
                self.readings = self.readings[-200:]

    def latest(self):
        return self.readings[-1] if self.readings else None

    def storm_warning(self) -> bool:
        r = self.latest()
        return r is not None and r["wind_ms"] > 6.0

    def report(self):
        r = super().report()
        r["readings"] = len(self.readings)
        r["latest"] = self.latest()
        r["storm_warning"] = self.storm_warning()
        return r


class RadioRepeater(Deployable):
    """Mesh node — extends comms range around its position."""
    def __init__(self, name: str, x: float, y: float):
        super().__init__(name, "repeater", x, y)
        self.range_m = 30.0

    def covers(self, x: float, y: float) -> bool:
        return distance_between(self.x, self.y, x, y) <= self.range_m

    def report(self):
        r = super().report()
        r["range_m"] = self.range_m
        return r


class Depot(Deployable):
    """Cache of supplies at a waypoint."""
    def __init__(self, name: str, x: float, y: float, kind="generic"):
        super().__init__(name, "depot", x, y)
        self.depot_kind = kind
        self.contents: Dict[str, int] = {}

    def stock(self, item: str, qty: int = 1):
        self.contents[item] = self.contents.get(item, 0) + qty

    def take(self, item: str, qty: int = 1) -> bool:
        if self.contents.get(item, 0) >= qty:
            self.contents[item] -= qty
            return True
        return False

    def report(self):
        r = super().report()
        r["kind_of"] = self.depot_kind
        r["contents"] = dict(self.contents)
        return r


class InfraManager:
    """Holds all deployed infrastructure in one place."""
    def __init__(self):
        self.items: Dict[str, Deployable] = {}

    def add(self, item: Deployable):
        if item.name in self.items:
            print(f"[INFRA] '{item.name}' already deployed")
            return False
        self.items[item.name] = item
        print(f"[INFRA] deployed {item.kind} '{item.name}' at "
              f"({item.x:.1f}, {item.y:.1f})")
        return True

    def tick(self, dt: float):
        for it in self.items.values():
            it.tick(dt)

    def get(self, name: str) -> Optional[Deployable]:
        return self.items.get(name)

    def of_kind(self, kind: str) -> List[Deployable]:
        return [i for i in self.items.values() if i.kind == kind]

    def weather(self) -> Optional[WeatherStation]:
        ws = self.of_kind("weather")
        return ws[0] if ws else None

    def repeaters(self) -> List[RadioRepeater]:
        return [i for i in self.of_kind("repeater") if isinstance(i, RadioRepeater)]

    def comms_covers(self, x: float, y: float) -> bool:
        """Is (x, y) covered by home OR any repeater?"""
        home = self.items.get("HomeBase")
        if home and distance_between(home.x, home.y, x, y) <= 30.0:
            return True
        return any(rep.covers(x, y) for rep in self.repeaters())

    def pretty(self):
        if not self.items:
            print("[INFRA] nothing deployed yet")
            return
        print(f"--- INFRASTRUCTURE ({len(self.items)}) ---")
        for it in self.items.values():
            print(f"  {it.kind:>10}  {it.name:<14} "
                  f"({it.x:>7.1f}, {it.y:>7.1f})  bat={it.battery:>5.1f}")
