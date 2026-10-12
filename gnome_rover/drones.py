"""Sub-robots that live in GnomeROVER bays."""
import math, random
from .comms import Bus
from .world import World


class Drone:
    def __init__(self, name, bus, world, role="generic"):
        self.name = name; self.bus = bus; self.world = world
        self.role = role; self.status = "stowed"; self.battery = 100.0
        world.add_unit(name, role=role)

    def deploy(self, x, y):
        self.status = "deployed"
        self.world.move_unit(self.name, x, y)
        self.bus.send(self.name, "base", "deployed", x=x, y=y)
        print(f"[{self.name}] deployed at ({x}, {y})")

    def recall(self):
        self.status = "returning"
        print(f"[{self.name}] returning")

    def tick(self, dt, bx, by):
        if self.status == "stowed": return
        if self.status == "deployed":
            self.battery -= dt * 0.1
            if self.battery <= 0:
                self.status = "dead"
                print(f"[{self.name}] dead")

    def report(self):
        u = self.world.units[self.name]
        return {"name": self.name, "role": self.role,
                "x": round(u.x,2), "y": round(u.y,2),
                "battery": round(self.battery,1), "status": self.status}


class ScoutDrone(Drone):
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="scout")
        self.findings = []

    def tick(self, dt, bx, by):
        super().tick(dt, bx, by)
        if self.status == "deployed":
            u = self.world.units[self.name]
            u.x += random.uniform(-0.5, 0.5)
            u.y += random.uniform(-0.5, 0.5)
            if random.random() < 0.05:
                k = random.choice(["rock","crevice","flat","ice-signature"])
                self.findings.append((round(u.x,1), round(u.y,1), k))
                self.world.add_landmark(f"{k}-{len(self.findings)}", u.x, u.y, k)
                self.bus.send(self.name, "base", "finding", what=k,
                              x=round(u.x,1), y=round(u.y,1))

    def report(self):
        r = super().report(); r["findings"] = len(self.findings); return r


class RelayDrone(Drone):
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="relay")


class SamplerDrone(Drone):
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="sampler")
        self.samples = []

    def sample_at(self, x, y):
        self.status = "deployed"
        self.world.move_unit(self.name, x, y)
        self.samples.append((x,y))
        self.bus.send(self.name, "base", "sample", x=x, y=y)
        print(f"[{self.name}] sampled at ({x},{y})")
        self.status = "returning"

    def tick(self, dt, bx, by):
        super().tick(dt, bx, by)
        if self.status == "returning":
            u = self.world.units[self.name]
            dx, dy = bx-u.x, by-u.y
            d = math.hypot(dx,dy)
            if d < 0.5:
                self.status = "stowed"
                self.world.move_unit(self.name, bx, by)
                print(f"[{self.name}] docked")
            else:
                s = min(1.0, d)
                u.x += dx/d*s; u.y += dy/d*s


class ColonySeed(Drone):
    STAGES = ["seed","anchor","mast","shield","powered"]
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="colony")
        self.stage = 0
        self.chosen_site = None    # SiteScore, once placed

    def place_auto(self, selector, search_radius=15.0):
        """Pick the best-scoring site and deploy there."""
        site = selector.best_site(search_radius=search_radius)
        if site is None:
            print(f"[{self.name}] no viable site found")
            return False
        self.chosen_site = site
        self.deploy(site.x, site.y)
        self.world.add_landmark(f"colony-site", site.x, site.y, "colony")
        print(f"[{self.name}] site score={site.total}  ok={site.ok()}")
        for r in site.reasons:
            print(f"    - {r}")
        if not site.ok():
            print(f"[{self.name}] WARNING: chosen site below threshold, risks storm damage")
        return True

    def tick(self, dt, bx, by):
        super().tick(dt, bx, by)
        if self.status == "deployed":
            self.battery -= dt * 0.05
            self.stage = min(int(self.battery // 20), len(self.STAGES)-1)

    def report(self):
        r = super().report()
        r["stage"] = self.STAGES[self.stage]
        if self.chosen_site:
            r["site_score"] = self.chosen_site.total
        return r
