"""In-process message bus. Swap for LoRa later."""
import time
import queue
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Packet:
    src: str
    dst: str
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    t: float = field(default_factory=time.time)


class Bus:
    def __init__(self):
        self.q: "queue.Queue[Packet]" = queue.Queue()
        self.log: list = []

    def send(self, src, dst, kind, **payload):
        p = Packet(src=src, dst=dst, kind=kind, payload=payload)
        self.q.put(p)
        self.log.append(p)

    def poll(self, dst: Optional[str] = None):
        """Return list of pending packets (optionally filtered by dst)."""
        out = []
        while not self.q.empty():
            p = self.q.get()
            if dst is None or p.dst == dst or p.dst == "*":
                out.append(p)
        return out
