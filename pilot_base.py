"""Base-station pilot commands."""
from gnome_rover.base import BaseStation


def attach(rover):
    return BaseStation(rover)


def cmd_deploy(base, args):
    if not args:
        print("usage: deploy <scout|relay|sampler|colony> [x y]"); return
    x = float(args[1]) if len(args) > 1 else 5.0
    y = float(args[2]) if len(args) > 2 else 5.0
    base.deploy(args[0], x, y)


def cmd_recall(base, args):
    if len(args) != 1:
        print("usage: recall <name>"); return
    base.recall(args[0])


def cmd_map(base, args):       base.world.pretty()
def cmd_ping(base, args):      base.ping()
def cmd_report(base, args):    base.status_report()
def cmd_log(base, args):       base.log_dump()
def cmd_uplink(base, args):    base.uplink(" ".join(args)) if args else print("usage: uplink <msg>")
