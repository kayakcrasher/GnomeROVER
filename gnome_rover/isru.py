"""ISRU: water extraction, electrolysis, colony spawning.

Physical model (simplified but grounded):
  ice_kg_extracted = drill_rate * dt * ice_availability
  water_kg         = ice_kg * extraction_efficiency
  o2_kg            = water_kg * 0.888   (mass fraction O in H2O)
  h2_kg            = water_kg * 0.112
  power_cost       = water_kg * 3.5 kWh/kg  (electrolysis)
"""
import math
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from .quiet import say


# --- physical constants (approximate, tuned for playability) ---
DRILL_RATE_KG_PER_SOL = 0.5           # kg ice per sol at full power
EXTRACTION_EFFICIENCY = 0.6           # fraction of ice that becomes water
O2_MASS_FRACTION = 0.888
H2_MASS_FRACTION = 0.112
ELECTROLYSIS_KWH_PER_KG_WATER = 3.5
PANEL_KWH_PER_M2_PER_SOL = 2.4        # ~3 m^2 panels for a kW-class system

SPAWN_O2_REQUIRED_KG = 50.0
SPAWN_H2_REQUIRED_KG = 6.0
SPAWN_COOLDOWN_SOLS = 8
SPAWN_MAX_DISTANCE_M = 25.0
SPAWN_MIN_DISTANCE_M = 6.0
SPAWN_STARTER_KG = 5.0                # O2/H2 starter kit given to child


COLONY_STAGES = ["seed", "anchor", "mast", "shield", "powered", "factory"]

STAGE_REQUIREMENTS = {
    "anchor":  {"o2_kg": 5.0,  "h2_kg": 0.6,  "power_net_kwh": 0.0},
    "mast":    {"o2_kg": 12.0, "h2_kg": 1.5,  "power_net_kwh": 0.5},
    "shield":  {"o2_kg": 22.0, "h2_kg": 2.8,  "power_net_kwh": 1.0},
    "powered": {"o2_kg": 35.0, "h2_kg": 4.5,  "power_net_kwh": 2.0},
    "factory": {"o2_kg": 50.0, "h2_kg": 6.0,  "power_net_kwh": 3.0},
}


@dataclass
class ISRUState:
    """Resource tank state for one colony node."""
    o2_kg: float = 0.0
    h2_kg: float = 0.0
    water_kg: float = 0.0
    ice_kg_mined: float = 0.0
    power_net_kwh: float = 0.0
    last_sol_update: int = -1
    cooldown_until_sol: int = -1
    children_spawned: int = 0

    def totals(self):
        return {
            "o2": round(self.o2_kg, 2),
            "h2": round(self.h2_kg, 2),
            "h2o": round(self.water_kg, 2),
            "ice_mined": round(self.ice_kg_mined, 2),
            "power_net": round(self.power_net_kwh, 2),
            "children": self.children_spawned,
        }


class ISRUEngine:
    """Advances resource extraction and colony growth."""

    def __init__(self, base):
        self.base = base
        self.states: Dict[str, ISRUState] = {}   # colony name -> state
        self.panel_area_m2 = 6.0                  # per colony node
        self.drill_active = True

    def attach(self, colony_name: str):
        if colony_name not in self.states:
            self.states[colony_name] = ISRUState()

    def state(self, colony_name: str) -> Optional[ISRUState]:
        return self.states.get(colony_name)

    # --- per-tick physics ---

    def tick(self, dt_sol: float = 1.0 / 86400.0):
        """dt_sol = change in sols since last tick."""
        sol = self.base.comms.clock.sol()

        # solar input from the environment
        solar_flux = self.base.env.solar_flux()
        opacity = self.base.env.opacity_effects()
        effective_solar = solar_flux * opacity   # 0..1

        for name, st in self.states.items():
            colony = self.base.drones.get(name)
            if not colony or colony.status != "deployed":
                continue

            # only powered+ nodes do ISRU
            stage = getattr(colony, "stage", 0)
            if stage < 3:   # pre-shield: no ISRU yet
                continue

            # power balance
            power_in = self.panel_area_m2 * PANEL_KWH_PER_M2_PER_SOL * effective_solar
            # electrolysis cost is proportional to the water we process
            ice_avail = 0.5 if self.drill_active else 0.0
            ice_kg = DRILL_RATE_KG_PER_SOL * ice_avail * dt_sol
            water_kg = ice_kg * EXTRACTION_EFFICIENCY
            power_cost = water_kg * ELECTROLYSIS_KWH_PER_KG_WATER
            power_net = power_in - power_cost

            # update tanks
            st.ice_kg_mined += ice_kg
            st.water_kg += water_kg
            st.o2_kg += water_kg * O2_MASS_FRACTION
            st.h2_kg += water_kg * H2_MASS_FRACTION
            st.power_net_kwh += power_net
            st.last_sol_update = sol

            # advance stage when we hit requirements
            self._maybe_upgrade(colony, st, sol)

    def _maybe_upgrade(self, colony, st: ISRUState, sol: int):
        # find next stage
        cur_stage = getattr(colony, "stage", 0)
        if cur_stage >= len(COLONY_STAGES) - 1:
            return
        next_stage = COLONY_STAGES[cur_stage + 1]
        req = STAGE_REQUIREMENTS.get(next_stage)
        if not req:
            return
        if (st.o2_kg >= req["o2_kg"]
                and st.h2_kg >= req["h2_kg"]
                and st.power_net_kwh >= req["power_net_kwh"]):
            colony.stage = cur_stage + 1
            say(f"[ISRU] {colony.name} upgraded to {COLONY_STAGES[colony.stage]}  "
                f"(O2={st.o2_kg:.1f}kg H2={st.h2_kg:.2f}kg)")

    # --- spawning ---

    def can_spawn(self, colony_name: str) -> tuple:
        colony = self.base.drones.get(colony_name)
        st = self.states.get(colony_name)
        if not colony or not st:
            return False, "no colony"
        if getattr(colony, "stage", 0) < 5:   # must be FACTORY
            return False, "not factory stage"
        sol = self.base.comms.clock.sol()
        if sol < st.cooldown_until_sol:
            return False, f"cooldown until sol {st.cooldown_until_sol}"
        if st.o2_kg < SPAWN_O2_REQUIRED_KG:
            return False, f"O2 low ({st.o2_kg:.1f}/{SPAWN_O2_REQUIRED_KG})"
        if st.h2_kg < SPAWN_H2_REQUIRED_KG:
            return False, f"H2 low ({st.h2_kg:.2f}/{SPAWN_H2_REQUIRED_KG})"
        if st.power_net_kwh < 0:
            return False, f"power deficit ({st.power_net_kwh:.1f} kWh)"
        if colony.battery < 60:
            return False, f"battery low ({colony.battery:.0f}%)"
        return True, "ready"

    def find_spawn_site(self, parent_xy) -> Optional[tuple]:
        """Find a valid site for the child node."""
        from .sites import SiteSelector
        selector = SiteSelector(self.base.world)
        best = None
        # sample around the parent
        for angle_i in range(12):
            ang = 2 * math.pi * angle_i / 12
            for r in (8.0, 12.0, 16.0, 20.0):
                x = parent_xy[0] + r * math.cos(ang)
                y = parent_xy[1] + r * math.sin(ang)
                # too close to existing colony?
                too_close = False
                for other in self.states:
                    o = self.base.drones.get(other)
                    if not o:
                        continue
                    if math.hypot(o.x - x, o.y - y) < SPAWN_MIN_DISTANCE_M:
                        too_close = True
                        break
                if too_close:
                    continue
                score = selector.score(x, y)
                if not score.ok():
                    continue
                if best is None or score.total > best[2].total:
                    best = (x, y, score)
        return (best[0], best[1]) if best else None

    def spawn_child(self, colony_name: str) -> Optional[str]:
        colony = self.base.drones.get(colony_name)
        st = self.states.get(colony_name)
        ok, reason = self.can_spawn(colony_name)
        if not ok:
            say(f"[ISRU] cannot spawn from {colony_name}: {reason}")
            return None
        site = self.find_spawn_site((colony.x, colony.y))
        if not site:
            say(f"[ISRU] no valid spawn site near {colony_name}")
            return None

        # create a new ColonySeed in the drones dict
        from .drones import ColonySeed
        child_name = f"Colony-{len(self.base.drones) + 1}"
        child = ColonySeed(child_name, self.base.bus, self.base.world)
        self.base.drones[child_name] = child
        child.deploy(site[0], site[1])
        child.stage = 0
        self.attach(child_name)

        # transfer starter kit
        child_state = self.states[child_name]
        child_state.o2_kg = SPAWN_STARTER_KG
        child_state.h2_kg = SPAWN_STARTER_KG * H2_MASS_FRACTION / O2_MASS_FRACTION
        st.o2_kg -= SPAWN_STARTER_KG
        st.h2_kg -= child_state.h2_kg
        st.children_spawned += 1
        st.cooldown_until_sol = self.base.comms.clock.sol() + SPAWN_COOLDOWN_SOLS

        self.base.world.add_landmark(child_name, site[0], site[1], "colony")
        say(f"[ISRU] ★ {colony_name} spawned {child_name} at "
            f"({site[0]:.1f}, {site[1]:.1f})  "
            f"children={st.children_spawned}")

        # extend supply line to the new colony
        sl = getattr(self.base, "_supply", None)
        if sl:
            sl.build_for(child_name)
        return child_name

    # --- reporting ---

    def report(self):
        if not self.states:
            print("[ISRU] no colonies yet")
            return
        print(f"=== ISRU ({len(self.states)} node(s)) ===")
        for name, st in self.states.items():
            colony = self.base.drones.get(name)
            stage_name = COLONY_STAGES[getattr(colony, "stage", 0)]
            ok, reason = self.can_spawn(name)
            status = "READY" if ok else reason
            print(f"  {name:<12} stage={stage_name:<8} "
                  f"O2={st.o2_kg:>6.1f}kg  H2={st.h2_kg:>5.2f}kg  "
                  f"mined={st.ice_kg_mined:>7.2f}kg  "
                  f"children={st.children_spawned}  [{status}]")
