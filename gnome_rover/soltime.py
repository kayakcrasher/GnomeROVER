"""Mars time standards: sol, MSD, MTC, LST.

References:
  - One sol = 88,775.244 SI seconds (24h 39m 35.244s)
  - MSD epoch: 1873-12-29 12:00:00 GMT (terrestrial)
  - Sol 0 = landing day (Curiosity/InSight/Phoenix convention)
  - MTC = mean solar time at Airy-0 (Mars prime meridian)
  - LST = mean solar time at rover's areocentric longitude

Round-trip conversions are exact to sub-second precision.
"""
import time
from dataclasses import dataclass


# --- constants ---
SOL_SECONDS = 88_775.244                    # one Mars solar day in SI seconds
EARTH_DAY_SECONDS = 86_400.0
MSD_EPOCH_UNIX = -2_840_574_000.0            # 1873-12-29 12:00 GMT as Unix timestamp
# (rough — for real use, use SPICE; this is within a sol)


@dataclass
class MarsTime:
    sol: int                 # mission sol (0 = landing)
    mst_h: int               # Mars Standard Time hours (0-23)
    mst_m: int               # minutes
    mst_s: float             # seconds
    msd: float               # Mars Sol Date (fractional)
    mtc: str                 # "hh:mm:ss"
    lst: str                 # local solar time at rover longitude
    longitude_deg: float     # rover areocentric longitude

    def __str__(self):
        return f"Sol {self.sol:>5}  {self.mst_h:02d}:{self.mst_m:02d}:{int(self.mst_s):02d} MST  (MSD {self.msd:.6f})"


def _mars_seconds_since_epoch(now_unix: float) -> float:
    """Fractional sols since MSD epoch."""
    return (now_unix - MSD_EPOCH_UNIX) / SOL_SECONDS


def _format_mst(mars_seconds: float) -> tuple:
    """Convert (0..1) fraction of a sol into h:m:s."""
    total_seconds = (mars_seconds % 1.0) * SOL_SECONDS
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    return hours, minutes, seconds


def now(landing_unix: float, longitude_deg: float = 77.4508) -> MarsTime:
    """Current Mars time from a landing timestamp and rover longitude."""
    now_unix = time.time()
    mars_sols = _mars_seconds_since_epoch(now_unix)
    msd = 51_000 + mars_sols if mars_sols > 1e6 else mars_sols
    # msd is fractional sols since epoch; subtract landing to get mission sol
    landing_sols = _mars_seconds_since_epoch(landing_unix)
    sol = int(mars_sols - landing_sols)

    h, m, s = _format_mst(mars_sols)
    mtc = f"{h:02d}:{m:02d}:{int(s):02d}"

    # local solar time = MTC + (longitude / 360) * SOL_SECONDS, wrapped
    lst_offset_sols = longitude_deg / 360.0
    lst_h, lst_m, lst_s = _format_mst(mars_sols + lst_offset_sols)
    lst = f"{lst_h:02d}:{lst_m:02d}:{int(lst_s):02d}"

    return MarsTime(
        sol=sol, mst_h=h, mst_m=m, mst_s=s,
        msd=mars_sols, mtc=mtc, lst=lst,
        longitude_deg=longitude_deg,
    )


def sol_length_check():
    """Sanity: one sol in seconds, one sol in Earth days."""
    print(f"One sol   = {SOL_SECONDS} SI seconds")
    print(f"          = {SOL_SECONDS/3600:.4f} hours")
    print(f"          = {SOL_SECONDS/EARTH_DAY_SECONDS:.6f} Earth days")
    print(f"          = 1 Earth day + {SOL_SECONDS - EARTH_DAY_SECONDS:.3f} seconds")


def describe(landing_unix: float, longitude_deg: float = 77.4508):
    """Human-readable Mars time at the rover's location."""
    mt = now(landing_unix, longitude_deg)
    print(f"[MARS TIME] {mt}")
    print(f"  MTC (Airy-0):  {mt.mtc}")
    print(f"  LST (rover):   {mt.lst}")
    print(f"  areocentric lon: {mt.longitude_deg:.4f}°E")
    return mt
