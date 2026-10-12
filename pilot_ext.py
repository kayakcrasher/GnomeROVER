"""Extended pilot commands: pose, ramp, watch, legs, home."""
import time
from gnome_rover.legs import LegPosition


def cmd_pose(rover, args):
    if len(args) != 4:
        print("usage: pose <FL|FR|BL|BR|all> <hip> <shoulder> <knee>")
        return
    which, h, s, k = args[0], float(args[1]), float(args[2]), float(args[3])
    if which.lower() == "all":
        for leg in rover.legs.values():
            leg.set_pose(h, s, k)
        print(f"[POSE] all -> hip={h} sh={s} kn={k}")
        return
    try:
        pos = LegPosition(which.upper())
    except ValueError:
        print(f"unknown leg: {which}")
        return
    rover.legs[pos].set_pose(h, s, k)
    print(f"[POSE] {pos.value} -> hip={h} sh={s} kn={k}")


def cmd_legs(rover, args):
    print("leg  hip     sh      kn")
    for pos, leg in rover.legs.items():
        print(f"{pos.value:>4} {leg.hip.angle:>7.1f} "
              f"{leg.shoulder.angle:>7.1f} {leg.knee.angle:>7.1f}")


def cmd_ramp(rover, args):
    if len(args) != 2:
        print("usage: ramp <FL|FR|BL|BR>_<hip|shoulder|knee> <target_deg>")
        return
    name, target = args[0].lower(), float(args[1])
    if "_" not in name:
        print("format: <LEG>_<joint>, e.g. FL_hip")
        return
    leg_key, joint_key = name.split("_", 1)
    try:
        pos = LegPosition(leg_key.upper())
    except ValueError:
        print(f"unknown leg: {leg_key}")
        return
    leg = rover.legs[pos]
    jmap = {"hip": leg.hip, "shoulder": leg.shoulder, "knee": leg.knee}
    if joint_key not in jmap:
        print(f"unknown joint: {joint_key}  (hip|shoulder|knee)")
        return
    joint = jmap[joint_key]
    joint.set_target(target)
    print(f"[RAMP] {pos.value}_{joint_key}: {joint.angle:.1f} -> {target:.1f}")
    while abs(joint.angle - target) > 0.5:
        print(f"  {joint.angle:>7.1f}")
        time.sleep(0.15)
    print(f"  {joint.angle:>7.1f}  (arrived)")


def cmd_watch(rover, args):
    if len(args) != 1:
        print("usage: watch <pan|tilt|battery|temp|FL_hip|FR_knee|...>")
        return
    field = args[0].lower()
    print(f"[WATCH] streaming '{field}' (Ctrl-C to stop)")
    try:
        while True:
            val = _read_field(rover, field)
            if val is None:
                print(f"no such field: {field}")
                return
            print(f"  {field} = {val}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[WATCH] stopped.")


def _read_field(rover, field):
    if field in ("pan", "tilt"):
        cam = rover.get_module("Camera")
        return getattr(cam, field) if cam else None
    if field in ("battery", "temp", "temp_c"):
        s = rover.get_module("Sensor")
        if not s:
            return None
        return s.battery_pct if field == "battery" else s.temperature
    if "_" in field:
        leg_key, joint_key = field.split("_", 1)
        try:
            pos = LegPosition(leg_key.upper())
        except ValueError:
            return None
        leg = rover.legs.get(pos)
        if not leg:
            return None
        jmap = {"hip": leg.hip, "shoulder": leg.shoulder, "knee": leg.knee}
        j = jmap.get(joint_key)
        return round(j.angle, 1) if j else None
    return None



def cmd_foot(rover, args):
    """foot <LEG|all> <x> <y> <z>  -- IK move foot in local frame."""
    if len(args) != 4:
        print("usage: foot <FL|FR|BL|BR|all> <x> <y> <z>")
        return
    which, x, y, z = args[0], float(args[1]), float(args[2]), float(args[3])
    if which.lower() == "all":
        for leg in rover.legs.values():
            ok = leg.move_foot(x, y, z)
        print(f"[FOOT] all -> ({x},{y},{z})")
        return
    try:
        pos = LegPosition(which.upper())
    except ValueError:
        print(f"unknown leg: {which}")
        return
    leg = rover.legs[pos]
    ok = leg.move_foot(x, y, z)
    if ok:
        print(f"[FOOT] {pos.value} -> ({x},{y},{z})")
    else:
        print(f"[FOOT] {pos.value} -> ({x},{y},{z})  UNREACHABLE, ignored")


def cmd_fkin(rover, args):
    """fkin <LEG|all>  -- print current foot position from joint angles."""
    if len(args) != 1:
        print("usage: fkin <FL|FR|BL|BR|all>")
        return
    which = args[0]
    targets = rover.legs.values() if which.lower() == "all" else [rover.legs[LegPosition(which.upper())]]
    for leg in targets:
        x, y, z = leg.foot()
        print(f"  {leg.position.value}: x={x:>6.2f} y={y:>6.2f} z={z:>6.2f}")
