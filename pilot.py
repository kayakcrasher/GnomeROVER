"""GnomeROVER pilot REPL: live terminal control."""
import time
import threading
from gnome_rover import Rover, CameraModule, SensorModule, ArmModule


HELP = """
Commands:
  stand                     lock neutral pose
  walk                      engage walk gait
  trot                      engage trot gait
  plug <camera|sensor|arm>  hot-plug a module
  unplug <name>             remove a module
  look <pan> <tilt>         aim camera
  grab / release            arm gripper
  status                    dump full state
  help                      this list
  quit / exit               shut down
"""


def make_module(kind):
    kind = kind.lower()
    if kind == "camera":
        return CameraModule()
    if kind == "sensor":
        return SensorModule()
    if kind == "arm":
        return ArmModule()
    return None


def main():
    rover = Rover("GnomeROVER")
    rover.plug_in(CameraModule())
    rover.plug_in(SensorModule())
    rover.plug_in(ArmModule())
    rover.stand()
    rover.start(hz=20)

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
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print(HELP)
            elif cmd == "stand":
                rover.stand()
            elif cmd == "walk":
                rover.walk()
            elif cmd == "trot":
                rover.trot()
            elif cmd == "status":
                rover.pretty_print()
            elif cmd == "plug":
                if not args:
                    print("usage: plug <camera|sensor|arm>")
                    continue
                m = make_module(args[0])
                if m is None:
                    print(f"unknown module: {args[0]}")
                else:
                    rover.plug_in(m)
            elif cmd == "unplug":
                if not args:
                    print("usage: unplug <name>")
                    continue
                rover.unplug(args[0])
            elif cmd == "look":
                cam = rover.get_module("Camera")
                if not cam:
                    print("no camera plugged in")
                    continue
                if len(args) != 2:
                    print("usage: look <pan> <tilt>")
                    continue
                cam.look_at(float(args[0]), float(args[1]))
            elif cmd == "grab":
                arm = rover.get_module("Arm")
                if arm:
                    arm.grab()
                else:
                    print("no arm plugged in")
            elif cmd == "release":
                arm = rover.get_module("Arm")
                if arm:
                    arm.release()
                else:
                    print("no arm plugged in")
            else:
                print(f"unknown command: {cmd}  (try 'help')")
    except KeyboardInterrupt:
        print("\ninterrupted.")
    finally:
        rover.stop()
        print("bye.")


if __name__ == "__main__":
    main()
