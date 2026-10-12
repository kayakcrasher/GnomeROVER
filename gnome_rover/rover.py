"""The GnomeROVER itself: four legs, modular, threaded."""
import math
import time
import threading
from enum import Enum
from typing import Dict, Any, Optional

from .legs import Leg, Joint, JointType, LegPosition
from .modules import RoverModule


class GaitType(Enum):
    STAND = "stand"
    WALK = "walk"
    TROT = "trot"


class Rover:
    def __init__(self, name: str = "GnomeROVER"):
        self.name = name
        self.legs: Dict[LegPosition, Leg] = {}
        self.modules: Dict[str, RoverModule] = {}
        self.gait = GaitType.STAND
        self.running = False
        self.gait_phase = 0.0
        self._lock = threading.Lock()
        self._build_legs()

    def _build_legs(self):
        for pos in LegPosition:
            hip = Joint(f"{pos.value}_hip", JointType.HIP, min_angle=-45, max_angle=45)
            sh = Joint(f"{pos.value}_shoulder", JointType.SHOULDER, min_angle=-60, max_angle=60)
            kn = Joint(f"{pos.value}_knee", JointType.KNEE, min_angle=-90, max_angle=90)
            self.legs[pos] = Leg(pos, hip, sh, kn)
        print(f"[ROVER] Built 4 legs: {[p.value for p in self.legs]}")

    def plug_in(self, module: RoverModule) -> bool:
        with self._lock:
            if module.name in self.modules:
                print(f"[ROVER] '{module.name}' already plugged in.")
                return False
            self.modules[module.name] = module
            module.on_attach(self)
            module.enabled = True
            return True

    def unplug(self, module_name: str) -> bool:
        with self._lock:
            m = self.modules.pop(module_name, None)
            if m:
                m.enabled = False
                m.on_detach()
                return True
            return False

    def get_module(self, name: str) -> Optional[RoverModule]:
        return self.modules.get(name)

    def stand(self):
        print("[ROVER] Standing.")
        self.gait = GaitType.STAND
        for leg in self.legs.values():
            leg.set_pose(hip=0, shoulder=-20, knee=40)

    def walk(self):
        print("[ROVER] Walk gait.")
        self.gait = GaitType.WALK

    def trot(self):
        print("[ROVER] Trot gait.")
        self.gait = GaitType.TROT

    def _apply_gait(self, dt: float):
        if self.gait == GaitType.STAND:
            return
        self.gait_phase = (self.gait_phase + dt * 1.2) % (2 * math.pi)

        if self.gait == GaitType.TROT:
            pairs = {
                LegPosition.FRONT_LEFT: 0.0,
                LegPosition.BACK_RIGHT: 0.0,
                LegPosition.FRONT_RIGHT: math.pi,
                LegPosition.BACK_LEFT: math.pi,
            }
            for pos, off in pairs.items():
                p = self.gait_phase + off
                self.legs[pos].set_pose(20 * math.sin(p),
                                        -20 + 15 * math.cos(p),
                                        40 + 20 * math.sin(p + math.pi / 2))
        elif self.gait == GaitType.WALK:
            order = [LegPosition.FRONT_LEFT, LegPosition.BACK_RIGHT,
                     LegPosition.FRONT_RIGHT, LegPosition.BACK_LEFT]
            for i, pos in enumerate(order):
                p = self.gait_phase + i * (math.pi / 2)
                self.legs[pos].set_pose(15 * math.sin(p),
                                        -20 + 10 * math.cos(p),
                                        40 + 15 * math.sin(p + math.pi / 2))

    def _tick(self, dt: float):
        self._apply_gait(dt)
        for leg in self.legs.values():
            leg.update(dt)
        for m in self.modules.values():
            if m.enabled:
                m.update(dt)

    def start(self, hz: float = 20.0):
        self.running = True
        self._thread = threading.Thread(target=self._loop, args=(hz,), daemon=True)
        self._thread.start()
        print(f"[ROVER] Started @ {hz} Hz")

    def _loop(self, hz: float):
        dt = 1.0 / hz
        while self.running:
            t0 = time.perf_counter()
            self._tick(dt)
            time.sleep(max(0, dt - (time.perf_counter() - t0)))

    def stop(self):
        self.running = False
        print("[ROVER] Stopped.")

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "gait": self.gait.value,
            "legs": {pos.value: {"hip": round(l.hip.angle, 1),
                                 "shoulder": round(l.shoulder.angle, 1),
                                 "knee": round(l.knee.angle, 1)}
                     for pos, l in self.legs.items()},
            "modules": {n: m.read() for n, m in self.modules.items()},
        }

    def pretty_print(self):
        s = self.status()
        print(f"\n=== {s['name']} | gait={s['gait']} ===")
        for leg, j in s["legs"].items():
            print(f"  {leg}: hip={j['hip']:>6}  sh={j['shoulder']:>6}  kn={j['knee']:>6}")
        for n, d in s["modules"].items():
            print(f"  [{n}] {d}")
        print()
