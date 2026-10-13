"""Bundle Protocol v7 primitives (RFC 9171 / CCSDS 734.2-B-3).

Simplified representation:
  PrimaryBlock  — src, dst, creation time, lifetime, CRC
  CanonicalBlock — extension blocks (payload, metadata, custody)

Real BPv7 has CBOR encoding, CRC-32C, and 64-bit DTN timestamps
(since 2000-01-01 00:00:00 UTC). This models the semantics, not the bytes.
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# --- DTN time epoch: 2000-01-01 00:00:00 UTC ---
DTN_EPOCH_UNIX = 946_684_800.0


def dtn_timestamp(unix: float = None):
    """Return (seconds, nanoseconds) since DTN epoch."""
    if unix is None:
        unix = time.time()
    delta = unix - DTN_EPOCH_UNIX
    secs = int(delta)
    nanos = int((delta - secs) * 1e9)
    return (secs, nanos)


def format_dtn(dtn_secs: int) -> str:
    """Human-readable DTN time."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(dtn_secs + DTN_EPOCH_UNIX))


@dataclass
class PrimaryBlock:
    """BPv7 primary block: who, where, when, how long."""
    src: str                    # e.g. "dtn://mars.jezero/rover"
    dst: str                    # e.g. "dtn://earth.dsn/base"
    dtn_time: tuple             # (seconds, nanos) since 2000-01-01
    lifetime_s: int             # how long this bundle is valid
    priority: str = "routine"   # routine | urgent | emergency
    crc: Optional[int] = None

    def expired(self, now_unix: float = None) -> bool:
        if now_unix is None:
            now_unix = time.time()
        dtn_now = dtn_timestamp(now_unix)
        age = (dtn_now[0] + dtn_now[1]/1e9) - (self.dtn_time[0] + self.dtn_time[1]/1e9)
        return age > self.lifetime_s

    def describe(self):
        return (f"<PrimaryBlock {self.src} -> {self.dst}  "
                f"created={format_dtn(self.dtn_time[0])} "
                f"lifetime={self.lifetime_s}s prio={self.priority}>")


@dataclass
class CanonicalBlock:
    """Payload or metadata block."""
    block_type: str             # "payload" | "metadata" | "custody"
    data: Dict[str, Any] = field(default_factory=dict)
    crc: Optional[int] = None


@dataclass
class Bundle:
    """A complete BPv7 bundle."""
    primary: PrimaryBlock
    blocks: List[CanonicalBlock] = field(default_factory=list)

    def payload(self) -> Optional[Dict[str, Any]]:
        for b in self.blocks:
            if b.block_type == "payload":
                return b.data
        return None

    def describe(self):
        lines = [self.primary.describe()]
        for b in self.blocks:
            lines.append(f"  <{b.block_type} {b.data}>")
        return "\n".join(lines)


# --- endpoint ID scheme (per BPv7) ---

def eid(node: str, service: str = "rover", domain: str = "mars.jezero") -> str:
    """Build a DTN endpoint ID. e.g. dtn://mars.jezero/rover"""
    return f"dtn://{domain}/{node}"


# --- factory ---

def make_bundle(src_node: str, dst_node: str, kind: str,
                lifetime_s: int = 3600, priority: str = "routine",
                **payload) -> Bundle:
    """Construct a BPv7 bundle with primary + payload blocks."""
    pb = PrimaryBlock(
        src=eid(src_node, "rover"),
        dst=eid(dst_node, "base", domain="earth.dsn"),
        dtn_time=dtn_timestamp(),
        lifetime_s=lifetime_s,
        priority=priority,
    )
    blocks = [
        CanonicalBlock("payload", {"kind": kind, **payload}),
    ]
    return Bundle(primary=pb, blocks=blocks)


def demo():
    print("=== BPv7 bundle demo ===")
    b = make_bundle(
        src_node="Scout-1", dst_node="dsn",
        kind="finding", lifetime_s=86_400, priority="routine",
        what="rock", lat=18.44479, lon=77.45088,
    )
    print(b.describe())
    print()
    print("DTN timestamp (s, ns):", dtn_timestamp())
    print("formatted:", format_dtn(dtn_timestamp()[0]))
    print("expired?", b.primary.expired())
