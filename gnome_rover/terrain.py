"""Procedural terrain heightmap with slope-aware cost and line-of-sight."""
import math
import random


class Terrain:
    """Deterministic procedural heightmap over the local ENU frame."""

    def __init__(self, seed: int = 42, roughness: float = 1.0,
                 base_elevation_m: float = -2600.0):
        self.seed = seed
        self.roughness = roughness
        self.base_elevation_m = base_elevation_m
        # integer grid we can index by cell for caching
        self._cache = {}

    # --- height function ---

    def _hash(self, x: int, y: int) -> float:
        """Deterministic hash -> [-1, 1]."""
        h = (x * 73856093) ^ (y * 19349663) ^ (self.seed * 83492791)
        h = (h * 2654435761) & 0xFFFFFFFF
        return (h / 0xFFFFFFFF) * 2.0 - 1.0

    def _value_noise(self, x: float, y: float) -> float:
        """Bilinear-interpolated value noise."""
        x0, y0 = math.floor(x), math.floor(y)
        x1, y1 = x0 + 1, y0 + 1
        fx, fy = x - x0, y - y0
        # smoothstep
        sx = fx * fx * (3 - 2 * fx)
        sy = fy * fy * (3 - 2 * fy)

        v00 = self._hash(x0, y0)
        v10 = self._hash(x1, y0)
        v01 = self._hash(x0, y1)
        v11 = self._hash(x1, y1)

        a = v00 * (1 - sx) + v10 * sx
        b = v01 * (1 - sx) + v11 * sx
        return a * (1 - sy) + b * sy

    def elevation(self, x: float, y: float) -> float:
        """Elevation in meters at local (x, y)."""
        key = (round(x, 1), round(y, 1))
        if key in self._cache:
            return self._cache[key]

        # fBm: sum octaves of value noise
        z = 0.0
        amp = 1.0
        freq = 0.08
        norm = 0.0
        for _ in range(5):
            z += amp * self._value_noise(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        z = (z / norm) * self.roughness

        # gentle bowl (crater floor shape) so we get a natural basin
        bowl = -0.4 * (x * x + y * y) / 400.0
        z += bowl

        elev = self.base_elevation_m + z * 8.0   # ±8m swing
        self._cache[key] = elev
        return elev

    def slope_deg(self, x1, y1, x2, y2) -> float:
        """Slope between two points in degrees."""
        dz = self.elevation(x2, y2) - self.elevation(x1, y1)
        dx = x2 - x1
        dy = y2 - y1
        d_horiz = math.hypot(dx, dy)
        if d_horiz < 1e-6:
            return 0.0
        return math.degrees(math.atan2(abs(dz), d_horiz))

    def slope_at(self, x, y, sample=1.0) -> float:
        """Local slope in degrees (average of 4 directions)."""
        slopes = []
        for dx, dy in ((sample, 0), (-sample, 0), (0, sample), (0, -sample)):
            slopes.append(self.slope_deg(x, y, x + dx, y + dy))
        return sum(slopes) / len(slopes)

    # --- cost ---

    def traversal_cost(self, x1, y1, x2, y2) -> float:
        """Multiplier on distance: 1.0 flat, 8.0+ very steep."""
        s = self.slope_deg(x1, y1, x2, y2)
        if s < 5:
            return 1.0
        if s < 15:
            return 1.5
        if s < 25:
            return 3.0
        return 8.0

    # --- line of sight (for mesh/radio) ---

    def line_of_sight(self, x1, y1, x2, y2,
                      clearance_m: float = 2.0, samples: int = 20) -> bool:
        """True if terrain doesn't block radio between two points."""
        z1 = self.elevation(x1, y1)
        z2 = self.elevation(x2, y2)
        base = max(z1, z2) + clearance_m
        for i in range(1, samples):
            t = i / samples
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            if self.elevation(x, y) > base:
                return False
        return True

    # --- landing suitability ---

    def is_landable(self, x, y, radius=3.0) -> bool:
        """Flat enough within radius for a safe landing."""
        for ang in [i * math.pi / 6 for i in range(12)]:
            px = x + radius * math.cos(ang)
            py = y + radius * math.sin(ang)
            if self.slope_deg(x, y, px, py) > 8.0:
                return False
        return True

    # --- stats ---

    def stats(self, x_range=(-30, 30), y_range=(-30, 30), grid=10):
        zs = []
        slopes = []
        for i in range(grid + 1):
            for j in range(grid + 1):
                x = x_range[0] + (x_range[1] - x_range[0]) * i / grid
                y = y_range[0] + (y_range[1] - y_range[0]) * j / grid
                zs.append(self.elevation(x, y))
                if i < grid and j < grid:
                    slopes.append(self.slope_at(x, y))
        return {
            "min_z": round(min(zs), 2),
            "max_z": round(max(zs), 2),
            "mean_z": round(sum(zs) / len(zs), 2),
            "min_slope": round(min(slopes), 2),
            "max_slope": round(max(slopes), 2),
            "mean_slope": round(sum(slopes) / len(slopes), 2),
        }

    def ascii_map(self, x_range=(-30, 30), y_range=(-30, 30),
                  w=60, h=20) -> str:
        """Simple elevation map as ASCII."""
        rows = []
        zmin = min(self.elevation(x_range[0] + (x_range[1]-x_range[0])*i/w,
                                  y_range[0] + (y_range[1]-y_range[0])*j/h)
                   for i in range(w) for j in range(h))
        zmax = max(self.elevation(x_range[0] + (x_range[1]-x_range[0])*i/w,
                                  y_range[0] + (y_range[1]-y_range[0])*j/h)
                   for i in range(w) for j in range(h))
        chars = " .:-=+*#%@"
        for j in range(h - 1, -1, -1):   # top is +y
            row = ""
            for i in range(w):
                x = x_range[0] + (x_range[1]-x_range[0]) * i / (w - 1)
                y = y_range[0] + (y_range[1]-y_range[0]) * j / (h - 1)
                z = self.elevation(x, y)
                t = (z - zmin) / max(1e-6, zmax - zmin)
                row += chars[int(t * (len(chars) - 1))]
            rows.append(row)
        return "\n".join(rows)


# --- scenario presets ---

def terrain_for(scenario: str) -> Terrain:
    if scenario == "jezero":
        return Terrain(seed=42, roughness=0.6, base_elevation_m=-2600)
    if scenario == "gale":
        return Terrain(seed=7, roughness=1.4, base_elevation_m=-4500)
    if scenario == "elysium":
        return Terrain(seed=101, roughness=0.9, base_elevation_m=-2600)
    if scenario == "rough":
        return Terrain(seed=3, roughness=2.5, base_elevation_m=-1000)
    return Terrain(seed=42, roughness=1.0)
