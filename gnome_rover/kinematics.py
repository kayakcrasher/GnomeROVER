"""2-link planar IK per leg + forward kinematics.

Convention:
  Frame is local to the shoulder. +x = forward (leg's own "out" direction),
  +y = left, +z = up.
  All returned angles are in degrees.
  hip_yaw   : rotation about Z, 0 = pointing forward
  shoulder  : rotation about Y, positive = leg raised (foot above shoulder line)
  knee      : bend angle, positive = knee flexed (foot pulled in)
"""
import math


L1 = 8.0   # shoulder -> knee
L2 = 8.0   # knee -> foot


def ik_leg(x, y, z):
    """Solve (hip_yaw, shoulder, knee) so foot lands at (x,y,z).

    Returns degrees, or None if unreachable.
    """
    # hip yaw: aim the leg plane toward the foot
    hip_yaw = math.degrees(math.atan2(y, x))

    # reach in the leg's own plane
    r = math.hypot(x, y)
    d = math.hypot(r, z)

    if d > (L1 + L2) * 0.999:
        return None
    if d < abs(L1 - L2) * 1.001:
        return None

    # interior angle at the knee (between the two links)
    cos_knee_int = (L1*L1 + L2*L2 - d*d) / (2 * L1 * L2)
    cos_knee_int = max(-1.0, min(1.0, cos_knee_int))
    knee_int = math.acos(cos_knee_int)
    knee_bend = math.degrees(math.pi - knee_int)   # 0 = straight

    # shoulder: angle of the upper leg from the +r axis (in r-z plane)
    # interior angle at the shoulder between upper leg and the r-axis
    cos_shoulder = (L1*L1 + d*d - L2*L2) / (2 * L1 * d)
    cos_shoulder = max(-1.0, min(1.0, cos_shoulder))
    alpha = math.acos(cos_shoulder)                # radians
    angle_to_foot = math.atan2(z, r)               # from +r axis
    shoulder = math.degrees(angle_to_foot + alpha)

    return (hip_yaw, shoulder, knee_bend)


def fk_leg(hip_yaw, shoulder, knee):
    """Forward kinematics: return foot (x,y,z) from joint angles (deg)."""
    hy = math.radians(hip_yaw)
    sh = math.radians(shoulder)
    kn = math.radians(knee)

    # interior angle at knee (fk takes the *bend* angle)
    knee_int = math.pi - kn

    # upper leg: from shoulder, at angle sh from the +r axis
    r1 = L1 * math.cos(sh)
    z1 = L1 * math.sin(sh)

    # lower leg: rotated by -knee_int from upper leg direction
    lower_dir = sh - knee_int
    r2 = L2 * math.cos(lower_dir)
    z2 = L2 * math.sin(lower_dir)

    r = r1 + r2
    z = z1 + z2

    x = r * math.cos(hy)
    y = r * math.sin(hy)
    return (x, y, z)
