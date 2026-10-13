"""Sample collection, custody chain, and hauling."""
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
from .quiet import say


class SampleState(Enum):
    TARGETED   = "targeted"
    COLLECTED  = "collected"
    CACHED     = "cached"
    RETURNED   = "returned"
    ARCHIVED   = "archived"


@dataclass
class CustodyEvent:
    t: float
    sol: int
    mst: str
    state: str
    custodian: str
    x: float
    y: float
    lat: float
    lon: float
    note: str = ""


@dataclass
class Sample:
    id: str
    kind: str                # rock, ice, crevice
    mass_g: float
    source_landmark: str
    state: SampleState = SampleState.TARGETED
    custodian: str = "--"    # unit holding it, or depot name
    science_value: float = 0.0
    custody: List[CustodyEvent] = field(default_factory=list)
    collected_sol: Optional[int] = None

    def add_event(self, base, state, custodian, x, y, note=""):
        lat, lon, _ = base.world.to_areocentric(x, y)
        h, m, s = base.comms.clock.hms()
        self.custody.append(CustodyEvent(
            t=time.time(), sol=base.comms.clock.sol(),
            mst=f"{h:02d}:{m:02d}:{s:02d}",
            state=state, custodian=custodian,
            x=round(x, 2), y=round(y, 2),
            lat=round(lat, 5), lon=round(lon, 5), note=note,
        ))

    def line(self):
        return (f"  {self.id:<12} {self.kind:<8} {self.mass_g:>5.0f}g  "
                f"[{self.state.value:<9}] custodian={self.custodian:<10} "
                f"value={self.science_value:.2f}")

    def custody_trail(self):
        print(f"=== SAMPLE {self.id} ({self.kind}, {self.mass_g}g) ===")
        for e in self.custody:
            print(f"  Sol {e.sol:>3} {e.mst}  {e.state:<10} "
                  f"by {e.custodian:<10} "
                  f"@ ({e.x:>6.1f},{e.y:>6.1f}) "
                  f"-> {e.lat:.5f}°N {e.lon:.5f}°E  {e.note}")


class SampleArchive:
    """Global repository of all samples collected during the mission."""
    def __init__(self, base):
        self.base = base
        self.samples: Dict[str, Sample] = {}
        self._counter = 0

    def new_id(self, kind: str) -> str:
        self._counter += 1
        return f"{kind[:3].upper()}-{self._counter:03d}"

    def collect(self, kind: str, mass_g: float, landmark: str,
                x: float, y: float, sci_value: float,
                collector: str) -> Sample:
        sid = self.new_id(kind)
        s = Sample(id=sid, kind=kind, mass_g=mass_g,
                   source_landmark=landmark, science_value=sci_value,
                   state=SampleState.COLLECTED, custodian=collector)
        s.collected_sol = self.base.comms.clock.sol()
        s.add_event(self.base, "collected", collector, x, y,
                    note=f"from {landmark}")
        self.samples[sid] = s
        say(f"[SAMPLE] {sid} ({kind}, {mass_g:.0f}g) collected by {collector}")
        return s

    def transfer(self, sample_id: str, to_unit: str,
                 x: float, y: float, state: SampleState, note=""):
        s = self.samples.get(sample_id)
        if not s:
            return
        s.custodian = to_unit
        s.state = state
        s.add_event(self.base, state.value, to_unit, x, y, note=note)
        say(f"[SAMPLE] {sample_id} -> {to_unit} [{state.value}] {note}")

    def depot_inventory(self, depot_name: str) -> List[Sample]:
        return [s for s in self.samples.values()
                if s.custodian == depot_name
                and s.state == SampleState.CACHED]

    def summary(self):
        if not self.samples:
            print("[SAMPLES] none collected yet")
            return
        by_state = {}
        for s in self.samples.values():
            by_state[s.state.value] = by_state.get(s.state.value, 0) + 1
        print(f"=== SAMPLES ({len(self.samples)} total) ===")
        for k, v in sorted(by_state.items()):
            print(f"  {k:<12} {v}")
        for s in list(self.samples.values())[-8:]:
            print(s.line())

    def pretty(self):
        print(f"=== ALL SAMPLES ({len(self.samples)}) ===")
        for s in self.samples.values():
            print(s.line())


# --- drone extensions ---

def extend_sampler(sampler_drone, archive: SampleArchive,
                   capacity_g: float = 500.0):
    """Attach collection logic to a SamplerDrone instance."""
    sampler_drone.payload: List[str] = []      # sample IDs
    sampler_drone.capacity_g = capacity_g

    def payload_mass():
        return sum(archive.samples[sid].mass_g
                   for sid in sampler_drone.payload
                   if sid in archive.samples)

    sampler_drone.payload_mass = payload_mass
    sampler_drone.payload_capacity = capacity_g


def extend_hauler(hauler_drone, archive: SampleArchive,
                  capacity_g: float = 2000.0):
    """Attach hauling logic to a generic Drone used as a courier."""
    hauler_drone.payload: List[str] = []
    hauler_drone.capacity_g = capacity_g
    hauler_drone.haul_target = None   # depot name it's heading to


def try_collect(archive: SampleArchive, sampler, landmark_name: str,
                science_value: float, base):
    """Sampler attempts to collect a sample at its current location."""
    # decide kind from landmark
    lm = base.world.landmarks.get(landmark_name)
    if not lm:
        return None
    u = base.world.units.get(sampler.name)
    # fake mass: 100-400g depending on kind
    import random
    mass = {"rock": 300, "ice-signature": 150, "crevice": 250}.get(lm.kind, 200)
    mass += random.uniform(-50, 50)

    # check payload
    current = sampler.payload_mass()
    if current + mass > sampler.payload_capacity:
        say(f"[{sampler.name}] payload full ({current:.0f}g/"
            f"{sampler.payload_capacity:.0f}g), cannot collect")
        return None

    s = archive.collect(lm.kind, mass, landmark_name,
                        u.x, u.y, science_value, collector=sampler.name)
    sampler.payload.append(s.id)
    return s
