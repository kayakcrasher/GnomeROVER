"""Site selection for colony seed placement.

Scores each candidate site against storm-survival criteria:
  + rock outcrop nearby (windbreak)
  + flat terrain (no tipping)
  - crevice nearby (fall hazard)
  - ice signature nearby (preserve for science)
  - distance from base (keep within radio range)
"""
from dataclasses import dataclass
from typing import List, Tuple, Optional


IDEAL = {
    "max_rock_dist":   4.0,   # must be this close to a rock
    "max_slope_deg":   8.0,   # flat-ish
    "min_crevice_dist": 6.0,  # keep crevices far
    "min_ice_dist":    8.0,   # don't build on science targets
    "max_base_dist":   40.0,  # stay in radio range
    "min_base_dist":   2.0,   # don't crowd the rover
}


@dataclass
class SiteScore:
    x: float
    y: float
    total: float
    reasons: List[str]

    def ok(self) -> bool:
        return self.total >= 0.6


class SiteSelector:
    def __init__(self, world):
        self.world = world

    def score(self, x: float, y: float) -> SiteScore:
        reasons = []
        score = 0.0

        # --- rock proximity (windbreak) ---
        rock_d = self._nearest_kind(x, y, "rock")
        if rock_d is None:
            reasons.append("no rocks nearby (-0.3)")
            score -= 0.3
        elif rock_d <= IDEAL["max_rock_dist"]:
            reasons.append(f"rock at {rock_d:.1f}cm (windbreak +0.5)")
            score += 0.5
        else:
            reasons.append(f"rock far ({rock_d:.1f}cm, +0.1)")
            score += 0.1

        # --- flat ground proxy: distance to nearest "flat" landmark ---
        flat_d = self._nearest_kind(x, y, "flat")
        if flat_d is not None and flat_d <= 3.0:
            reasons.append(f"flat patch at {flat_d:.1f}cm (+0.3)")
            score += 0.3
        else:
            reasons.append("no flat patch nearby (+0.0)")

        # --- crevice hazard ---
        crev_d = self._nearest_kind(x, y, "crevice")
        if crev_d is not None and crev_d < IDEAL["min_crevice_dist"]:
            reasons.append(f"crevice too close ({crev_d:.1f}cm, -0.6)")
            score -= 0.6
        else:
            reasons.append("clear of crevices (+0.2)")
            score += 0.2

        # --- ice science preservation ---
        ice_d = self._nearest_kind(x, y, "ice-signature")
        if ice_d is not None and ice_d < IDEAL["min_ice_dist"]:
            reasons.append(f"ice signature too close ({ice_d:.1f}cm, -0.4)")
            score -= 0.4
        else:
            reasons.append("clear of ice (+0.1)")
            score += 0.1

        # --- base distance (radio) ---
        base = self.world.landmarks.get("base")
        if base:
            bd = ((x - base.x) ** 2 + (y - base.y) ** 2) ** 0.5
            if bd < IDEAL["min_base_dist"]:
                reasons.append(f"too close to base ({bd:.1f}cm, -0.3)")
                score -= 0.3
            elif bd > IDEAL["max_base_dist"]:
                reasons.append(f"out of radio range ({bd:.1f}cm, -0.5)")
                score -= 0.5
            else:
                reasons.append(f"base range OK ({bd:.1f}cm, +0.2)")
                score += 0.2

        return SiteScore(round(x, 2), round(y, 2), round(score, 2), reasons)

    def _nearest_kind(self, x, y, kind) -> Optional[float]:
        best = None
        for lm in self.world.landmarks.values():
            if lm.kind != kind:
                continue
            d = ((x - lm.x) ** 2 + (y - lm.y) ** 2) ** 0.5
            if best is None or d < best:
                best = d
        return best

    def best_site(self, search_radius: float = 15.0, grid: int = 12) -> Optional[SiteScore]:
        """Grid-search a square around origin for the best-scoring site."""
        best = None
        for i in range(grid):
            for j in range(grid):
                x = -search_radius + (2 * search_radius) * i / (grid - 1)
                y = -search_radius + (2 * search_radius) * j / (grid - 1)
                s = self.score(x, y)
                if best is None or s.total > best.total:
                    best = s
        return best

    def explain(self, x, y):
        s = self.score(x, y)
        print(f"Site ({s.x}, {s.y}) score={s.total}  ok={s.ok()}")
        for r in s.reasons:
            print(f"  - {r}")
        return s
