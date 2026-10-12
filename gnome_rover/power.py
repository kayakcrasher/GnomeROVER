"""Battery modes and solar charging state machine."""
from enum import Enum


class PowerMode(Enum):
    NORMAL    = "normal"
    CONSERVE  = "conserve"
    HALTED    = "halted"
    DOCKED    = "docked"
    CHARGING  = "charging"


# thresholds (percent)
LOW_THRESHOLD      = 25.0
CRITICAL_THRESHOLD = 10.0
CHARGE_EXIT        = 90.0
CHARGE_HYSTERESIS  = 85.0  # don't re-enter charging until below this

# drain rates (percent / second at 10Hz tick, i.e. per 0.1s dt in tick())
DRAIN_NORMAL   = 0.10
DRAIN_CONSERVE = 0.02   # 20% of normal
DRAIN_HALTED   = 0.00
CHARGE_RATE    = 0.15   # solar, faster than drain


def next_mode(current: PowerMode, battery: float, docked: bool) -> PowerMode:
    """Pure function: given state, what should the mode be now?"""
    # charging has its own exit (with hysteresis)
    if current == PowerMode.CHARGING:
        if battery >= CHARGE_EXIT:
            return PowerMode.NORMAL
        return PowerMode.CHARGING

    # if we're NORMAL but battery drops below hysteresis floor, go back to charging
    if current == PowerMode.NORMAL and battery < CHARGE_HYSTERESIS and docked:
        return PowerMode.CHARGING

    # docking is a request, honored until charged
    if current == PowerMode.DOCKED:
        return PowerMode.CHARGING   # immediately begin charging on dock

    # battery-driven transitions
    if battery <= 0.0:
        return PowerMode.HALTED
    if battery < CRITICAL_THRESHOLD:
        return PowerMode.HALTED
    if battery < LOW_THRESHOLD:
        return PowerMode.CONSERVE
    return PowerMode.NORMAL


def drain_for(mode: PowerMode) -> float:
    return {
        PowerMode.NORMAL:   DRAIN_NORMAL,
        PowerMode.CONSERVE: DRAIN_CONSERVE,
        PowerMode.HALTED:   DRAIN_HALTED,
        PowerMode.CHARGING: -CHARGE_RATE,   # negative drain = charging
        PowerMode.DOCKED:   -CHARGE_RATE,   # same
    }[mode]


def can_move(mode: PowerMode) -> bool:
    """Whether this mode permits motion."""
    return mode in (PowerMode.NORMAL, PowerMode.DOCKED)


def describe(mode: PowerMode) -> str:
    return {
        PowerMode.NORMAL:   "[NORMAL]",
        PowerMode.CONSERVE: "[CONSERVE]",
        PowerMode.HALTED:   "[HALTED]",
        PowerMode.DOCKED:   "[DOCKED]",
        PowerMode.CHARGING: "[CHARGING]",
    }[mode]
