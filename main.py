"""GnomeROVER demo entrypoint."""
import time
from gnome_rover import Rover, CameraModule, SensorModule, ArmModule


def main():
    rover = Rover("GnomeROVER")
    cam = CameraModule()
    sensors = SensorModule()
    arm = ArmModule()
    rover.plug_in(cam)
    rover.plug_in(sensors)
    rover.plug_in(arm)

    rover.stand()
    rover.start(hz=20)
    time.sleep(1.0)
    rover.pretty_print()

    rover.walk()
    time.sleep(2.0)
    rover.pretty_print()

    rover.trot()
    time.sleep(2.0)

    cam.look_at(pan=90, tilt=-15)
    arm.grab()
    time.sleep(1.0)
    rover.pretty_print()

    rover.stop()


if __name__ == "__main__":
    main()
