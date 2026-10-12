"""2-link planar IK per leg + forward kinematics."""
import math


# Leg segment lengths (cm). Tunable.
L1 = 8.0   # shoulder -> knee
L2 = 8.0   # knee -> foot


def ik_leg(x, y, z):
    """Solve (hip_yaw, shoulder, knee) so foot lands at (x,y,z).

    Frame: origin at shoulder, +x forward, +y left, +z up.
    Returns degrees, or None if unreachable.
    """
    # hip yaw: rotate leg to point toward foot in XY plane
    hip_yaw = math.degrees(math.atan2(y, x))

    # in the leg's own plane, horizontal reach
    r = math.hypot(x, y)

    # distance shoulder -> foot
    d = math.hypot(r, z)
    if d > (L1 + L2) * 0.999:
        return None
    if d < abs(L1 - L2) * 1.001:
        return None

    # cosine rule for knee interior angle
    cos_knee = (L1*L1 + L2*L2 - d*d) / (2 * L1 * L2)
    cos_knee = max(-1.0, min(1.0, cos_knee))
    knee_interior = math.acos(cos_knee)
    knee = math.degrees(math.pi - knee_interior)   # bend angle

    # shoulder: angle from +r axis to the shoulder->foot line
    shoulder_to_foot = math.atan2(z, r)
    cos_a = (L1*L1 + d*d - L2*L2) / (2 * L1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    a = math.acos(cos_a)
    shoulder = math.degrees(shoulder_to_foot + a)

    return (hip_yaw, shoulder, knee)


def fk_leg(hip_yaw, shoulder, knee):
    """Forward kinematics: given angles (deg), return foot (x,y,z)."""
    hy = math.radians(hip_yaw)
    sh = math.radians(shoulder)
    kn = math.radians(knee)

    # interior angle at knee
    knee_interior = math.pi - kn

    # planar chain in the r-z plane
    # shoulder joint at origin, upper leg at angle 'sh' from +r axis
    r1 = L1 * math.cos(sh)
    z1 = L1 * math.sin(sh)

    # lower leg direction: sh - knee_interior
    lower_dir = sh - knee_interior
    r2 = L2 * math.cos(lower_dir)
    z2 = L2 * math.sin(lower_dir)

    r = r1 + r2
    z = z1 + z2

    # rotate back into XY by hip yaw
    x = r * math.cos(hy)
    y = r * math.sin(hy)
    return (x, y, z)
