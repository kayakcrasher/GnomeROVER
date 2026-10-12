"""Leg and joint primitives for the GnomeROVER."""
import math
from dataclasses import dataclass
from enum import Enum


class LegPosition(Enum):
    FRONT_LEFT = "FL"
    FRONT_RIGHT = "FR"
    BACK_LEFT = "BL"
    BACK_RIGHT = "BR"


class JointType(Enum):
    HIP = "hip"
    SHOULDER = "shoulder"
    KNEE = "knee"


@dataclass
class Joint:
    name: str
    joint_type: JointType
    angle: float = 0.0
    min_angle: float = -90.0
    max_angle: float = 90.0
    target_angle: float = 0.0
    speed: float = 60.0

    def set_target(self, angle: float):
        self.target_angle = max(self.min_angle, min(self.max_angle, angle))

    def update(self, dt: float) -> bool:
        diff = self.target_angle - self.angle
        if abs(diff) < 0.5:
            self.angle = self.target_angle
            return True
        step = self.speed * dt
        self.angle += math.copysign(min(step, abs(diff)), diff)
        return False


@dataclass
class Leg:
    position: LegPosition
    hip: Joint
    shoulder: Joint
    knee: Joint

    def all_joints(self):
        return [self.hip, self.shoulder, self.knee]

    def set_pose(self, hip: float, shoulder: float, knee: float):
        self.hip.set_target(hip)
        self.shoulder.set_target(shoulder)
        self.knee.set_target(knee)

    def update(self, dt: float) -> bool:
        return all(j.update(dt) for j in self.all_joints())


    # ---- inverse kinematics ----
    def move_foot(self, x, y, z):
        """Command foot to (x,y,z) in the leg's local frame."""
        from .kinematics import ik_leg
        sol = ik_leg(x, y, z)
        if sol is None:
            return False
        hy, sh, kn = sol
        self.hip.set_target(hy)
        self.shoulder.set_target(sh)
        self.knee.set_target(kn)
        self.foot_x, self.foot_y, self.foot_z = x, y, z
        return True

    def foot(self):
        """Current foot position from forward kinematics."""
        from .kinematics import fk_leg
        return fk_leg(self.hip.angle, self.shoulder.angle, self.knee.angle)
