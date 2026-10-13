"""GnomeROVER pilot REPL: live terminal control."""
import time
import threading
from gnome_rover import Rover, CameraModule, SensorModule, ArmModule
import pilot_ext
import pilot_base


HELP = """
stand                     lock neutral pose
walk                      engage walk gait
trot                      engage trot gait
plug <camera|sensor|arm>  hot-plug a module
unplug <name>             remove a module
look <pan> <tilt>         aim camera
grab / release            arm gripper
status                    full state dump
legs                      compact leg table
pose <leg|all> <h> <s> <k> set raw joint angles
ramp <LEG>_<joint> <deg>  sweep one joint slowly
watch <field>             stream a value (Ctrl-C stops)
fkin <leg|all>            print current foot position
foot <leg|all> <x> <y> <z> IK: send foot to local position
home                      alias for stand
deploy <role> [x y]       launch a sub-drone (scout|relay|sampler|colony)
recall <name>             call a drone home
map                       world map
ping                      radio check
report                    full mission status
log                       mission log
uplink <msg>              queue a message to Earth
infra [list|deploy]       show/deploy infrastructure
weather                   latest weather reading
quiet [on|off]            silence background chatter
site <x> <y>              score a colony site
find-site [radius]        grid-search best site
road <new|add|list|show>  define/inspect roads
route <x1> <y1> <x2> <y2> plan a route (or 'route <unitA> <unitB>')
go <unit> <x> <y>         plan route + walk it
help                      this list
quit / exit               shut down
"""


def make_module(kind):
    kind = kind.lower()
    return {"camera": CameraModule,
            "sensor": SensorModule,
            "arm":    ArmModule}.get(kind, lambda: None)()


def main():
    rover = Rover("GnomeROVER")
    rover.plug_in(CameraModule())
    rover.plug_in(SensorModule())
    rover.plug_in(ArmModule())
    rover.stand()
    rover.start(hz=20)

    base = pilot_base.attach(rover)

    def _base_loop():
        while rover.running:
            base.tick(0.1)
            time.sleep(0.1)
    threading.Thread(target=_base_loop, daemon=True).start()

    print(HELP)

    try:
        while True:
            try:
                line = input("rover> ").strip()
            except EOFError:
                break
            if not line:
                continue
            parts = line.split()
            cmd, args = parts[0].lower(), parts[1:]

            if   cmd in ("quit", "exit"): break
            elif cmd == "help":    print(HELP)
            elif cmd in ("stand", "home"): rover.stand()
            elif cmd == "walk":    rover.walk()
            elif cmd == "trot":    rover.trot()
            elif cmd == "status":  rover.pretty_print()
            elif cmd == "legs":    pilot_ext.cmd_legs(rover, args)
            elif cmd == "pose":    pilot_ext.cmd_pose(rover, args)
            elif cmd == "ramp":    pilot_ext.cmd_ramp(rover, args)
            elif cmd == "watch":   pilot_ext.cmd_watch(rover, args)
            elif cmd == "foot":    pilot_ext.cmd_foot(rover, args)
            elif cmd == "fkin":    pilot_ext.cmd_fkin(rover, args)
            elif cmd == "deploy":  pilot_base.cmd_deploy(base, args)
            elif cmd == "site":     pilot_base.cmd_site(base, args)
            elif cmd == "find-site": pilot_base.cmd_find_site(base, args)
            elif cmd == "road":     pilot_base.cmd_road(base, args)
            elif cmd == "route":    pilot_base.cmd_route(base, args)
            elif cmd == "go":       pilot_base.cmd_go(base, args)
            elif cmd == "recall":  pilot_base.cmd_recall(base, args)
            elif cmd == "map":     pilot_base.cmd_map(base, args)
            elif cmd == "ping":    pilot_base.cmd_ping(base, args)
            elif cmd == "report":  pilot_base.cmd_report(base, args)
            elif cmd == "log":     pilot_base.cmd_log(base, args)
            elif cmd == "uplink":  pilot_base.cmd_uplink(base, args)
            elif cmd == "infra":    pilot_base.cmd_infra(base, args)
            elif cmd == "weather":  pilot_base.cmd_weather(base, args)
            elif cmd == "quiet":    pilot_base.cmd_quiet(base, args)
            elif cmd == "plug":
                if not args: print("usage: plug <camera|sensor|arm>")
                else: rover.plug_in(make_module(args[0]))
            elif cmd == "unplug":
                if args: rover.unplug(args[0])
            elif cmd == "look":
                cam = rover.get_module("Camera")
                if not cam: print("no camera plugged in")
                elif len(args) != 2: print("usage: look <pan> <tilt>")
                else: cam.look_at(float(args[0]), float(args[1]))
            elif cmd == "grab":
                arm = rover.get_module("Arm")
                arm.grab() if arm else print("no arm plugged in")
            elif cmd == "release":
                arm = rover.get_module("Arm")
                arm.release() if arm else print("no arm plugged in")
            elif cmd == "supply":   pilot_base.cmd_supply(base, args)
            elif cmd == "time":     pilot_base.cmd_time(base, args)
            elif cmd == "pass":     pilot_base.cmd_pass(base, args)
            elif cmd == "uplink-q": pilot_base.cmd_uplink_queue(base, args)
            elif cmd == "comms":    pilot_base.cmd_comms(base, args)
            elif cmd == "queue":    pilot_base.cmd_queue(base, args)
            elif cmd == "diag":     pilot_base.cmd_diag(base, args)
            elif cmd == "wave1":    pilot_base.cmd_wave1(base, args)
            else:
                print(f"unknown command: {cmd}  (try 'help')")
    except KeyboardInterrupt:
        print("\ninterrupted.")
    finally:
        rover.stop()
        print("bye.")


if __name__ == "__main__":
    main()
