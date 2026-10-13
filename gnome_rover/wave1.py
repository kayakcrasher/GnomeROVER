"""Wave 1 autonomous mission: hybrid scripted + autonomous phases."""
import time
import threading
from typing import Optional

from .supply import SupplyLine
from .sites import SiteSelector
from .infra import HomeBase, WeatherStation, RadioRepeater, Depot
from .bpv7 import make_bundle
from .quiet import say


PHASE_NAMES = {
    0: "LANDING",
    1: "STAKEOUT",
    2: "SURVEY",
    3: "ROADWORK",
    4: "INFRA_DEPLOY",
    5: "COLONIZE",
    6: "OPERATE",
    7: "REPORT",
}


class Wave1Mission:
    def __init__(self, base):
        self.base = base
        self.rover = base.rover
        self.phase = 0
        self.start_time = time.time()
        self.log = []
        self.operating = False
        self._thread: Optional[threading.Thread] = None
        self.new_since_last = 0

    # --- logging ---

    def say(self, msg):
        line = f"[WAVE1 P{self.phase}] {msg}"
        say(line)
        self.log.append(line)

    def phase_header(self, n: int):
        self.phase = n
        say(f"")
        say(f"════════ PHASE {n}: {PHASE_NAMES[n]} ════════")

    # --- phases ---

    def phase0_landing(self):
        self.phase_header(0)
        self.say("Rover landed at Jezero crater (18.4447°N, 77.4508°E)")
        self.rover.stand()
        self.say("Legs locked in level stance")
        self.say(f"Origin established: (0, 0) local")

    def phase1_stakeout(self):
        self.phase_header(1)
        base = self.base
        home = HomeBase("HomeBase", 0.0, 0.0)
        base.infra.add(home)
        base.world.add_landmark("HomeBase", 0.0, 0.0, "home")
        self.say("HomeBase deployed — charger + comms + solar mast")
        self.say(f"Landmark 'HomeBase' registered at origin")

    def phase2_survey(self, min_findings=6, max_seconds=120):
        self.phase_header(2)
        base = self.base
        scout = base.drones["Scout-1"]
        scout.deploy(5.0, 5.0)
        self.say(f"Scout deployed at (5, 5), surveying...")

        t0 = time.time()
        last_count = 0
        while True:
            time.sleep(2.0)
            n = len(scout.findings) if hasattr(scout, "findings") else 0
            if n != last_count:
                self.say(f"  {n} finding(s) so far")
                last_count = n
            if n >= min_findings:
                self.say(f"Survey complete: {n} findings")
                break
            if time.time() - t0 > max_seconds:
                self.say(f"Survey timeout after {max_seconds}s, "
                         f"{n} findings")
                break
            if scout.battery < 40:
                self.say(f"Scout battery low ({scout.battery:.0f}%), "
                         f"recalling")
                break

        scout.recall()
        self.say("Scout recalled")

    def phase3_roadwork(self):
        self.phase_header(3)
        base = self.base
        sl = SupplyLine(base.world, base.roads, home_xy=(0, 0))
        base._supply = sl
        n = sl.build_all()
        self.say(f"Built {n} road(s)")
        self.say(f"Total supply-line length: {sl.total_length():.1f}m")
        self.say(f"Connected nodes: {len(sl.connected)}")

    def phase4_infra(self):
        self.phase_header(4)
        base = self.base
        # pick a nice flat/rocky cluster for weather
        selector = SiteSelector(base.world)
        best = selector.best_site(search_radius=20)
        if best and best.ok():
            base.infra.add(WeatherStation("Weather-1", best.x, best.y))
            base.world.add_landmark("Weather-1", best.x, best.y, "weather")
            self.say(f"WeatherStation at ({best.x:.1f}, {best.y:.1f}) "
                     f"score={best.total}")
        else:
            base.infra.add(WeatherStation("Weather-1", 8.0, -8.0))
            self.say("WeatherStation at fallback (8, -8)")

        # repeater at the farthest connected node
        sl = base._supply
        if sl and len(sl.connected) > 1:
            far = max(sl.connected,
                      key=lambda p: p[0]**2 + p[1]**2)
            base.infra.add(RadioRepeater("Repeater-1", far[0], far[1]))
            base.world.add_landmark("Repeater-1", far[0], far[1], "repeater")
            self.say(f"RadioRepeater at ({far[0]:.1f}, {far[1]:.1f}) "
                     f"— extends mesh")
        else:
            self.say("Skipping repeater (no supply nodes)")

    def phase5_colonize(self):
        self.phase_header(5)
        base = self.base
        selector = SiteSelector(base.world)
        colony = base.drones["Colony-1"]
        ok = colony.place_auto(selector, search_radius=20.0)
        if ok:
            self.say(f"ColonySeed anchored at "
                     f"({colony.chosen_site.x:.1f}, "
                     f"{colony.chosen_site.y:.1f})")
            self.say(f"Site score: {colony.chosen_site.total}")
            # extend supply line to colony
            sl = base._supply
            if sl:
                sl.build_for("colony-site")
                self.say("Supply line extended to colony")
        else:
            self.say("Colonization failed — no viable site")

    def phase6_operate(self):
        self.phase_header(6)
        self.operating = True

        def loop():
            while self.operating:
                time.sleep(30.0)
                if not self.operating:
                    break
                # rescan for new landmarks
                sl = self.base._supply
                if sl:
                    n = sl.build_all()
                    if n > 0:
                        self.say(f"operate: extended supply by {n} road(s)")
                # queue telemetry for uplink
                self._queue_telemetry()
                # colony growth handled by its own tick
                # weather already samples internally
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        self.say("Mission now operating autonomously")
        self.say("Background loop: supply extension + telemetry uplink")

    def _queue_telemetry(self):
        base = self.base
        b = make_bundle("base", "dsn", "telemetry",
                        sol=base.comms.clock.sol(),
                        battery=round(base.infra.items["HomeBase"].battery, 1),
                        landmarks=len(base.world.landmarks),
                        roads=len(base.roads.roads))
        base.comms.uplink.enqueue(b, size_kb=1.0, priority=0)

    def phase7_report(self):
        self.phase_header(7)
        base = self.base
        elapsed = time.time() - self.start_time
        self.say(f"Mission elapsed (real): {elapsed:.1f}s")
        self.say(f"Sol: {base.comms.clock.sol()}")
        self.say(f"Landmarks: {len(base.world.landmarks)}")
        self.say(f"Roads: {len(base.roads.roads)}")
        self.say(f"Drones deployed: "
                 f"{sum(1 for d in base.drones.values() if d.status != 'stowed')}/4")
        self.say(f"Infra: {len(base.infra.items)}")
        self.say(f"Uplink queue: {len(base.comms.uplink.items)} bundle(s)")

    # --- top-level ---

    def stop(self):
        self.operating = False

    def run(self, operate_forever=True):
        try:
            self.phase0_landing()
            self.phase1_stakeout()
            self.phase2_survey()
            self.phase3_roadwork()
            self.phase4_infra()
            self.phase5_colonize()
            if operate_forever:
                self.phase6_operate()
            self.phase7_report()
        except Exception as e:
            self.say(f"ABORT: {type(e).__name__}: {e}")
            raise
