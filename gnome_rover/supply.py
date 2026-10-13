"""Autonomous supply-line builder.

Greedy algorithm: for each resource find, plan a road from the nearest
already-connected node. HomeBase is the root. Result is a tree.
"""
import math
from typing import List, Tuple, Dict, Optional
from .roads import RoadNetwork
from .world import World


# Which landmark kinds are worth connecting with roads
RESOURCE_KINDS = ("rock", "flat", "ice-signature", "colony", "depot", "weather", "repeater")


class SupplyLine:
    def __init__(self, world: World, roads: RoadNetwork, home_xy=(0.0, 0.0)):
        self.world = world
        self.roads = roads
        self.home = home_xy
        self.connected: List[Tuple[float, float]] = [home_xy]
        self.graph: Dict[str, List[str]] = {"home": []}   # adjacency by road name

    def _nearest_connected(self, x, y) -> Tuple[float, float]:
        return min(self.connected,
                   key=lambda p: math.hypot(p[0]-x, p[1]-y))

    def _dist(self, a, b):
        return self.world.surface_distance(a[0], a[1], b[0], b[1])

    def _road_name(self, landmark_name: str) -> str:
        # sanitize
        return "road-" + landmark_name.replace(" ", "_")

    def _road_exists(self, landmark_name: str) -> bool:
        return self._road_name(landmark_name) in self.roads.roads

    def build_for(self, landmark_name: str) -> bool:
        """Build one road from the nearest connected node to a landmark."""
        lm = self.world.landmarks.get(landmark_name)
        if not lm:
            print(f"[SUPPLY] no landmark '{landmark_name}'")
            return False
        if self._road_exists(landmark_name):
            print(f"[SUPPLY] road to '{landmark_name}' already exists")
            return False

        target = (lm.x, lm.y)
        anchor = self._nearest_connected(lm.x, lm.y)
        dist = self._dist(anchor, target)
        if dist < 3.0:
            # too close to justify a road; just mark connected
            self.connected.append(target)
            return False

        name = self._road_name(landmark_name)
        self.roads.new(name)
        self.roads.add(name, anchor[0], anchor[1])
        self.roads.add(name, target[0], target[1])

        self.connected.append(target)
        self.graph.setdefault(landmark_name, [])
        self.graph["home"].append(name)

        # report with real Mars coordinates
        lat, lon, _ = self.world.to_areocentric(target[0], target[1])
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        print(f"[SUPPLY] built {name}: {dist:.1f}m  ->  "
              f"{abs(lat):.5f}°{ns} {abs(lon):.5f}°{ew}")
        return True

    def build_all(self, kinds=RESOURCE_KINDS) -> int:
        """Build roads to every landmark of the given kinds. Returns count."""
        built = 0
        for name, lm in list(self.world.landmarks.items()):
            if lm.kind not in kinds:
                continue
            if name == "base" or name == "HomeBase":
                continue
            if self._road_exists(name):
                continue
            if self.build_for(name):
                built += 1
        return built

    def total_length(self) -> float:
        return sum(r.length() for r in self.roads.roads.values())

    def report(self):
        print("=== SUPPLY LINE ===")
        print(f"  connected nodes: {len(self.connected)}")
        print(f"  roads: {len(self.roads.roads)}")
        print(f"  total length: {self.total_length():.1f}m")
        print(f"  home areocentric: ", end="")
        lat, lon, _ = self.world.to_areocentric(*self.home)
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        print(f"{abs(lat):.5f}°{ns} {abs(lon):.5f}°{ew}")
        for name, road in self.roads.roads.items():
            if len(road.waypoints) >= 2:
                end = road.waypoints[-1]
                lat, lon, _ = self.world.to_areocentric(*end)
                ns = "N" if lat >= 0 else "S"
                ew = "E" if lon >= 0 else "W"
                print(f"  {name:<24} {road.length():>7.1f}m  ends at "
                      f"{abs(lat):.5f}°{ns} {abs(lon):.5f}°{ew}")


def trace_line(world: World, roads: RoadNetwork, x: float, y: float):
    """Return the full coordinate chain from home to (x, y) along roads."""
    path, cost = roads.route((0.0, 0.0), (x, y))
    if not path:
        print(f"[TRACE] no route to ({x},{y})")
        return None, None
    print(f"[TRACE] home -> ({x},{y}): {len(path)} waypoints, cost={cost:.1f}m")
    coords = []
    for i, (px, py) in enumerate(path):
        lat, lon, _ = world.to_areocentric(px, py)
        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        print(f"  {i}: local ({px:>7.1f}, {py:>7.1f})  ->  "
              f"{abs(lat):.5f}°{ns} {abs(lon):.5f}°{ew}")
        coords.append((px, py, lat, lon))
    return path, coords
