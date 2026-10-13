"""Sub-robots that live in GnomeROVER bays."""
import math, random
from .comms import Bus
from .world import World
from .quiet import say
from .power import (
    PowerMode, next_mode, drain_for, can_move, describe,
    LOW_THRESHOLD, CRITICAL_THRESHOLD, CHARGE_EXIT,
)


class Drone:
    def __init__(self, name, bus, world, role="generic"):
        self.name = name; self.bus = bus; self.world = world
        self.role = role
        self.status = "stowed"
        self.battery = 100.0
        self.mode = PowerMode.NORMAL
        self.route = []          # list of (x, y) waypoints
        self.route_idx = 0       # next waypoint to head toward
        world.add_unit(name, role=role)

    def deploy(self, x, y):
        self.status = "deployed"
        self.world.move_unit(self.name, x, y)
        self.world.units[self.name].status = "deployed"
        self.bus.send(self.name, "base", "deployed", x=x, y=y)
        say(f"[{self.name}] deployed at ({x}, {y}) {describe(self.mode)}")

    def recall(self):
        self.status = "returning"
        self.world.units[self.name].status = "returning"
        say(f"[{self.name}] returning")

    def go_to(self, x, y, roads=None):
        """Plan a route (via roads if given) and start walking it."""
        u = self.world.units[self.name]
        if roads is not None:
            path, cost = roads.route((u.x, u.y), (x, y))
        else:
            path, cost = [(u.x, u.y), (x, y)], math.hypot(x - u.x, y - u.y)
        if not path:
            say(f"[{self.name}] no route to ({x}, {y})")
            return False
        self.route = path
        self.route_idx = 1      # first waypoint is current position
        self.status = "deployed"
        u.status = "deployed"
        say(f"[{self.name}] route planned: {len(path)} waypoints, cost={cost:.2f}m")
        return True

    def _walk_route(self, dt):
        """Advance one step along self.route, return True when complete."""
        if not self.route or self.route_idx >= len(self.route):
            return True
        u = self.world.units[self.name]
        tx, ty = self.route[self.route_idx]
        dx, dy = tx - u.x, ty - u.y
        d = math.hypot(dx, dy)
        if d < 0.3:
            self.route_idx += 1
            if self.route_idx >= len(self.route):
                say(f"[{self.name}] arrived at ({u.x:.2f}, {u.y:.2f})")
                self.route = []
                return True
            return False
        # speed gated by power mode
        speed = 0.5 if self.mode == PowerMode.NORMAL else 0.15
        step = min(speed, d)
        u.x += dx / d * step
        u.y += dy / d * step
        return False

    def _update_power(self, dt, bx, by):
        """Run the power state machine one step."""
        u = self.world.units[self.name]

        # if HALTED and not at base, request a dock (crawl back)
        if self.mode == PowerMode.HALTED and self.status == "deployed":
            self.status = "returning"

        # docked once we're basically on top of base
        dist_to_base = math.hypot(u.x - bx, u.y - by)
        at_base = dist_to_base < 0.6

        docked = at_base and self.status in ("stowed", "returning")

        new_mode = next_mode(self.mode, self.battery, docked)

        # if at base and battery below exit threshold, force CHARGING
        if at_base and self.status != "deployed" and self.battery < CHARGE_EXIT:
            new_mode = PowerMode.CHARGING

        if new_mode != self.mode:
            say(f"[{self.name}] {describe(self.mode)} -> {describe(new_mode)} "
                f"(bat={self.battery:.1f}%)")
            self.mode = new_mode

        # apply drain/charge
        delta = drain_for(self.mode) * dt * 10   # dt is in tick seconds; scale by 10 to match original
        self.battery = max(0.0, min(100.0, self.battery - delta))

        # if we've hit HALTED and are back at base, dock+charge
        if at_base and self.status == "returning":
            self.status = "stowed"
            u.status = "stowed"

        u.battery = self.battery
        u.status = self.status

    def tick(self, dt, bx, by):
        self._update_power(dt, bx, by)

        if self.status == "stowed":
            return
        if self.route and self.status == "deployed":
            if not can_move(self.mode):
                return   # frozen by battery policy
            self._walk_route(dt)
            return
        if self.status == "returning":
            u = self.world.units[self.name]
            dx, dy = bx - u.x, by - u.y
            d = math.hypot(dx, dy) or 1.0
            step = min(0.8, d) * (0.3 if self.mode == PowerMode.CONSERVE else 1.0)
            u.x += dx / d * step
            u.y += dy / d * step
            return

    def report(self):
        u = self.world.units[self.name]
        return {"name": self.name, "role": self.role,
                "x": round(u.x,2), "y": round(u.y,2),
                "battery": round(self.battery,1), "status": self.status,
                "mode": self.mode.value}


class ScoutDrone(Drone):
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="scout")
        self.findings = []

    def tick(self, dt, bx, by):
        self._update_power(dt, bx, by)
        if self.status == "deployed" and can_move(self.mode):
            u = self.world.units[self.name]
            u.x += random.uniform(-0.5, 0.5)
            u.y += random.uniform(-0.5, 0.5)
            if random.random() < 0.05:
                k = random.choice(["rock","crevice","flat","ice-signature"])
                self.findings.append((round(u.x,1), round(u.y,1), k))
                self.world.add_landmark(f"{k}-{len(self.findings)}", u.x, u.y, k)
                self.bus.send(self.name, "base", "finding", what=k,
                              x=round(u.x,1), y=round(u.y,1))
        elif self.status == "returning":
            Drone.tick(self, dt, bx, by)

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
        if not can_move(self.mode):
            say(f"[{self.name}] cannot sample: {describe(self.mode)}")
            return
        self.status = "deployed"
        self.world.move_unit(self.name, x, y)
        self.samples.append((x,y))
        self.bus.send(self.name, "base", "sample", x=x, y=y)
        say(f"[{self.name}] sampled at ({x},{y})")
        self.status = "returning"

    def tick(self, dt, bx, by):
        Drone.tick(self, dt, bx, by)


class ColonySeed(Drone):
    STAGES = ["seed","anchor","mast","shield","powered"]
    def __init__(self, name, bus, world):
        super().__init__(name, bus, world, role="colony")
        self.stage = 0
        self.chosen_site = None

    def place_auto(self, selector, search_radius=15.0):
        site = selector.best_site(search_radius=search_radius)
        if site is None:
            say(f"[{self.name}] no viable site found")
            return False
        self.chosen_site = site
        self.deploy(site.x, site.y)
        self.world.add_landmark(f"colony-site", site.x, site.y, "colony")
        say(f"[{self.name}] site score={site.total}  ok={site.ok()}")
        for r in site.reasons:
            say(f"    - {r}")
        if not site.ok():
            say(f"[{self.name}] WARNING: chosen site below threshold, risks storm damage")
        return True

    def tick(self, dt, bx, by):
        self._update_power(dt, bx, by)
        if self.status == "deployed" and can_move(self.mode):
            self.stage = min(int(self.battery // 20), len(self.STAGES) - 1)

    def report(self):
        r = super().report()
        r["stage"] = self.STAGES[self.stage]
        if self.chosen_site:
            r["site_score"] = self.chosen_site.total
        return r
