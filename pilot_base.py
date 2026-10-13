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


def cmd_infra(base, args):
    """infra                       -- list infra
       infra deploy home <x> <y>   -- place HomeBase
       infra deploy weather <x> <y>
       infra deploy repeater <x> <y>
       infra deploy depot <x> <y>"""
    if not args or args[0] == "list":
        base.infra.pretty()
        return
    if args[0] == "deploy" and len(args) >= 4:
        kind = args[1].lower()
        x, y = float(args[2]), float(args[3])
        if kind == "home":
            base.infra.add(HomeBase("HomeBase", x, y))
            base.world.add_landmark("HomeBase", x, y, "home")
        elif kind == "weather":
            n = f"Weather-{len(base.infra.of_kind('weather'))+1}"
            base.infra.add(WeatherStation(n, x, y))
            base.world.add_landmark(n, x, y, "weather")
        elif kind == "repeater":
            n = f"Repeater-{len(base.infra.of_kind('repeater'))+1}"
            base.infra.add(RadioRepeater(n, x, y))
            base.world.add_landmark(n, x, y, "repeater")
        elif kind == "depot":
            n = f"Depot-{len(base.infra.of_kind('depot'))+1}"
            base.infra.add(Depot(n, x, y))
            base.world.add_landmark(n, x, y, "depot")
        else:
            print(f"unknown kind: {kind}")
        return
    print("usage: infra [list | deploy <home|weather|repeater|depot> <x> <y>]")


def cmd_weather(base, args):
    ws = base.infra.weather()
    if not ws:
        print("[WEATHER] no weather station deployed")
        return
    r = ws.latest()
    if not r:
        print("[WEATHER] no readings yet")
        return
    print(f"[WEATHER {ws.name} @ ({ws.x},{ws.y})]")
    print(f"  wind: {r['wind_ms']} m/s")
    print(f"  temp: {r['temp_c']} C")
    print(f"  pressure: {r['pressure_pa']} Pa")
    print(f"  rad: {r['rad_usv']} uSv/h")
    if ws.storm_warning():
        print("  ** STORM WARNING **")


def cmd_quiet(base, args):
    from gnome_rover.quiet import set_quiet, is_quiet
    if not args:
        print(f"quiet is {'ON' if is_quiet() else 'OFF'}")
        return
    on = args[0].lower() in ("on", "true", "1", "yes")
    set_quiet(on)
    print(f"quiet -> {'ON' if on else 'OFF'}")


def cmd_supply(base, args):
    """supply [report|build|trace <x> <y>]"""
    from gnome_rover.supply import SupplyLine, trace_line
    sl = getattr(base, "_supply", None)
    if sl is None:
        sl = SupplyLine(base.world, base.roads, home_xy=(0, 0))
        base._supply = sl
    if not args or args[0] == "report":
        sl.report()
    elif args[0] == "build":
        n = sl.build_all()
        print(f"[SUPPLY] built {n} new road(s)")
    elif args[0] == "trace" and len(args) >= 3:
        trace_line(base.world, base.roads, float(args[1]), float(args[2]))
    else:
        print("usage: supply [report|build|trace <x> <y>]")


def cmd_time(base, args):
    from gnome_rover.soltime import describe
    h, m, s = base.comms.clock.hms()
    print(f"[MARS TIME] Sol {base.comms.clock.sol()}  "
          f"{h:02d}:{m:02d}:{s:02d} MST")


def cmd_pass(base, args):
    print("[ORBITER PASSES]")
    for orb in base.comms.orbiters:
        status = "OVERHEAD" if orb.is_overhead(base.comms.clock) else orb.next_pass_in_hms(base.comms.clock)
        print(f"  {orb.name:<10} {status}")
    print(f"  Earth: {base.comms.earth.describe()}")


def cmd_uplink_queue(base, args):
    base.comms.uplink.pretty()


def cmd_comms(base, args):
    base.comms.status()


def cmd_queue(base, args):
    """queue <size_kb> <kind> [priority]  -- enqueue a test bundle"""
    from gnome_rover.bpv7 import make_bundle
    if len(args) < 2:
        print("usage: queue <size_kb> <kind> [prio]")
        return
    size = float(args[0]); kind = args[1]
    prio = int(args[2]) if len(args) > 2 else 0
    b = make_bundle("base", "dsn", kind, what=kind, size_kb=size)
    base.comms.uplink.enqueue(b, size_kb=size, priority=prio)
    print(f"[QUEUE] {size} KB {kind} prio={prio}  ({len(base.comms.uplink.items)} total)")


def cmd_diag(base, args):
    """diag [full|<subsystem>]"""
    from gnome_rover.diagnostics import run_all, run_subsystem
    if not args:
        run_all(base.rover, base, show_ok=True)
    elif args[0] == "full":
        run_all(base.rover, base, show_ok=True)
    else:
        run_subsystem(base.rover, base, args[0])


def cmd_wave1(base, args):
    """wave1 [stop]  -- run (or stop) the full autonomous mission."""
    from gnome_rover.wave1 import Wave1Mission
    m = getattr(base, "_wave1", None)
    if args and args[0].lower() == "stop":
        if m:
            m.stop()
            print("[WAVE1] stopping background operations")
        return
    if m and m.operating:
        print("[WAVE1] already running")
        return
    m = Wave1Mission(base)
    base._wave1 = m
    m.run(operate_forever=True)


def cmd_save(base, args):
    from gnome_rover.persist import save
    from pathlib import Path
    path = Path(args[0]) if args else None
    save(base) if path is None else save(base, path)


def cmd_load(base, args):
    from gnome_rover.persist import load
    from pathlib import Path
    path = Path(args[0]) if args else None
    load(base) if path is None else load(base, path)


def cmd_wipe(base, args):
    """wipe -- clear all world/roads/infra/drones state (fresh mission)."""
    confirm = args and args[0].lower() in ("yes", "y", "confirm")
    if not confirm:
        print("wipe requires confirmation: wipe yes")
        return
    from pathlib import Path
    from gnome_rover.persist import DEFAULT_PATH
    if DEFAULT_PATH.exists():
        DEFAULT_PATH.unlink()
        print(f"[WIPE] deleted {DEFAULT_PATH}")
    base.world.landmarks.clear()
    base.world.units.clear()
    base.world.add_unit("rover", role="base")
    base.roads.roads.clear()
    base.infra.items.clear()
    base.mission_log.clear()
    for d in base.drones.values():
        d.status = "stowed"
        d.battery = 100.0
        d.route = []
    print("[WIPE] state cleared")


def cmd_fault(base, args):
    """fault <kind> <target> [duration_s]  |  fault clear [target]  |  fault list"""
    from gnome_rover.faults import FAULT_TYPES
    if not args:
        print("usage: fault <kind> <target> [secs] | fault clear [target] | fault list")
        print("kinds:", ", ".join(FAULT_TYPES))
        return
    sub = args[0].lower()
    if sub == "list":
        base.faults.list_active()
        return
    if sub == "clear":
        target = args[1] if len(args) > 1 else None
        base.faults.clear(target)
        return
    if sub not in FAULT_TYPES:
        print(f"unknown fault kind: {sub}")
        print("valid:", ", ".join(FAULT_TYPES))
        return
    if len(args) < 2:
        print("usage: fault <kind> <target> [secs]")
        return
    target = args[1]
    dur = float(args[2]) if len(args) > 2 else -1.0
    base.faults.inject(target, sub, duration_s=dur)


def cmd_science(base, args):
    """science [top N]  -- rank landmarks by science value."""
    from gnome_rover.science import ScienceEvaluator
    ev = ScienceEvaluator(base.world, base.roads)
    n = int(args[0]) if args and args[0].isdigit() else 10
    ev.report(top=n)


def cmd_dash(base, args):
    """dash -- launch curses dashboard (blocks until you press q)."""
    from gnome_rover.dashboard import run
    print("[DASH] launching... press q to exit")
    import time as _t
    _t.sleep(0.5)
    run(base)


def cmd_sol(base, args):
    """sol -- print current sol report."""
    base.solops.print_current()


def cmd_sol_history(base, args):
    """solhistory [N] -- list past sol summaries."""
    n = int(args[0]) if args and args[0].isdigit() else 10
    base.solops.print_history(n=n)


def cmd_terrain(base, args):
    """terrain [stats|map|slope <x> <y>|scenario <name>]"""
    from gnome_rover.terrain import terrain_for
    t = getattr(base, "_terrain", None)
    if t is None:
        t = terrain_for("jezero")
        base._terrain = t
    if not args:
        s = t.stats()
        print(f"[TERRAIN] jezero")
        for k, v in s.items():
            print(f"  {k:<12} {v}")
        print(t.ascii_map())
    elif args[0] == "map":
        print(t.ascii_map())
    elif args[0] == "stats":
        s = t.stats()
        for k, v in s.items():
            print(f"  {k:<12} {v}")
    elif args[0] == "slope" and len(args) >= 3:
        x, y = float(args[1]), float(args[2])
        print(f"  ({x},{y}): z={t.elevation(x,y):.2f}m  "
              f"slope={t.slope_at(x,y):.2f}deg  "
              f"landable={t.is_landable(x,y)}")
    elif args[0] == "scenario" and len(args) >= 2:
        base._terrain = terrain_for(args[1])
        print(f"[TERRAIN] switched to '{args[1]}'")
    else:
        print("usage: terrain [map|stats|slope <x> <y>|scenario <name>]")


def cmd_env(base, args):
    """env [storm]  -- show environment, or force a storm."""
    if args and args[0] == "storm":
        base.env.storm_until_sol = base.comms.clock.sol() + 5
        base._storm_mode = True
        print("[ENV] forced storm for 5 sols")
        return
    base.env.report()
    # small history
    print("  recent samples:")
    for s in base.env.log[-8:]:
        tag = "STORM" if s.storm else "     "
        print(f"    Sol {s.sol:>3} ph={s.sol_phase:.2f} "
              f"T={s.temp_c:>6.1f}C sol={s.solar_flux:.3f} "
              f"tau={s.opacity_tau:.2f} wind={s.wind_ms:>4.1f} {tag}")


def cmd_storm(base, args):
    """storm [start|end] -- manual storm control."""
    if not args:
        print(f"storm_mode: {base._storm_mode}")
        return
    if args[0] == "start":
        base.env.storm_until_sol = base.comms.clock.sol() + 5
        base._storm_mode = True
        print("[ENV] storm manually started (5 sols)")
    elif args[0] == "end":
        base.env.storm_until_sol = -1
        base._storm_mode = False
        base.env.opacity_tau = 0.3
        print("[ENV] storm ended")


def cmd_samples(base, args):
    """samples [<id>]  -- list samples or show custody trail."""
    if args:
        s = base.samples.samples.get(args[0])
        if not s:
            print(f"no sample {args[0]}")
            return
        s.custody_trail()
        return
    base.samples.summary()


def cmd_collect(base, args):
    """collect <landmark> [science_value]  -- sampler collects a sample."""
    from gnome_rover.samples import try_collect
    if not args:
        print("usage: collect <landmark> [value]")
        return
    lname = args[0]
    val = float(args[1]) if len(args) > 1 else 0.5
    sampler = base.drones["Sampler-1"]
    if sampler.status == "stowed":
        print("[SAMPLER] deploy the sampler first: deploy sampler <x> <y>")
        return
    s = try_collect(base.samples, sampler, lname, val, base)
    if s:
        print(f"[COLLECT] {s.id} {s.mass_g:.0f}g  "
              f"payload now {sampler.payload_mass():.0f}/{sampler.payload_capacity:.0f}g")


def cmd_cache(base, args):
    """cache <sample_id> <depot_name>  -- drop a sample at a depot."""
    from gnome_rover.samples import SampleState
    if len(args) != 2:
        print("usage: cache <sample_id> <depot_name>")
        return
    sid, dname = args[0], args[1]
    d = base.infra.items.get(dname)
    if not d or d.kind != "depot":
        print(f"no depot named {dname}")
        return
    s = base.samples.samples.get(sid)
    if not s:
        print(f"no sample {sid}")
        return
    base.samples.transfer(sid, dname, d.x, d.y, SampleState.CACHED,
                          note=f"cached at {dname}")


def cmd_isru(base, args):
    """isru  -- show ISRU state for all colonies."""
    base.isru.report()


def cmd_spawn(base, args):
    """spawn <colony_name>  -- force a colony to spawn a child."""
    if not args:
        print("usage: spawn <colony_name>")
        return
    base.isru.spawn_child(args[0])


def cmd_attach_isru(base, args):
    """attach-isru <colony_name>  -- register a colony with the ISRU engine."""
    if not args:
        print("usage: attach-isru <colony_name>")
        return
    base.isru.attach(args[0])
    print(f"[ISRU] attached {args[0]}")


def cmd_isru_fill(base, args):
    """isru-fill <colony_name>  -- cheat: fill O2/H2 tanks for testing spawn."""
    if not args:
        print("usage: isru-fill <colony_name>")
        return
    st = base.isru.states.get(args[0])
    if not st:
        print(f"no state for {args[0]} (use attach-isru)")
        return
    st.o2_kg = 80.0
    st.h2_kg = 10.0
    st.power_net_kwh = 5.0
    # force stage to factory
    colony = base.drones.get(args[0])
    if colony:
        colony.stage = 5
    print(f"[ISRU] {args[0]} loaded: O2=80kg H2=10kg stage=FACTORY")


def cmd_plugins(base, args):
    """plugins [scan]  -- list available plugin modules."""
    from gnome_rover.plugins import PluginLoader, DEFAULT_PLUGIN_DIR
    if not hasattr(base, "_plugins"):
        base._plugins = PluginLoader()
        base._plugins.scan()
    if args and args[0] == "scan":
        base._plugins.scan()
    base._plugins.pretty()


def cmd_plugp(base, args):
    """plugp <ModuleName>  -- plug a plugin module into the rover."""
    if not args:
        print("usage: plugp <ModuleName>")
        return
    from gnome_rover.plugins import PluginLoader
    if not hasattr(base, "_plugins"):
        base._plugins = PluginLoader()
        base._plugins.scan()
    m = base._plugins.instantiate(args[0])
    if not m:
        print(f"[PLUGINS] no such plugin: {args[0]}")
        return
    ok = base.rover.plug_in(m)
    print(f"[PLUGINS] plugged {args[0]}: {ok}")


def cmd_cfg(base, args):
    """cfg [key]  -- show config values (all or one)."""
    from gnome_rover.config import get_config
    c = get_config()
    if args:
        print(f"{args[0]} = {c.get(args[0])}")
        return
    for k in sorted(c.all().keys()):
        print(f"  {k:<40} {c.get(k)}")


def cmd_cfg_write(base, args):
    """cfg-write  -- write a full example mission.yaml."""
    from gnome_rover.config import get_config
    get_config().write_example()
