"""Mission save/load: everything to JSON, everything back."""
import json
import time
from pathlib import Path
from typing import Dict, Any


SAVE_VERSION = 1
DEFAULT_PATH = Path.home() / "GnomeROVER" / "mission_save.json"


def _serialize_landmark(lm):
    return {"name": lm.name, "x": lm.x, "y": lm.y, "kind": lm.kind}


def _serialize_unit(u):
    return {"name": u.name, "x": u.x, "y": u.y, "heading": u.heading,
            "battery": u.battery, "status": u.status, "role": u.role}


def _serialize_road(road):
    return {"name": road.name, "waypoints": [list(w) for w in road.waypoints]}


def _serialize_drone(d):
    return {
        "name": d.name,
        "role": d.role,
        "status": d.status,
        "battery": d.battery,
        "mode": d.mode.value if hasattr(d.mode, "value") else str(d.mode),
        "route": [list(p) for p in getattr(d, "route", [])],
        "route_idx": getattr(d, "route_idx", 0),
        "extra": {
            k: v for k, v in d.__dict__.items()
            if k in ("findings", "samples", "stage", "chosen_site")
            and not k.startswith("_")
        },
    }


def _serialize_infra(it):
    base = {"name": it.name, "kind": it.kind, "x": it.x, "y": it.y,
            "battery": it.battery, "status": it.status}
    if it.kind == "weather" and hasattr(it, "readings"):
        base["readings"] = it.readings[-50:]   # trim to last 50
    if it.kind == "repeater":
        base["range_m"] = getattr(it, "range_m", 30.0)
    if it.kind == "home":
        base["charger_capacity_kwh"] = getattr(it, "charger_capacity_kwh", 50.0)
    if it.kind == "depot":
        base["contents"] = dict(getattr(it, "contents", {}))
        base["depot_kind"] = getattr(it, "depot_kind", "generic")
    return base


def save(base, path: Path = DEFAULT_PATH):
    """Serialize the entire base station to JSON."""
    data = {
        "version": SAVE_VERSION,
        "saved_at": time.time(),
        "clock": {
            "mars_seconds": base.comms.clock.mars_seconds,
            "scale": base.comms.clock.scale,
            "start_unix": base.comms.clock.start_unix,
        },
        "world": {
            "frame": {
                "lat0": base.world.frame.lat0,
                "lon0": base.world.frame.lon0,
                "name": base.world.frame.name,
            },
            "landmarks": [_serialize_landmark(lm)
                          for lm in base.world.landmarks.values()],
            "units": [_serialize_unit(u)
                      for u in base.world.units.values()],
        },
        "roads": [_serialize_road(r) for r in base.roads.roads.values()],
        "drones": {name: _serialize_drone(d)
                   for name, d in base.drones.items()},
        "infra": [_serialize_infra(it) for it in base.infra.items.values()],
        "comms": {
            "total_sent_kb": base.comms.uplink.total_sent_kb,
            "sent_count": len(base.comms.uplink.sent_history),
        },
        "log": base.mission_log[-100:],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    print(f"[PERSIST] saved to {path} ({path.stat().st_size} bytes)")
    return path


def load(base, path: Path = DEFAULT_PATH):
    """Restore base station state from a save file."""
    if not path.exists():
        print(f"[PERSIST] no save at {path}")
        return False
    data = json.loads(path.read_text())
    if data.get("version") != SAVE_VERSION:
        print(f"[PERSIST] version mismatch "
              f"(file={data.get('version')} code={SAVE_VERSION})")
        return False

    # --- clock ---
    ck = data["clock"]
    base.comms.clock.mars_seconds = ck["mars_seconds"]
    base.comms.clock.scale = ck["scale"]
    base.comms.clock.start_unix = ck["start_unix"]

    # --- world ---
    base.world.landmarks.clear()
    base.world.units.clear()
    for lm in data["world"]["landmarks"]:
        base.world.add_landmark(lm["name"], lm["x"], lm["y"], lm["kind"])
    for u in data["world"]["units"]:
        base.world.add_unit(u["name"], role=u["role"])
        base.world.move_unit(u["name"], u["x"], u["y"], u.get("heading"))
        wu = base.world.units[u["name"]]
        wu.battery = u["battery"]
        wu.status = u["status"]

    # --- roads ---
    from .roads import Road
    base.roads.roads.clear()
    for rd in data["roads"]:
        road = Road(name=rd["name"])
        road.waypoints = [tuple(w) for w in rd["waypoints"]]
        base.roads.roads[rd["name"]] = road

    # --- drones ---
    from .power import PowerMode
    for name, dd in data["drones"].items():
        d = base.drones.get(name)
        if not d:
            continue
        d.status = dd["status"]
        d.battery = dd["battery"]
        try:
            d.mode = PowerMode(dd["mode"])
        except Exception:
            pass
        d.route = [tuple(p) for p in dd.get("route", [])]
        d.route_idx = dd.get("route_idx", 0)
        for k, v in dd.get("extra", {}).items():
            setattr(d, k, v)

    # --- infra ---
    from .infra import (HomeBase, WeatherStation,
                        RadioRepeater, Depot)
    base.infra.items.clear()
    for it in data["infra"]:
        cls = {"home": HomeBase, "weather": WeatherStation,
               "repeater": RadioRepeater, "depot": Depot}.get(it["kind"])
        if not cls:
            continue
        obj = cls(it["name"], it["x"], it["y"])
        obj.battery = it["battery"]
        obj.status = it["status"]
        if it["kind"] == "weather":
            obj.readings = it.get("readings", [])
        if it["kind"] == "repeater":
            obj.range_m = it.get("range_m", 30.0)
        if it["kind"] == "depot":
            obj.contents = dict(it.get("contents", {}))
            obj.depot_kind = it.get("depot_kind", "generic")
        base.infra.items[it["name"]] = obj

    # --- comms totals ---
    base.comms.uplink.total_sent_kb = data["comms"]["total_sent_kb"]

    # --- log ---
    base.mission_log = data.get("log", [])

    print(f"[PERSIST] loaded from {path}")
    print(f"  sol={base.comms.clock.sol()} "
          f"landmarks={len(base.world.landmarks)} "
          f"roads={len(base.roads.roads)} "
          f"infra={len(base.infra.items)}")
    return True
