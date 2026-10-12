"""Roads and routing over the world map."""
import heapq
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


@dataclass
class Road:
    name: str
    waypoints: List[Tuple[float, float]] = field(default_factory=list)

    def length(self) -> float:
        return sum(
            math.hypot(self.waypoints[i+1][0] - self.waypoints[i][0],
                       self.waypoints[i+1][1] - self.waypoints[i][1])
            for i in range(len(self.waypoints) - 1)
        )


class RoadNetwork:
    def __init__(self):
        self.roads: Dict[str, Road] = {}

    # --- define ---
    def new(self, name: str):
        if name in self.roads:
            print(f"[ROAD] '{name}' exists")
            return
        self.roads[name] = Road(name)
        print(f"[ROAD] created '{name}'")

    def add(self, name: str, x: float, y: float):
        if name not in self.roads:
            self.new(name)
        self.roads[name].waypoints.append((x, y))
        print(f"[ROAD] '{name}' += ({x:.1f}, {y:.1f})  ({len(self.roads[name].waypoints)} pts)")

    def show(self, name: str):
        r = self.roads.get(name)
        if not r:
            print(f"[ROAD] no such road: {name}")
            return
        print(f"Road '{name}' ({len(r.waypoints)} waypoints, {r.length():.1f}m):")
        for i, (x, y) in enumerate(r.waypoints):
            print(f"  [{i}] ({x:>7.1f}, {y:>7.1f})")

    def list_all(self):
        if not self.roads:
            print("[ROAD] no roads defined")
            return
        print(f"{len(self.roads)} road(s):")
        for r in self.roads.values():
            print(f"  {r.name:<12} {len(r.waypoints)} pts, {r.length():>7.2f}m")

    # --- routing ---
    def _nodes(self, extra_points=()) -> List[Tuple[float, float]]:
        nodes = []
        for r in self.roads.values():
            nodes.extend(r.waypoints)
        nodes.extend(extra_points)
        # dedup near-identical
        out = []
        for n in nodes:
            if not any(math.hypot(n[0]-o[0], n[1]-o[1]) < 1e-6 for o in out):
                out.append(n)
        return out

    def _build_graph(self, extra_points=(), snap_radius=3.0):
        """nodes = tuples, edges = {node_index: [(neighbor_idx, weight), ...]}"""
        nodes = self._nodes(extra_points)
        idx_of = {n: i for i, n in enumerate(nodes)}
        edges = {i: [] for i in range(len(nodes))}

        # road edges between consecutive waypoints
        for r in self.roads.values():
            for i in range(len(r.waypoints) - 1):
                a = idx_of[r.waypoints[i]]
                b = idx_of[r.waypoints[i+1]]
                w = math.hypot(r.waypoints[i+1][0]-r.waypoints[i][0],
                               r.waypoints[i+1][1]-r.waypoints[i][1])
                edges[a].append((b, w))
                edges[b].append((a, w))

        # junction edges: any two nodes within snap_radius get a road-cost link
        for i, a in enumerate(nodes):
            for j, b in enumerate(nodes):
                if j <= i: continue
                d = math.hypot(b[0]-a[0], b[1]-a[1])
                if d <= snap_radius:
                    edges[i].append((j, d))
                    edges[j].append((i, d))

        # extra points (start/end): connect to nearest few road nodes with penalty
        extra_idx = [idx_of[p] for p in extra_points if p in idx_of]
        for ei in extra_idx:
            a = nodes[ei]
            candidates = sorted(
                ((j, math.hypot(b[0]-a[0], b[1]-a[1])) for j, b in enumerate(nodes) if j != ei),
                key=lambda t: t[1]
            )[:3]
            for j, d in candidates:
                w = d * 1.5   # off-road penalty
                edges[ei].append((j, w))
                edges[j].append((ei, w))

        return nodes, edges

    def route(self, start_xy, goal_xy, snap_radius=3.0):
        """Dijkstra. Returns (path_points, total_cost) or (None, None)."""
        nodes, edges = self._build_graph(extra_points=[start_xy, goal_xy],
                                         snap_radius=snap_radius)
        idx_of = {n: i for i, n in enumerate(nodes)}
        s = idx_of.get(start_xy)
        g = idx_of.get(goal_xy)
        if s is None or g is None:
            return None, None

        dist = {i: math.inf for i in range(len(nodes))}
        prev = {}
        dist[s] = 0.0
        pq = [(0.0, s)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == g: break
            if d > dist[u]: continue
            for v, w in edges[u]:
                nd = d + w
                if nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))

        if dist[g] == math.inf:
            return None, None

        path = []
        cur = g
        while cur != s:
            path.append(nodes[cur])
            cur = prev.get(cur)
            if cur is None:
                return None, None
        path.append(nodes[s])
        path.reverse()

        # simplify: drop near-collinear points
        simplified = [path[0]]
        for p in path[1:-1]:
            a, b = simplified[-1], p
            if math.hypot(b[0]-a[0], b[1]-a[1]) > 0.4:
                simplified.append(p)
        simplified.append(path[-1])
        return simplified, dist[g]

    def pretty_route(self, path, cost):
        if not path:
            print("[ROUTE] no path")
            return
        print(f"[ROUTE] {len(path)} waypoints, cost={cost:.2f}m")
        for i, (x, y) in enumerate(path):
            print(f"  {i}: ({x:>7.1f}, {y:>7.1f})")
