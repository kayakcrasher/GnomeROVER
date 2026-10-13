"""Orbiter relay passes + Deep Space Network uplink.

Physics:
  - One-way light-time Mars<->Earth: 3 to 22 minutes (varies with orbit)
  - Orbiter passes over a given longitude: roughly every 110 minutes,
    lasting 8 minutes (MRO, MAVEN, TGO combined coverage)
  - UHF link rover->orbiter: ~2 Mbps during pass
  - X-band orbiter->Earth: ~40 kbps nominal
  - Bandwidth budget per pass: ~120 MB

Simplified: sols advance in accelerated time (1 real second = N mars seconds)
so you can watch a full sol pass in the REPL.
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .soltime import SOL_SECONDS
from .bpv7 import Bundle, format_dtn


# --- time acceleration ---

TIME_SCALE = 60.0    # 1 real second = 60 Mars seconds (~4 min / real min)


class MarsClock:
    """Accelerated Mars clock. Ticks forward at TIME_SCALE x real time."""
    def __init__(self, landing_unix: float = None, scale: float = TIME_SCALE):
        self.start_unix = landing_unix if landing_unix is not None else time.time()
        self.mars_seconds = 0.0
        self.scale = scale
        self._last_wall = time.time()

    def tick(self):
        """Advance virtual Mars time based on real elapsed time."""
        now = time.time()
        dt_wall = now - self._last_wall
        self._last_wall = now
        self.mars_seconds += dt_wall * self.scale

    def sol(self) -> int:
        return int(self.mars_seconds // SOL_SECONDS)

    def sol_fraction(self) -> float:
        return (self.mars_seconds % SOL_SECONDS) / SOL_SECONDS

    def hms(self) -> tuple:
        secs = self.mars_seconds % SOL_SECONDS
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return (h, m, s)


# --- orbiters ---

@dataclass
class Orbiter:
    name: str
    period_s: float          # orbital period in Mars seconds
    pass_duration_s: float   # how long it's overhead
    phase_offset_s: float    # when its first pass began
    downlink_kbps: float = 40.0     # X-band to Earth

    def is_overhead(self, clock: MarsClock) -> bool:
        elapsed = clock.mars_seconds - self.phase_offset_s
        if elapsed < 0:
            return False
        cycle_pos = elapsed % self.period_s
        return cycle_pos < self.pass_duration_s

    def next_pass_in_s(self, clock: MarsClock) -> float:
        if self.is_overhead(clock):
            return 0.0
        elapsed = clock.mars_seconds - self.phase_offset_s
        if elapsed < 0:
            return -elapsed
        cycle_pos = elapsed % self.period_s
        return self.period_s - cycle_pos

    def next_pass_in_hms(self, clock: MarsClock) -> str:
        s = self.next_pass_in_s(clock)
        h = int(s // 3600); m = int((s % 3600) // 60); sec = int(s % 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"


# Standard orbital fleet (approximate real periods)
ORBITER_FLEET = [
    Orbiter("MRO",       period_s=6_600,  pass_duration_s=480, phase_offset_s=0),
    Orbiter("Odyssey",   period_s=7_200,  pass_duration_s=420, phase_offset_s=900),
    Orbiter("MAVEN",     period_s=13_200, pass_duration_s=360, phase_offset_s=1_800),
    Orbiter("TGO",       period_s=14_400, pass_duration_s=300, phase_offset_s=3_600),
]


# --- uplink queue ---

@dataclass
class UplinkItem:
    bundle: Bundle
    size_kb: float
    priority: int = 0    # higher first
    queued_at: float = 0.0
    sent_at: Optional[float] = None
    landed_at: Optional[float] = None


class UplinkQueue:
    """Queue of bundles waiting for an orbiter pass. Store-and-forward."""
    def __init__(self, bandwidth_kb_per_s: float = 250.0):
        self.items: List[UplinkItem] = []
        self.bandwidth = bandwidth_kb_per_s
        self.sent_history: List[UplinkItem] = []
        self.total_sent_kb = 0.0

    def enqueue(self, bundle: Bundle, size_kb: float, priority: int = 0):
        item = UplinkItem(bundle=bundle, size_kb=size_kb,
                          priority=priority, queued_at=time.time())
        self.items.append(item)
        # sort: highest priority first, then oldest
        self.items.sort(key=lambda i: (-i.priority, i.queued_at))

    def flush_during_pass(self, duration_s: float, clock: MarsClock):
        """During an orbiter pass, send as much as bandwidth allows."""
        budget_kb = self.bandwidth * duration_s
        sent = []
        for item in list(self.items):
            if budget_kb >= item.size_kb:
                item.sent_at = clock.mars_seconds
                self.items.remove(item)
                self.sent_history.append(item)
                self.total_sent_kb += item.size_kb
                budget_kb -= item.size_kb
                sent.append(item)
            else:
                break
        return sent

    def pending_kb(self) -> float:
        return sum(i.size_kb for i in self.items)

    def pretty(self):
        print(f"=== UPLINK QUEUE ({len(self.items)} items, {self.pending_kb():.1f} KB) ===")
        for i in self.items[:5]:
            p = i.bundle.payload()
            print(f"  prio={i.priority} {i.size_kb:>7.1f} KB  "
                  f"kind={p.get('kind')}  {i.bundle.primary.dst}")
        if len(self.items) > 5:
            print(f"  ... {len(self.items) - 5} more")


# --- Earth link with light-time ---

class EarthLink:
    """Simulates the one-way delay to Earth and DSN reception."""
    def __init__(self):
        # distance varies over Mars synodic period; fake it with sine
        self.base_delay_s = 600.0    # 10 min average one-way
        self.swings = 300.0          # +/- 5 min

    def one_way_delay_s(self) -> float:
        t = time.time() / 3600.0
        import math
        return self.base_delay_s + self.swings * math.sin(t * 0.01)

    def describe(self):
        d = self.one_way_delay_s()
        return f"one-way delay {d/60:.2f} min  (round-trip {2*d/60:.2f} min)"


# --- mission comms controller ---

class CommsController:
    """Owns the clock, orbiters, uplink queue, Earth link."""
    def __init__(self, scale: float = TIME_SCALE):
        self.clock = MarsClock(scale=scale)
        self.orbiters = list(ORBITER_FLEET)
        self.uplink = UplinkQueue()
        self.earth = EarthLink()
        self.last_pass_orbiter: Optional[str] = None
        self.pass_count = 0

    def tick(self):
        """Advance clock; check for active passes."""
        self.clock.tick()
        for orb in self.orbiters:
            if orb.is_overhead(self.clock):
                # flush the queue for the time we spent in this pass
                # (simplified: 1 real second = 60 Mars s, so budget)
                duration_mars_s = 1.0 * self.clock.scale
                sent = self.uplink.flush_during_pass(duration_mars_s, self.clock)
                if sent:
                    self.pass_count += 1
                    self.last_pass_orbiter = orb.name
                    # apply light-time delay to each
                    delay = self.earth.one_way_delay_s()
                    for item in sent:
                        item.landed_at = self.clock.mars_seconds + delay
                    print(f"[DSN] pass via {orb.name}: {len(sent)} bundle(s) sent, "
                          f"{sum(i.size_kb for i in sent):.1f} KB, "
                          f"arrive in {delay/60:.1f} min")

    def status(self):
        h, m, s = self.clock.hms()
        overhead = [o.name for o in self.orbiters if o.is_overhead(self.clock)]
        print(f"=== COMMS ===")
        print(f"  Sol {self.clock.sol():>4}  {h:02d}:{m:02d}:{s:02d} MST")
        print(f"  overhead: {overhead if overhead else 'none'}")
        for orb in self.orbiters:
            print(f"    {orb.name:<10} next pass in {orb.next_pass_in_hms(self.clock)}")
        print(f"  Earth link: {self.earth.describe()}")
        print(f"  uplink queue: {len(self.uplink.items)} items, "
              f"{self.uplink.pending_kb():.1f} KB")
        if self.uplink.sent_history:
            print(f"  total sent: {self.uplink.total_sent_kb:.1f} KB "
                  f"({len(self.uplink.sent_history)} bundles)")
