"""Mars environment: temperature, solar flux, dust storms, radiation.

Physically-inspired. Not a GCM, but captures the qualitative behavior:
  - diurnal temperature swing
  - solar charging only during daylight
  - cold reduces battery capacity
  - dust storms darken panels and force CONSERVE mode
"""
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, List
from .quiet import say
from .soltime import SOL_SECONDS


CLEAR_TAU = 0.3          # atmospheric opacity, clear
STORM_TAU = 5.0          # opacity during a full storm
STORM_THRESHOLD = 2.5    # above this, storm_mode engages


@dataclass
class EnvSample:
    sol: int
    sol_phase: float        # 0..1 (0 = midnight, 0.5 = noon)
    temp_c: float
    solar_flux: float       # 0..1 relative (1.0 = clear noon)
    opacity_tau: float      # 0.3 clear, 5.0 storm
    wind_ms: float
    rad_usv: float
    storm: bool


class MarsEnvironment:
    """Full environment model per sol."""

    def __init__(self, base, seed: int = 42, storm_rate: float = 0.02):
        self.base = base
        self.rng = random.Random(seed)
        self.opacity_tau = CLEAR_TAU
        self.wind_ms = 3.0
        self.storm_until_sol: int = -1
        self.next_storm_sol: int = self._schedule_storm()
        self.log: List[EnvSample] = []
        self._last_sample_sol: int = -1
        self._last_sample_phase: float = -1

    def _schedule_storm(self) -> int:
        """Poisson-ish: one storm every ~20 sols."""
        return self.base.comms.clock.sol() + self.rng.randint(12, 30)

    def _sol_phase(self) -> float:
        """0..1 through the current sol."""
        c = self.base.comms.clock
        secs_into_sol = c.mars_seconds % SOL_SECONDS
        return secs_into_sol / SOL_SECONDS

    # --- diurnal ---

    def solar_flux(self) -> float:
        """Fraction of clear-noon insolation (0 at night, 1 at clear noon)."""
        ph = self._sol_phase()
        # daytime is phase 0.25..0.75 (sunrise ~06:00, sunset ~18:00)
        if ph < 0.25 or ph > 0.75:
            return 0.0
        # peak at 0.5
        return math.sin((ph - 0.25) * 4 * math.pi / 2)

    def temperature_c(self) -> float:
        """Diurnal temperature curve. -80 to +20."""
        ph = self._sol_phase()
        # coldest at midnight (phase 0), warmest at noon (phase 0.5)
        base = -30.0 + 50.0 * math.sin((ph - 0.25) * 2 * math.pi)
        # cold snap during storms
        if self.is_storm():
            base -= 20.0
        # small noise
        return base + self.rng.uniform(-1.0, 1.0)

    def opacity_effects(self) -> float:
        """How much opacity attenuates solar (0..1). 1 = no attenuation."""
        # exp(-tau) approximation, normalized so tau=0.3 → ~0.95, tau=5 → ~0.1
        return max(0.05, math.exp(-self.opacity_tau * 0.6))

    # --- storms ---

    def is_storm(self) -> bool:
        return self.base.comms.clock.sol() <= self.storm_until_sol

    def _maybe_start_storm(self, sol: int):
        if self.is_storm():
            return
        if sol >= self.next_storm_sol:
            duration = self.rng.randint(2, 5)
            self.storm_until_sol = sol + duration
            self.next_storm_sol = sol + duration + self.rng.randint(12, 30)
            say(f"[ENV] DUST STORM starting — expected {duration} sol(s)")
            self.base._storm_mode = True

    def _maybe_end_storm(self, sol: int):
        if not self.is_storm() and getattr(self.base, "_storm_mode", False):
            self.base._storm_mode = False
            self.opacity_tau = CLEAR_TAU
            say(f"[ENV] dust storm ended; panels clearing")

    def update_opacity(self, dt_sol: float):
        """Opacity drifts toward a target based on wind."""
        target = CLEAR_TAU
        if self.is_storm():
            target = STORM_TAU
        elif self.wind_ms > 6.0:
            target = CLEAR_TAU + (self.wind_ms - 6.0) * 0.5
        # move 20% toward target each call
        self.opacity_tau += (target - self.opacity_tau) * 0.05

    def update_wind(self):
        # base wind varies with sol phase (daytime breezier)
        ph = self._sol_phase()
        base = 2.0 + 4.0 * abs(math.sin(ph * 2 * math.pi))
        noise = self.rng.uniform(-1.0, 1.0)
        self.wind_ms = max(0.0, base + noise)
        if self.is_storm():
            self.wind_ms += 6.0

    # --- main tick ---

    def tick(self):
        """Called from base.tick. Advances environment, samples once per sol."""
        sol = self.base.comms.clock.sol()
        ph = self._sol_phase()

        self._maybe_end_storm(sol)
        self._maybe_start_storm(sol)
        self.update_wind()
        self.update_opacity(0.0)

        # sample once per 10% of sol
        bin_phase = int(ph * 10)
        if sol != self._last_sample_sol or bin_phase != int(self._last_sample_phase * 10):
            self._last_sample_sol = sol
            self._last_sample_phase = ph
            self.log.append(EnvSample(
                sol=sol, sol_phase=round(ph, 3),
                temp_c=round(self.temperature_c(), 1),
                solar_flux=round(self.solar_flux() * self.opacity_effects(), 3),
                opacity_tau=round(self.opacity_tau, 3),
                wind_ms=round(self.wind_ms, 2),
                rad_usv=round(0.15 + (0.3 if self.is_storm() else 0.0)
                              + self.rng.uniform(0, 0.05), 3),
                storm=self.is_storm(),
            ))
            if len(self.log) > 500:
                self.log = self.log[-500:]

    # --- consumption side effects (called by power system) ---

    def cold_capacity_factor(self) -> float:
        """Battery capacity multiplier (1.0 warm, lower cold)."""
        t = self.temperature_c()
        if t >= 0:
            return 1.0
        return max(0.4, 1.0 + t / 100.0)   # -60C → 0.4

    def solar_input_factor(self) -> float:
        """Effective solar for charging. 0 at night, dark in storm."""
        return self.solar_flux() * self.opacity_effects()

    # --- reporting ---

    def latest(self) -> Optional[EnvSample]:
        return self.log[-1] if self.log else None

    def report(self):
        s = self.latest()
        if not s:
            print("[ENV] no samples yet")
            return
        flag = "STORM" if s.storm else "clear"
        print(f"[ENV] Sol {s.sol}  phase={s.sol_phase:.2f}  "
              f"temp={s.temp_c:.1f}C  solar={s.solar_flux:.3f}  "
              f"tau={s.opacity_tau:.2f}  wind={s.wind_ms:.1f}m/s  [{flag}]")
        print(f"  cold capacity factor: {self.cold_capacity_factor():.2f}")
        print(f"  next storm window: sol {self.next_storm_sol}")
