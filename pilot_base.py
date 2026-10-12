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


def cmd_road(base, args):
    """road <new|add|list|show> [name] [x] [y]"""
    if not args:
        print("usage: road <new|add|list|show> ...")
        return
    sub = args[0].lower()
    if sub == "new" and len(args) >= 2:
        base.roads.new(args[1])
    elif sub == "add" and len(args) >= 4:
        base.roads.add(args[1], float(args[2]), float(args[3]))
    elif sub == "list":
        base.roads.list_all()
    elif sub == "show" and len(args) >= 2:
        base.roads.show(args[1])
    else:
        print("usage: road new <name> | road add <name> <x> <y> | road list | road show <name>")


def cmd_route(base, args):
    """route <x1> <y1> <x2> <y2>   OR   route <unit_a> <unit_b>"""
    if len(args) == 4:
        try:
            x1, y1, x2, y2 = map(float, args)
        except ValueError:
            print("usage: route <x1> <y1> <x2> <y2>"); return
    elif len(args) == 2:
        a = base.world.units.get(args[0])
        b = base.world.units.get(args[1])
        if not a or not b:
            print(f"unknown unit(s): {args}"); return
        x1, y1, x2, y2 = a.x, a.y, b.x, b.y
    else:
        print("usage: route <x1> <y1> <x2> <y2>  OR  route <unit> <unit>")
        return

    path, cost = base.roads.route((x1, y1), (x2, y2))
    if path:
        base.roads.pretty_route(path, cost)
    else:
        print(f"[ROUTE] no path from ({x1},{y1}) to ({x2},{y2}) — need roads or points within 3m")


def cmd_go(base, args):
    """go <unit> <x> <y>   -- plan a route via roads and start walking."""
    if len(args) != 3:
        print("usage: go <unit> <x> <y>"); return
    d = base._find(args[0]) or base.drones.get(args[0])
    if not d:
        print(f"no such unit: {args[0]}"); return
    d.go_to(float(args[1]), float(args[2]), roads=base.roads)
