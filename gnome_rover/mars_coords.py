"""Martian coordinate systems and conversion math.

Conventions:
  - Areocentric coordinates: (lat_deg, lon_deg, height_m)
    lat positive north, lon positive EAST (MOLA convention)
  - Local frame: ENU (East-North-Up) in meters, centered on a reference
    point (the landing site / home base)
  - Areoid radius for Mars (mean sphere) = 3,389,500 m
  - Flattening f = 0.00589 (Mars is oblate)
"""
import math


# --- Mars reference constants ---
MARS_RADIUS_M = 3_389_500.0       # volumetric mean radius
MARS_FLATTENING = 0.00589
MARS_MAJOR_AXIS_M = 3_396_190.0   # equatorial radius
MARS_MINOR_AXIS_M = 3_376_200.0   # polar radius
MARS_SOL_SECONDS = 88_775.244     # one sol, for reference


# --- distance ---

def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance on a sphere (meters). Good enough for <100 km."""
    r = MARS_RADIUS_M
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def vincenty_m(lat1, lon1, lat2, lon2):
    """More accurate ellipsoidal distance. Slower but <1m error."""
    a = MARS_MAJOR_AXIS_M
    f = MARS_FLATTENING
    b = a * (1 - f)

    L = math.radians(lon2 - lon1)
    U1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    U2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sinU1, cosU1 = math.sin(U1), math.cos(U1)
    sinU2, cosU2 = math.sin(U2), math.cos(U2)

    lam = L
    for _ in range(20):
        sinLam, cosLam = math.sin(lam), math.cos(lam)
        sinSig = math.sqrt((cosU2*sinLam)**2 + (cosU1*sinU2 - sinU1*cosU2*cosLam)**2)
        if sinSig == 0:
            return 0.0
        cosSig = sinU1*sinU2 + cosU1*cosU2*cosLam
        sigma = math.atan2(sinSig, cosSig)
        sinAl = cosU1*cosU2*sinLam/sinSig
        cos2Al = 1 - sinAl**2
        cos2Sm = cosSig - 2*sinU1*sinU2/cos2Al if cos2Al != 0 else 0
        C = f/16*cos2Al*(4 + f*(4 - 3*cos2Al))
        lam_prev = lam
        lam = L + (1 - C)*f*sinAl*(sigma + C*sinSig*(cos2Sm + C*cosSig*(-1 + 2*cos2Sm**2)))
        if abs(lam - lam_prev) < 1e-12:
            break

    u2 = cos2Al * (a*a - b*b) / (b*b)
    A = 1 + u2/16384*(4096 + u2*(-768 + u2*(320 - 175*u2)))
    B = u2/1024*(256 + u2*(-128 + u2*(74 - 47*u2)))
    dSig = B*sinSig*(cos2Sm + B/4*(cosSig*(-1 + 2*cos2Sm**2) - B/6*cos2Sm*(-3 + 4*sinSig**2)*(-3 + 4*cos2Sm**2)))
    return b * A * (sigma - dSig)


# --- local ENU <-> areocentric ---

class LocalFrame:
    """Local ENU frame centered at a reference (lat0, lon0)."""
    def __init__(self, lat0: float, lon0: float, height0: float = 0.0, name: str = "origin"):
        self.lat0 = lat0
        self.lon0 = lon0
        self.height0 = height0
        self.name = name
        # meters per degree at this latitude
        self.m_per_deg_lat = math.radians(1.0) * MARS_RADIUS_M
        self.m_per_deg_lon = math.radians(1.0) * MARS_RADIUS_M * math.cos(math.radians(lat0))

    def to_local(self, lat, lon, height=0.0):
        """Areocentric -> local ENU (x=east, y=north, z=up in meters)."""
        dlat = lat - self.lat0
        dlon = lon - self.lon0
        x = dlon * self.m_per_deg_lon      # east
        y = dlat * self.m_per_deg_lat      # north
        z = height - self.height0
        return (x, y, z)

    def to_areocentric(self, x, y, z=0.0):
        """Local ENU -> areocentric (lat, lon, height)."""
        lat = self.lat0 + (y / self.m_per_deg_lat)
        lon = self.lon0 + (x / self.m_per_deg_lon)
        height = self.height0 + z
        return (lat, lon, height)

    def distance(self, x1, y1, x2, y2):
        """Local distance with ellipsoid correction."""
        lat1, lon1, _ = self.to_areocentric(x1, y1)
        lat2, lon2, _ = self.to_areocentric(x2, y2)
        return vincenty_m(lat1, lon1, lat2, lon2)


# --- real Mars sites (areocentric, east-positive) ---

KNOWN_SITES = {
    "Jezero_landing":   (18.4447, 77.4508, -2600.0),   # Perseverance landing
    "Wright_Brothers":  (18.4447, 77.4508, -2600.0),   # Ingenuity first flight field
    "Mala_Mala":        (18.2,    77.5,    -2400.0),   # recent Perseverance location
    "Gale_Crater":      (-4.5895, 137.4417, -4500.0),  # Curiosity landing
    "Elysium_Planitia": (4.5,     135.9,    -2600.0),  # candidate future site
}


def site_local(name: str, lat0: float, lon0: float):
    """Build a LocalFrame for a named site, relative to a rover origin."""
    if name not in KNOWN_SITES:
        raise ValueError(f"unknown site: {name}")
    lat, lon, h = KNOWN_SITES[name]
    return LocalFrame(lat0, lon0, height0=0.0, name=name).to_local(lat, lon, h)


def describe(lat, lon, height=0.0):
    """Human-readable areocentric coordinate."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}°{ns}, {abs(lon):.4f}°{ew} @ {height:.0f}m"
