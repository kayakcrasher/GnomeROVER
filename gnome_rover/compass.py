"""Cardinal directions and heading math.

Convention (chosen at landing, NEVER changed):
  +x = East
  +y = North
  +z = Up
  Heading in degrees: 0=N, 90=E, 180=S, 270=W
"""
import math
from enum import Enum


class Cardinal(Enum):
    N = 0.0
    NE = 45.0
    E = 90.0
    SE = 135.0
    S = 180.0
    SW = 225.0
    W = 270.0
    NW = 315.0


# --- heading <-> vector ---

def heading_of(dx: float, dy: float) -> float:
    """Return compass heading (deg, 0=N) for a displacement."""
    # atan2(E, N) — note order
    return math.degrees(math.atan2(dx, dy)) % 360.0


def vector_of(heading_deg: float) -> tuple:
    """Return (dx, dy) unit vector for a compass heading."""
    r = math.radians(heading_deg)
    return (math.sin(r), math.cos(r))


# --- cardinal parsing ---

def parse(token: str) -> float:
    """'N' -> 0.0, 'SE' -> 135.0, '145' -> 145.0, etc."""
    t = token.strip().upper()
    if t in Cardinal.__members__:
        return Cardinal[t].value
    try:
        return float(t) % 360.0
    except ValueError:
        raise ValueError(f"bad heading: {token!r}")


def name_of(heading_deg: float) -> str:
    """Round to nearest of 8 cardinals for display."""
    h = heading_deg % 360.0
    names = ["N","NE","E","SE","S","SW","W","NW"]
    idx = int((h + 22.5) // 45) % 8
    return names[idx]


# --- move helpers ---

def move_point(x: float, y: float, heading_deg: float, dist: float):
    """Return new (x, y) after moving dist in heading_deg."""
    dx, dy = vector_of(heading_deg)
    return (x + dx * dist, y + dy * dist)


def bearing_between(x1, y1, x2, y2) -> float:
    """Compass heading from point 1 to point 2."""
    return heading_of(x2 - x1, y2 - y1)


def distance_between(x1, y1, x2, y2) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def describe_vector(dx, dy) -> str:
    """Human string: '5.2m NE (42°)'."""
    d = math.hypot(dx, dy)
    h = heading_of(dx, dy)
    return f"{d:.2f}m {name_of(h)} ({h:.0f}deg)"
