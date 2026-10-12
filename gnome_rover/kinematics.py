"""2-link planar IK + FK for a single leg.

Convention (must stay consistent between ik_leg and fk_leg):

  Leg-local frame:
    +x = forward (leg's outward direction)
    +y = left
    +z = up
    Origin is at the shoulder joint.

  Angles in degrees:
    hip_yaw  : rotation about Z. 0 deg = leg plane aligned with +x.
    shoulder : angle of the UPPER leg measured from the horizontal
               (the +r axis). Positive = knee rises above the shoulder line.
    knee     : INTERIOR angle at the knee. 180 deg = straight leg, 0 deg = folded.

  Knee bends forward (toward +r direction).
"""
import math


L1 = 8.0   # shoulder -> knee
L2 = 8.0   # knee -> foot

EPS = 1e-6


def ik_leg(x, y, z):
    """Solve (hip_yaw, shoulder, knee) so foot lands at (x,y,z).

    Returns degrees, or None if unreachable.
    """
    hip_yaw = math.degrees(math.atan2(y, x))
    r = math.hypot(x, y)
    d = math.hypot(r, z)

    if d > (L1 + L2) - EPS:
        return None
    if d < abs(L1 - L2) + EPS:
        return None

    # Interior angle at the knee (law of cosines)
    cos_k = (L1*L1 + L2*L2 - d*d) / (2 * L1 * L2)
    cos_k = max(-1.0, min(1.0, cos_k))
    knee = math.degrees(math.acos(cos_k))     # interior

    # Shoulder: angle from +r axis to the upper leg
    # Law of cosines on the triangle (shoulder, knee, foot):
    #   angle at shoulder between upper leg and the line to the foot
    cos_a = (L1*L1 + d*d - L2*L2) / (2 * L1 * d)
    cos_a = max(-1.0, min(1.0, cos_a))
    a = math.acos(cos_a)

    angle_to_foot = math.atan2(z, r)
    shoulder = math.degrees(angle_to_foot + a)   # knee "above" the line

    return (hip_yaw, shoulder, knee)


def fk_leg(hip_yaw, shoulder, knee):
    """Forward kinematics: return foot (x,y,z) given joint angles in degrees.

    Matches ik_leg's convention exactly.
    """
    hy = math.radians(hip_yaw)
    sh = math.radians(shoulder)
    kn = math.radians(knee)          # interior angle

    # Upper leg: at angle `sh` from +r axis
    r1 = L1 * math.cos(sh)
    z1 = L1 * math.sin(sh)

    # Lower leg: upper leg direction, rotated by (pi - knee_interior)
    # because the leg folds by the exterior angle.
    # Exterior angle at knee = pi - interior.
    exterior = math.pi - kn
    lower_dir = sh - exterior       # fold DOWN/FORWARD from upper leg

    r2 = L2 * math.cos(lower_dir)
    z2 = L2 * math.sin(lower_dir)

    r = r1 + r2
    z = z1 + z2

    x = r * math.cos(hy)
    y = r * math.sin(hy)
    return (x, y, z)
