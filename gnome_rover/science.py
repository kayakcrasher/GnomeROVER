"""Science value model: score landmarks by scientific interest."""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional


CATEGORY_WEIGHT = {
    "ice-signature": 1.00,
    "rock":          0.70,
    "crevice":       0.50,
    "flat":          0.20,
    "colony":        0.00,
    "home":          0.00,
    "weather":       0.00,
    "repeater":      0.00,
    "depot":         0.00,
}

NOVELTY_SCALE_M = 15.0    # same-kind landmark this far away = full novelty
ACCESS_SCALE_M  = 10.0    # distance from nearest road node


@dataclass
class ScienceValue:
    landmark: str
    kind: str
    novelty: float
    fit: float
    access: float
    category_w: float
    total: float

    def line(self):
        return (f"  {self.landmark:<22} {self.kind:<14} "
                f"total={self.total:.3f}  "
                f"(n={self.novelty:.2f} f={self.fit:.2f} "
                f"a={self.access:.2f} w={self.category_w:.2f})")


class ScienceEvaluator:
    def __init__(self, world, roads=None):
        self.world = world
        self.roads = roads
        self.instrument_coverage = {
            "camera":     ("rock", "crevice", "flat"),
            "spectro":    ("rock", "ice-signature"),
            "drill":      ("rock",),
            "weather":    ("flat",),
            "all":        ("rock", "ice-signature", "crevice", "flat"),
        }

    def novelty(self, landmark) -> float:
        """How unique is this landmark vs same-kind neighbors?"""
        nearest = None
        for lm in self.world.landmarks.values():
            if lm.name == landmark.name or lm.kind != landmark.kind:
                continue
            d = math.hypot(lm.x - landmark.x, lm.y - landmark.y)
            if nearest is None or d < nearest:
                nearest = d
        if nearest is None:
            return 1.0
        # smooth decay from 1.0 to 0.3 as distance shrinks
        return 0.3 + 0.7 * min(1.0, nearest / NOVELTY_SCALE_M)

    def instrument_fit(self, landmark, instruments=("all",)) -> float:
        """How well does our instrument suite match this landmark?"""
        for inst in instruments:
            if landmark.kind in self.instrument_coverage.get(inst, ()):
                return 1.0
        return 0.4

    def accessibility(self, landmark) -> float:
        """How close is this to a road node?"""
        if not self.roads or not self.roads.roads:
            return 0.3   # no roads yet, low access
        nearest = None
        for road in self.roads.roads.values():
            for (wx, wy) in road.waypoints:
                d = math.hypot(wx - landmark.x, wy - landmark.y)
                if nearest is None or d < nearest:
                    nearest = d
        if nearest is None:
            return 0.3
        if nearest < 2.0:
            return 1.0
        return 0.3 + 0.7 * max(0.0, 1.0 - (nearest / ACCESS_SCALE_M))

    def evaluate(self, landmark_name: str,
                 instruments=("all",)) -> Optional[ScienceValue]:
        lm = self.world.landmarks.get(landmark_name)
        if not lm:
            return None
        n = self.novelty(lm)
        f = self.instrument_fit(lm, instruments)
        a = self.accessibility(lm)
        w = CATEGORY_WEIGHT.get(lm.kind, 0.1)
        total = n * f * a * w
        return ScienceValue(
            landmark=lm.name, kind=lm.kind,
            novelty=round(n, 3), fit=round(f, 3),
            access=round(a, 3), category_w=round(w, 3),
            total=round(total, 4),
        )

    def rank_all(self, min_total: float = 0.0) -> List[ScienceValue]:
        out = []
        for name in self.world.landmarks:
            sv = self.evaluate(name)
            if sv and sv.total >= min_total:
                out.append(sv)
        out.sort(key=lambda s: -s.total)
        return out

    def best(self) -> Optional[ScienceValue]:
        ranked = self.rank_all()
        return ranked[0] if ranked else None

    def report(self, top: int = 10, min_total: float = 0.0):
        ranked = self.rank_all(min_total)
        print(f"=== SCIENCE VALUES (top {min(top, len(ranked))} of {len(ranked)}) ===")
        for sv in ranked[:top]:
            print(sv.line())


# --- scout bias ---

def explorer_gradient(world, evaluator, x: float, y: float,
                      sample_radius: float = 3.0,
                      samples: int = 8) -> tuple:
    """Return a unit vector pointing toward higher-value unexplored space.

    Samples around the current position and picks the direction of
    highest average science potential.
    """
    best_score = -1.0
    best_dir = (0.0, 0.0)
    for i in range(samples):
        ang = 2 * math.pi * i / samples
        sx = x + sample_radius * math.cos(ang)
        sy = y + sample_radius * math.sin(ang)
        # heuristic: value near (sx, sy) is high if it's far from
        # existing landmarks of the same kind (novelty) and within
        # instrument range of known terrain
        local_score = 0.0
        for lm in world.landmarks.values():
            d = math.hypot(lm.x - sx, lm.y - sy)
            if d < 0.5:
                local_score -= 0.5   # don't revisit
            # reward distance from clustered landmarks
            if d < 3.0:
                local_score -= CATEGORY_WEIGHT.get(lm.kind, 0.1) * 0.3
        # slight preference for unexplored frontier
        local_score += 0.1 * math.hypot(sx - x, sy - y)
        if local_score > best_score:
            best_score = local_score
            best_dir = (math.cos(ang), math.sin(ang))
    return best_dir
