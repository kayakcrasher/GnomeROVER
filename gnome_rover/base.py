"""Base station: ties rover + drones + world + bus together."""
from .comms import Bus
from .world import World
from .drones import ScoutDrone, RelayDrone, SamplerDrone, ColonySeed
from .roads import RoadNetwork
from .infra import InfraManager, HomeBase, WeatherStation, RadioRepeater, Depot
from .dsn import CommsController
from .faults import FaultInjector
from .solops import SolOps


class BaseStation:
    def __init__(self, rover):
        self.rover = rover
        self.bus = Bus()
        self.world = World()
        self.roads = RoadNetwork(world=self.world)
        self.infra = InfraManager()
        self.comms = CommsController()
        self.uplink_log = []
        self.faults = FaultInjector(self)
        self.solops = SolOps(self)
        self._comms_jammed = False
        self.faults = FaultInjector(self)
        self._comms_jammed = False
        self.world.add_unit("rover", role="base")
        self.drones = {}
        self.uplink_queue = []
        self.mission_log = []
        self._add(ScoutDrone("Scout-1", self.bus, self.world))
        self._add(RelayDrone("Relay-1", self.bus, self.world))
        self._add(SamplerDrone("Sampler-1", self.bus, self.world))
        self._add(ColonySeed("Colony-1", self.bus, self.world))
        self.world.add_landmark("base", 0.0, 0.0, "home")
        self.log("mission start; base established at origin")

    def _add(self, d): self.drones[d.name] = d

    def log(self, msg):
        print(f"[BASE] {msg}")
        self.mission_log.append(f"[BASE] {msg}")

    def _find(self, key):
        if key in self.drones: return self.drones[key]
        for d in self.drones.values():
            if d.role == key: return d
        return None

    def deploy(self, key, x, y):
        d = self._find(key)
        if not d: print(f"[BASE] no drone: {key}"); return
        d.deploy(x, y)
        self.log(f"deployed {d.name} to ({x},{y})")

    def recall(self, key):
        d = self._find(key)
        if d: d.recall(); self.log(f"recalled {d.name}")

    def tick(self, dt):
        rx, ry = self.world.units["rover"].x, self.world.units["rover"].y
        for d in self.drones.values():
            d.tick(dt, rx, ry)
        self.infra.tick(dt)
        self.faults.tick()
        self.solops.check_milestones()
        self.solops.tick()
        if not self._comms_jammed:
            self.comms.tick()
        for p in self.bus.poll("base"):
            self.mission_log.append(f"  << {p.src} -> {p.kind} {p.payload}")

    def status_report(self):
        print("=== MISSION STATUS ===")
        self.world.pretty()
        print("=== DRONES ===")
        for d in self.drones.values():
            print(f"  {d.report()}")
        print("=== INFRA ===")
        self.infra.pretty()
        print()
        self.comms.status()

    def ping(self):
        print("[PING] radio check:")
        for d in self.drones.values():
            dist = self.world.distance("rover", d.name) or 0
            link = "OK" if dist < 50 else "WEAK"
            print(f"  {d.name:<12} dist={dist:>6.2f}  status={d.status}  {link}")

    def uplink(self, msg):
        self.uplink_queue.append(msg)
        print(f"[UPLINK queued] {msg}")

    def log_dump(self):
        print("=== MISSION LOG ===")
        for line in self.mission_log[-30:]: print(line)
