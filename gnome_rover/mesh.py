"""Mesh networking: packets, nodes, routing, heartbeats."""
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from .quiet import say
from .bpv7 import make_bundle


class Priority(Enum):
    ROUTINE = 0
    URGENT = 1
    EMERGENCY = 2


class PacketKind(Enum):
    HEARTBEAT = "heartbeat"
    TELEMETRY = "telemetry"
    FINDING = "finding"
    COMMAND = "command"
    ACK = "ack"
    ALERT = "alert"
    PING = "ping"


@dataclass
class Packet:
    src: str
    dst: str                   # unit name or "broadcast" or "base"
    kind: str
    seq: int = 0
    t: float = field(default_factory=time.time)
    priority: str = "routine"
    hops: int = 0
    path: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "src": self.src, "dst": self.dst, "kind": self.kind,
            "seq": self.seq, "t": round(self.t, 1),
            "prio": self.priority, "hops": self.hops,
            "path": list(self.path), "payload": dict(self.payload),
        }

    def short(self) -> str:
        return (f"{self.src}->{self.dst} [{self.kind}] "
                f"seq={self.seq} hops={self.hops}")

    def as_bundle(self, lifetime_s: int = 3600):
        """Wrap this packet as a BPv7 bundle for interplanetary relay."""
        return make_bundle(
            src_node=self.src, dst_node=self.dst, kind=self.kind,
            lifetime_s=lifetime_s, priority=self.priority,
            **self.payload,
        )


class MeshNode:
    """A radio-equipped unit in the mesh."""
    def __init__(self, name: str, range_m: float = 30.0):
        self.name = name
        self.range_m = range_m
        self.x = 0.0
        self.y = 0.0
        self.seq = 0          # outgoing sequence
        self.last_rx = 0      # seq we last heard from each neighbor (future)
        self.inbox: List[Packet] = []
        self.last_heartbeat_t = 0.0

    def move(self, x: float, y: float):
        self.x, self.y = x, y

    def in_range(self, other: "MeshNode") -> bool:
        d = math.hypot(self.x - other.x, self.y - other.y)
        return d <= min(self.range_m, other.range_m)

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def make_packet(self, dst: str, kind: str, priority: str = "routine",
                    **payload) -> Packet:
        return Packet(src=self.name, dst=dst, kind=kind,
                      seq=self.next_seq(), priority=priority,
                      path=[self.name], payload=payload)


class MeshRouter:
    """Owns nodes, routes packets, tracks heartbeats."""
    def __init__(self):
        self.nodes: Dict[str, MeshNode] = {}
        self.delivered: List[Packet] = []
        self.dropped: int = 0
        self.last_heard: Dict[str, float] = {}
        self.missing_threshold_s = 15.0

    def add_node(self, node: MeshNode):
        self.nodes[node.name] = node
        self.last_heard[node.name] = time.time()

    def remove_node(self, name: str):
        self.nodes.pop(name, None)
        self.last_heard.pop(name, None)

    # --- neighbor discovery ---

    def neighbors(self, name: str) -> List[str]:
        n = self.nodes.get(name)
        if not n: return []
        return [o.name for o in self.nodes.values()
                if o.name != name and n.in_range(o)]

    def _graph(self) -> Dict[str, List[str]]:
        g = {n: [] for n in self.nodes}
        for name in self.nodes:
            g[name] = self.neighbors(name)
        return g

    def route(self, src: str, dst: str) -> Optional[List[str]]:
        """BFS shortest path. Returns [src, ..., dst] or None if unreachable."""
        if src == dst:
            return [src]
        g = self._graph()
        if src not in g or dst not in g:
            return None
        from collections import deque
        prev = {src: None}
        q = deque([src])
        while q:
            cur = q.popleft()
            if cur == dst:
                path = []
                while cur:
                    path.append(cur)
                    cur = prev[cur]
                return list(reversed(path))
            for nxt in g[cur]:
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        return None

    # --- delivery ---

    def send(self, packet: Packet) -> bool:
        """Route a packet from src to dst. Returns True if delivered."""
        path = self.route(packet.src, packet.dst) if packet.dst != "broadcast" else None

        if packet.dst == "broadcast":
            # every node hears it if reachable in <=3 hops
            packet.path = [packet.src]
            packet.hops = 0
            self.delivered.append(packet)
            for name in self.nodes:
                if name != packet.src:
                    p = self.route(packet.src, name)
                    if p and len(p) <= 4:
                        self.last_heard[name] = time.time()
            return True

        if path is None:
            self.dropped += 1
            if packet.priority == "emergency":
                say(f"[MESH] EMERGENCY packet DROPPED {packet.short()}")
            return False

        packet.path = path
        packet.hops = len(path) - 1
        self.delivered.append(packet)
        self.last_heard[packet.dst] = time.time()

        if packet.priority == "emergency":
            say(f"[MESH] EMERGENCY {packet.short()} path={path}")
        elif packet.kind == "alert":
            say(f"[MESH] {packet.short()} path={path}")

        return True

    def heartbeat(self, name: str, **status):
        n = self.nodes.get(name)
        if not n: return
        pkt = n.make_packet("base", "heartbeat", **status)
        self.send(pkt)

    def check_missing(self) -> List[str]:
        """Return names of nodes whose last heartbeat is stale."""
        now = time.time()
        missing = []
        for name, t in self.last_heard.items():
            if name == "base":  # base is the receiver, ignore
                continue
            if now - t > self.missing_threshold_s:
                missing.append(name)
        return missing

    def stats(self):
        return {
            "nodes": len(self.nodes),
            "delivered": len(self.delivered),
            "dropped": self.dropped,
            "missing": self.check_missing(),
        }

    def pretty(self):
        print(f"=== MESH ({len(self.nodes)} nodes) ===")
        for name, n in self.nodes.items():
            nbrs = self.neighbors(name)
            age = time.time() - self.last_heard.get(name, time.time())
            print(f"  {name:<14} range={n.range_m:>5.1f}m  "
                  f"neighbors={len(nbrs):>2}  last_heard={age:>5.1f}s ago")
        print(f"  delivered={len(self.delivered)}  dropped={self.dropped}")
