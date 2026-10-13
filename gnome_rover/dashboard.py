"""Curses live dashboard for GnomeROVER."""
import curses
import time
from typing import Optional


def _fmt_drone(d, width=34):
    bat = d.battery
    mode = d.mode.value if hasattr(d.mode, "value") else str(d.mode)
    status = d.status
    line = f"{d.name:<11} bat={bat:>5.1f}% [{status}]"
    return line[:width]


def _fmt_infra(it, width=34):
    line = f"{it.name:<12} {it.kind:<10} bat={it.battery:>5.1f}%"
    return line[:width]


def _fmt_comms(base, width=40):
    q = base.comms.uplink
    lines = []
    lines.append(f"queue: {len(q.items)} item(s)  {q.pending_kb():.1f} KB")
    if base.comms.uplink.sent_history:
        lines.append(f"total sent: {q.total_sent_kb:.1f} KB")
    oh = [o for o in base.comms.orbiters if o.is_overhead(base.comms.clock)]
    if oh:
        lines.append(f"OVERHEAD: {', '.join(o.name for o in oh)}")
    else:
        nxt = min(base.comms.orbiters,
                  key=lambda o: o.next_pass_in_s(base.comms.clock))
        lines.append(f"next pass: {nxt.name} in "
                     f"{nxt.next_pass_in_hms(base.comms.clock)}")
    lines.append(f"Earth: {base.comms.earth.one_way_delay_s()/60:.1f} min one-way")
    return [l[:width] for l in lines]


def _fmt_mesh(base, width=34):
    mesh = getattr(base, "mesh", None)
    if not mesh:
        return ["no mesh router"]
    s = mesh.stats()
    return [
        f"nodes: {s['nodes']}",
        f"delivered: {s['delivered']}",
        f"dropped: {s['dropped']}",
        f"missing: {', '.join(s['missing']) if s['missing'] else '--'}",
    ]


def _fmt_supply(base, width=34):
    roads = base.roads.roads
    total = sum(r.length() for r in roads.values())
    sl = getattr(base, "_supply", None)
    lines = [
        f"roads: {len(roads)}",
        f"total: {total:.1f}m",
    ]
    if sl:
        lines.append(f"connected nodes: {len(sl.connected)}")
    return [l[:width] for l in lines]


def _fmt_science(base, width=34):
    try:
        from gnome_rover.science import ScienceEvaluator
        ev = ScienceEvaluator(base.world, base.roads)
        ranked = ev.rank_all(min_total=0.01)[:5]
        return [f"{sv.landmark:<14} {sv.total:.3f}"[:width] for sv in ranked]
    except Exception as e:
        return [f"err: {e}"[:width]]


def _fmt_log(base, width=50, lines=5):
    out = base.mission_log[-lines:]
    return [l[:width] for l in out]


def _write(stdscr, y, x, text, attr=0):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def run(base, refresh_hz=10.0):
    """Launch the dashboard. Blocks until user quits."""
    def _main(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.clearok(True)
        paused = False

        while True:
            stdscr.clear()
            h, w = stdscr.getmaxyx()

            # header
            hh, mm, ss = base.comms.clock.hms()
            header = (f" GNOME ROVER  |  Sol {base.comms.clock.sol():>4}  "
                      f"{hh:02d}:{mm:02d}:{ss:02d} MST  |  "
                      f"Earth delay {base.comms.earth.one_way_delay_s()/60:>4.1f} min ")
            _write(stdscr, 0, 0, header.ljust(w-1), curses.A_REVERSE)

            # left column
            _write(stdscr, 2, 2, "ROVER", curses.A_BOLD)
            r = base.rover
            _write(stdscr, 3, 4, f"gait: {r.gait.value}")
            _write(stdscr, 4, 4,
                   f"FL: hip={r.legs[list(r.legs)[0]].hip.angle:>6.1f}  "
                   f"sh={r.legs[list(r.legs)[0]].shoulder.angle:>6.1f}  "
                   f"kn={r.legs[list(r.legs)[0]].knee.angle:>6.1f}")
            _write(stdscr, 5, 4, f"loop: {'running' if r.running else 'stopped'}")
            mods = ", ".join(f"{n}({'on' if m.enabled else 'off'})"
                             for n, m in r.modules.items())
            _write(stdscr, 6, 4, mods[:60])

            _write(stdscr, 8, 2, "DRONES", curses.A_BOLD)
            for i, d in enumerate(base.drones.values()):
                _write(stdscr, 9 + i, 4, _fmt_drone(d))

            _write(stdscr, 14, 2, "MESH", curses.A_BOLD)
            for i, line in enumerate(_fmt_mesh(base)):
                _write(stdscr, 15 + i, 4, line)

            _write(stdscr, 20, 2, "SUPPLY LINE", curses.A_BOLD)
            for i, line in enumerate(_fmt_supply(base)):
                _write(stdscr, 21 + i, 4, line)

            # middle column
            mid_x = 42
            _write(stdscr, 2, mid_x, "COMMS", curses.A_BOLD)
            for i, line in enumerate(_fmt_comms(base)):
                _write(stdscr, 3 + i, mid_x + 2, line)

            _write(stdscr, 10, mid_x, "SCIENCE (top)", curses.A_BOLD)
            for i, line in enumerate(_fmt_science(base)):
                _write(stdscr, 11 + i, mid_x + 2, line)

            _write(stdscr, 18, mid_x, "INFRA", curses.A_BOLD)
            for i, it in enumerate(list(base.infra.items.values())[:6]):
                _write(stdscr, 19 + i, mid_x + 2, _fmt_infra(it))

            # right column (log)
            right_x = 82
            if w > right_x + 20:
                _write(stdscr, 2, right_x, "LOG", curses.A_BOLD)
                for i, line in enumerate(_fmt_log(base, lines=h - 8)):
                    _write(stdscr, 3 + i, right_x, line)

            # footer
            footer = " [q]uit  [space]pause  [s]ave  [d]iag  [f]ault  [c]omms "
            if paused:
                footer = " PAUSED " + footer
            _write(stdscr, h - 1, 0, footer.ljust(w-1), curses.A_REVERSE)

            stdscr.refresh()

            # input
            try:
                ch = stdscr.getch()
            except Exception:
                ch = -1
            if ch == ord('q'):
                return
            elif ch == ord(' '):
                paused = not paused
            elif ch == ord('s'):
                try:
                    from gnome_rover.persist import save
                    save(base)
                    base.mission_log.append("[DASH] saved mission")
                except Exception as e:
                    base.mission_log.append(f"[DASH] save failed: {e}")
            elif ch == ord('d'):
                try:
                    from gnome_rover.diagnostics import run_all
                    base.mission_log.append("[DASH] running diag...")
                    run_all(base.rover, base, show_ok=True)
                except Exception as e:
                    base.mission_log.append(f"[DASH] diag failed: {e}")
            elif ch == ord('c'):
                base.comms.status()
            elif ch == ord('f'):
                base.mission_log.append(
                    "[DASH] use 'fault <kind> <target>' from pilot; "
                    "see 'fault list'")
            elif ch == ord('h'):
                base.mission_log.append(
                    "[DASH] q=quit spc=pause s=save d=diag f=fault-info c=comms")
            elif ch == -1:
                pass

            if not paused:
                time.sleep(1.0 / refresh_hz)

    try:
        curses.wrapper(_main)
    except KeyboardInterrupt:
        pass
    print("[DASH] exited")
