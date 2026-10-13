"""System diagnostics: health checks across the whole stack."""
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable, Any


class Level(Enum):
    OK      = ("OK",     "green")
    WARN    = ("WARN",   "yellow")
    FAIL    = ("FAIL",   "red")
    UNKNOWN = ("?",      "gray")

    @property
    def label(self): return self.value[0]


@dataclass
class Check:
    name: str
    level: Level
    detail: str = ""
    data: Any = None

    def line(self):
        return f"  [{self.level.label:>4}] {self.name:<28} {self.detail}"


@dataclass
class Report:
    checks: List[Check] = field(default_factory=list)
    t: float = field(default_factory=time.time)

    def add(self, name, level, detail="", data=None):
        self.checks.append(Check(name, level, detail, data))

    def worst(self) -> Level:
        order = {Level.FAIL: 3, Level.WARN: 2, Level.UNKNOWN: 1, Level.OK: 0}
        return max(self.checks, key=lambda c: order[c.level]).level if self.checks else Level.OK

    def count(self, level):
        return sum(1 for c in self.checks if c.level == level)

    def pretty(self, show_ok=True):
        w = self.worst()
        print(f"=== DIAGNOSTICS  overall={w.label}  "
              f"({self.count(Level.OK)} ok / {self.count(Level.WARN)} warn / "
              f"{self.count(Level.FAIL)} fail) ===")
        for c in self.checks:
            if not show_ok and c.level == Level.OK:
                continue
            print(c.line())
        print()


# ============================================================
# individual check functions — each returns a Check
# ============================================================

def check_rover(rover, base) -> List[Check]:
    out = []
    # joint ranges
    bad = []
    for pos, leg in rover.legs.items():
        for j in leg.all_joints():
            if not (j.min_angle - 1 <= j.angle <= j.max_angle + 1):
                bad.append(f"{j.name}={j.angle:.1f}")
    if bad:
        out.append(Check("rover.joints", Level.FAIL,
                         f"{len(bad)} joint(s) out of range"))
    else:
        out.append(Check("rover.joints", Level.OK, "12 joints nominal"))

    # gait
    if rover.running:
        out.append(Check("rover.loop", Level.OK, f"gait={rover.gait.value}"))
    else:
        out.append(Check("rover.loop", Level.WARN, "rover thread not running"))
    return out


def check_modules(rover) -> List[Check]:
    out = []
    if not rover.modules:
        out.append(Check("modules", Level.WARN, "none plugged in"))
        return out
    for name, m in rover.modules.items():
        if m.enabled:
            out.append(Check(f"module.{name}", Level.OK, "enabled"))
        else:
            out.append(Check(f"module.{name}", Level.WARN, "disabled"))
    return out


def check_drones(base) -> List[Check]:
    out = []
    if not base.drones:
        out.append(Check("drones", Level.UNKNOWN, "none"))
        return out
    for d in base.drones.values():
        r = d.report()
        bat = r.get("battery", 100)
        status = r.get("status", "?")
        mode = r.get("mode", "?")
        if bat <= 5:
            lvl = Level.FAIL
        elif bat < 25:
            lvl = Level.WARN
        else:
            lvl = Level.OK
        out.append(Check(f"drone.{d.name}", lvl,
                         f"bat={bat}% mode={mode} [{status}]"))
    return out


def check_infra(base) -> List[Check]:
    out = []
    if not base.infra.items:
        out.append(Check("infra", Level.WARN, "nothing deployed"))
        return out
    for it in base.infra.items.values():
        lvl = Level.OK
        detail = f"bat={it.battery:.1f}%"
        if it.battery < 25:
            lvl = Level.WARN
            detail += " LOW"
        if it.battery < 10:
            lvl = Level.FAIL
        # weather staleness
        if it.kind == "weather":
            ws = it
            r = ws.latest()
            if r:
                age = time.time() - r["t"]
                detail += f" last_sample={age:.0f}s ago"
                if age > ws.sample_interval * 3:
                    lvl = Level.WARN
                    detail += " STALE"
            else:
                lvl = Level.WARN
                detail += " no readings yet"
        out.append(Check(f"infra.{it.kind}.{it.name}", lvl, detail))
    return out


def check_mesh(base) -> List[Check]:
    out = []
    mesh = getattr(base, "mesh", None)
    if mesh is None:
        out.append(Check("mesh", Level.UNKNOWN, "no mesh router in base"))
        return out
    s = mesh.stats()
    lvl = Level.OK
    detail = f"nodes={s['nodes']} delivered={s['delivered']} dropped={s['dropped']}"
    if s["dropped"] > 0 and s["delivered"] > 0:
        ratio = s["dropped"] / s["delivered"]
        if ratio > 0.1:
            lvl = Level.WARN
            detail += f" drop_ratio={ratio:.2f}"
    if s["missing"]:
        lvl = Level.WARN
        detail += f" MISSING={s['missing']}"
    out.append(Check("mesh", lvl, detail))
    return out


def check_comms(base) -> List[Check]:
    out = []
    c = base.comms
    q_depth = len(c.uplink.items)
    q_kb = c.uplink.pending_kb()
    lvl = Level.OK
    detail = f"queue={q_depth} ({q_kb:.1f} KB)"
    if q_kb > 2000:
        lvl = Level.WARN
        detail += " BACKLOG"
    if q_kb > 10000:
        lvl = Level.FAIL
    out.append(Check("comms.uplink", lvl, detail))

    # time since last successful pass
    if c.uplink.sent_history:
        last = c.uplink.sent_history[-1]
        h, m, s = c.clock.hms()
        out.append(Check("comms.last_pass",
                         Level.OK,
                         f"sol {c.clock.sol()} {h:02d}:{m:02d} sent "
                         f"{c.uplink.total_sent_kb:.1f} KB total"))
    else:
        out.append(Check("comms.last_pass", Level.UNKNOWN, "no passes yet"))

    d = c.earth.one_way_delay_s() / 60
    out.append(Check("comms.earth_link", Level.OK,
                     f"one-way {d:.1f} min"))
    return out


def check_supply(base) -> List[Check]:
    out = []
    rn = base.roads
    if not rn.roads:
        out.append(Check("supply", Level.UNKNOWN, "no roads yet"))
        return out
    total = sum(r.length() for r in rn.roads.values())
    out.append(Check("supply.roads", Level.OK,
                     f"{len(rn.roads)} roads, {total:.1f}m total"))

    # orphan check: any connected node with no road touching it
    touched = set()
    for r in rn.roads.values():
        for wp in r.waypoints:
            touched.add((round(wp[0], 2), round(wp[1], 2)))
    sl = getattr(base, "_supply", None)
    if sl:
        orphans = []
        for node in sl.connected:
            key = (round(node[0], 2), round(node[1], 2))
            if key not in touched and node != (0.0, 0.0):
                orphans.append(node)
        if orphans:
            out.append(Check("supply.orphans", Level.WARN,
                             f"{len(orphans)} orphan node(s)"))
        else:
            out.append(Check("supply.orphans", Level.OK, "none"))
    return out


def check_clock(base) -> List[Check]:
    out = []
    c = base.comms.clock
    out.append(Check("clock.sol", Level.OK, f"sol {c.sol()}"))
    h, m, s = c.hms()
    out.append(Check("clock.mst", Level.OK, f"{h:02d}:{m:02d}:{s:02d}"))
    return out


def check_world(base) -> List[Check]:
    out = []
    n = len(base.world.landmarks)
    out.append(Check("world.landmarks", Level.OK, f"{n} landmarks"))
    # sanity: any landmark with wild coordinates?
    wild = [lm.name for lm in base.world.landmarks.values()
            if abs(lm.x) > 1e6 or abs(lm.y) > 1e6]
    if wild:
        out.append(Check("world.sanity", Level.FAIL,
                         f"wild coords on: {wild[:3]}"))
    else:
        out.append(Check("world.sanity", Level.OK, "coordinates sane"))
    return out


# ============================================================
# top-level
# ============================================================

def run_all(rover, base, show_ok=True) -> Report:
    r = Report()
    for chk in (check_rover(rover, base) +
                check_modules(rover) +
                check_drones(base) +
                check_infra(base) +
                check_mesh(base) +
                check_comms(base) +
                check_supply(base) +
                check_clock(base) +
                check_world(base)):
        r.checks.append(chk)
    r.pretty(show_ok=show_ok)
    return r


def run_subsystem(rover, base, system: str) -> Report:
    system = system.lower()
    r = Report()
    fn_map = {
        "rover":    lambda: check_rover(rover, base),
        "modules":  lambda: check_modules(rover),
        "drones":   lambda: check_drones(base),
        "infra":    lambda: check_infra(base),
        "mesh":     lambda: check_mesh(base),
        "comms":    lambda: check_comms(base),
        "supply":   lambda: check_supply(base),
        "clock":    lambda: check_clock(base),
        "world":    lambda: check_world(base),
    }
    if system not in fn_map:
        print(f"unknown subsystem: {system}")
        print("available:", ", ".join(fn_map.keys()))
        return r
    r.checks = fn_map[system]()
    r.pretty()
    return r
