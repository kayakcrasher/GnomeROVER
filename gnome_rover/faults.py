"""Fault injection for stress-testing the mission."""
import random
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from .quiet import say


FAULT_TYPES = (
    "stuck_joint", "battery_dead", "lost_mesh",
    "drifting", "comms_jam", "stuck_drone", "weather_gone",
)


@dataclass
class Fault:
    target: str
    kind: str
    duration_s: float = -1.0     # -1 = permanent
    applied_at: float = field(default_factory=time.time)
    payload: dict = field(default_factory=dict)

    def expired(self) -> bool:
        if self.duration_s < 0:
            return False
        return time.time() - self.applied_at > self.duration_s

    def describe(self):
        d = "permanent" if self.duration_s < 0 else f"{self.duration_s}s"
        return f"{self.kind}@{self.target} ({d})"


class FaultInjector:
    def __init__(self, base):
        self.base = base
        self.faults: List[Fault] = []
        self.applied_effects: Dict[str, int] = {}   # for reporting counts

    # --- inject / clear ---

    def inject(self, target: str, kind: str, duration_s: float = -1.0, **payload):
        if kind not in FAULT_TYPES:
            print(f"[FAULT] unknown kind: {kind}")
            print(f"        valid: {', '.join(FAULT_TYPES)}")
            return False
        f = Fault(target=target, kind=kind, duration_s=duration_s, payload=payload)
        self.faults.append(f)
        say(f"[FAULT] injected {f.describe()}")
        self._apply_once(f)
        return True

    def clear(self, target: Optional[str] = None):
        if target in (None, "all", "*"):
            n = len(self.faults)
            self.faults.clear()
            print(f"[FAULT] cleared {n} fault(s)")
        else:
            before = len(self.faults)
            self.faults = [f for f in self.faults if f.target != target]
            print(f"[FAULT] cleared {before - len(self.faults)} fault(s) on {target}")

    def list_active(self):
        if not self.faults:
            print("[FAULT] no active faults")
            return
        print(f"[FAULT] {len(self.faults)} active:")
        for f in self.faults:
            print(f"  {f.describe()}")

    # --- tick ---

    def tick(self):
        """Called every base.tick. Applies ongoing effects, drops expired."""
        self.faults = [f for f in self.faults if not f.expired()]
        for f in list(self.faults):
            self._apply_tick(f)

    # --- effect handlers ---

    def _apply_once(self, f: Fault):
        b = self.base
        if f.kind == "battery_dead":
            # drones
            d = b.drones.get(f.target)
            if d:
                d.battery = 0.0
                say(f"[FAULT] {f.target} battery forced to 0")
                self.applied_effects[f.kind] = self.applied_effects.get(f.kind, 0) + 1
                return
            # infra
            it = b.infra.items.get(f.target)
            if it:
                it.battery = 0.0
                say(f"[FAULT] {f.target} battery forced to 0")
                self.applied_effects[f.kind] = self.applied_effects.get(f.kind, 0) + 1
                return
            say(f"[FAULT] no unit named {f.target}")

        elif f.kind == "lost_mesh":
            mesh = getattr(b, "mesh", None)
            if mesh and f.target in mesh.nodes:
                mesh.remove_node(f.target)
                say(f"[FAULT] {f.target} removed from mesh")
                self.applied_effects[f.kind] = self.applied_effects.get(f.kind, 0) + 1

        elif f.kind == "stuck_drone":
            d = b.drones.get(f.target)
            if d:
                d.status = "stuck"
                say(f"[FAULT] {f.target} stuck (will not move)")

        elif f.kind == "weather_gone":
            it = b.infra.items.get(f.target)
            if it and it.kind == "weather":
                it.sample_interval = 1e9   # never sample again
                say(f"[FAULT] {f.target} sampling halted")

        elif f.kind == "comms_jam":
            # flag on base; enqueue checks it
            b._comms_jammed = True
            say(f"[FAULT] uplink jammed")

        elif f.kind == "drifting":
            # nothing to do at inject time; effect happens per tick
            say(f"[FAULT] {f.target} drifting enabled")

        elif f.kind == "stuck_joint":
            # capture the joint's current angle so we hold it
            if f.target.startswith("rover."):
                joint_name = f.target.split(".", 1)[1]
                for leg in b.rover.legs.values():
                    for j in leg.all_joints():
                        if j.name == joint_name:
                            f.payload["held_angle"] = j.angle
                            say(f"[FAULT] joint {joint_name} stuck at {j.angle:.1f}")
                            return
            say(f"[FAULT] no joint named {f.target}")

    def _apply_tick(self, f: Fault):
        b = self.base
        if f.kind == "stuck_joint":
            # hold joint at payload angle
            held = f.payload.get("held_angle")
            if held is None:
                return
            joint_name = f.target.split(".", 1)[1] if "." in f.target else f.target
            for leg in b.rover.legs.values():
                for j in leg.all_joints():
                    if j.name == joint_name:
                        j.angle = held
                        j.target_angle = held

        elif f.kind == "drifting":
            unit = b.world.units.get(f.target)
            if unit:
                unit.x += random.uniform(-0.05, 0.05)
                unit.y += random.uniform(-0.05, 0.05)

        elif f.kind == "stuck_drone":
            d = b.drones.get(f.target)
            if d:
                d.status = "stuck"
                d.route = []   # kill any active route

        elif f.kind == "lost_mesh":
            mesh = getattr(b, "mesh", None)
            if mesh and f.target in mesh.nodes:
                mesh.remove_node(f.target)

        elif f.kind == "comms_jam":
            b._comms_jammed = True
