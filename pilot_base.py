"""Base-station pilot commands."""
from gnome_rover.base import BaseStation
from gnome_rover.sites import SiteSelector


def attach(rover):
    return BaseStation(rover)


def cmd_deploy(base, args):
    if not args:
        print("usage: deploy <scout|relay|sampler|colony> [x y | auto]"); return
    role = args[0].lower()

    # auto site selection for colony
    if role in ("colony", "seed") and len(args) > 1 and args[1].lower() == "auto":
        colony = base._find("colony")
        if not colony:
            print("no colony seed in bays"); return
        selector = SiteSelector(base.world)
        print(f"[BASE] running site search...")
        ok = colony.place_auto(selector, search_radius=15.0)
        if ok:
            base.log(f"deployed {colony.name} to best site")
        return

    x = float(args[1]) if len(args) > 1 else 5.0
    y = float(args[2]) if len(args) > 2 else 5.0
    base.deploy(role, x, y)


def cmd_site(base, args):
    """site <x> <y>   — score a specific coordinate."""
    if len(args) != 2:
        print("usage: site <x> <y>"); return
    from gnome_rover.sites import SiteSelector
    SiteSelector(base.world).explain(float(args[0]), float(args[1]))


def cmd_find_site(base, args):
    """find-site [radius]   — grid search, print the winner."""
    radius = float(args[0]) if args else 15.0
    from gnome_rover.sites import SiteSelector
    best = SiteSelector(base.world).best_site(search_radius=radius)
    if not best:
        print("no site found"); return
    print(f"BEST: ({best.x}, {best.y}) score={best.total} ok={best.ok()}")
    for r in best.reasons: print(f"  - {r}")


def cmd_recall(base, args):
    if len(args) != 1:
        print("usage: recall <name>"); return
    base.recall(args[0])


def cmd_map(base, args):       base.world.pretty()
def cmd_ping(base, args):      base.ping()
def cmd_report(base, args):    base.status_report()
def cmd_log(base, args):       base.log_dump()
def cmd_uplink(base, args):    base.uplink(" ".join(args)) if args else print("usage: uplink <msg>")
