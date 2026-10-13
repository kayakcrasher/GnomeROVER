"""Sol rollover: daily reports, mission log, milestone tracking."""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from .quiet import say


MISSION_LOG_PATH = Path.home() / "GnomeROVER" / "mission_log.json"


class SolOps:
    def __init__(self, base):
        self.base = base
        self.current_sol = base.comms.clock.sol()
        self.sols: List[dict] = []
        self.milestones: List[tuple] = []   # (sol, text)
        self._known_milestones = set()

    # --- rollover detection ---

    def tick(self):
        sol_now = self.base.comms.clock.sol()
        if sol_now > self.current_sol:
            # one or more sols passed
            for s in range(self.current_sol + 1, sol_now + 1):
                self._snapshot_and_report(s)
            self.current_sol = sol_now

    def _snapshot_and_report(self, sol: int):
        snap = self._snapshot(sol)
        self.sols.append(snap)
        self._print_report(snap)
        self._save()

    # --- snapshot ---

    def _snapshot(self, sol: int) -> dict:
        b = self.base
        kinds = {}
        for lm in b.world.landmarks.values():
            kinds[lm.kind] = kinds.get(lm.kind, 0) + 1

        top_science = None
        try:
            from .science import ScienceEvaluator
            ev = ScienceEvaluator(b.world, b.roads)
            best = ev.best()
            if best:
                top_science = {"name": best.landmark, "score": best.total}
        except Exception:
            pass

        roads = b.roads.roads
        total_road_m = sum(r.length() for r in roads.values())

        drones_deployed = sum(
            1 for d in b.drones.values() if d.status != "stowed")

        return {
            "sol": sol,
            "t": time.time(),
            "mst": self._hms(),
            "landmarks": len(b.world.landmarks),
            "kinds": kinds,
            "roads": len(roads),
            "road_m": round(total_road_m, 2),
            "drones_deployed": drones_deployed,
            "infra": len(b.infra.items),
            "uplink_kb": round(b.comms.uplink.total_sent_kb, 2),
            "top_science": top_science,
            "milestones": [m[1] for m in self.milestones[-5:]],
        }

    def _hms(self):
        h, m, s = self.base.comms.clock.hms()
        return f"{h:02d}:{m:02d}:{s:02d}"

    # --- milestones ---

    def check_milestones(self):
        b = self.base
        checks = [
            ("roads", len(b.roads.roads) >= 1, "first road built"),
            ("roads_5", len(b.roads.roads) >= 5, "5 roads connected"),
            ("roads_10", len(b.roads.roads) >= 10, "10 roads connected"),
            ("colony", any(d.role == "colony" and d.status == "deployed"
                           for d in b.drones.values()), "first colony seed anchored"),
            ("weather", any(it.kind == "weather" for it in b.infra.items.values()),
             "weather station online"),
            ("repeater", any(it.kind == "repeater" for it in b.infra.items.values()),
             "radio repeater online"),
            ("landmarks_10", len(b.world.landmarks) >= 10, "10 landmarks logged"),
            ("landmarks_25", len(b.world.landmarks) >= 25, "25 landmarks logged"),
            ("landmarks_50", len(b.world.landmarks) >= 50, "50 landmarks logged"),
            ("uplink_1mb", b.comms.uplink.total_sent_kb >= 1024, "1 MB sent to Earth"),
        ]
        sol = b.comms.clock.sol()
        for key, cond, text in checks:
            if cond and key not in self._known_milestones:
                self._known_milestones.add(key)
                self.milestones.append((sol, text))
                say(f"[SOLOPS] MILESTONE Sol {sol}: {text}")

    # --- reporting ---

    def _print_report(self, snap: dict):
        lines = []
        lines.append("")
        lines.append(f"════════ SOL {snap['sol']} REPORT ════════")
        lines.append(f"  mission time: {snap['sol']} sols, {snap['mst']} MST")
        lines.append(f"  earth delay: "
                     f"{self.base.comms.earth.one_way_delay_s()/60:.1f} min")
        lines.append("")
        lines.append("  SCIENCE")
        lines.append(f"    landmarks: {snap['landmarks']}")
        for k, v in sorted(snap["kinds"].items(), key=lambda x: -x[1]):
            lines.append(f"      {k:<14} {v}")
        if snap["top_science"]:
            lines.append(f"    top find: {snap['top_science']['name']} "
                         f"@ {snap['top_science']['score']}")
        lines.append("")
        lines.append("  INFRASTRUCTURE")
        lines.append(f"    roads: {snap['roads']}, {snap['road_m']}m total")
        lines.append(f"    drones deployed: {snap['drones_deployed']}/4")
        lines.append(f"    infra items: {snap['infra']}")
        lines.append(f"    uplink sent: {snap['uplink_kb']} KB")
        if snap["milestones"]:
            lines.append("")
            lines.append("  RECENT MILESTONES")
            for m in snap["milestones"]:
                lines.append(f"    - {m}")
        lines.append("")
        for line in lines:
            print(line)

    def print_current(self):
        snap = self._snapshot(self.current_sol)
        self._print_report(snap)

    def print_history(self, n: int = 10):
        if not self.sols:
            print("[SOLOPS] no completed sols yet")
            return
        print(f"=== SOL HISTORY (last {min(n, len(self.sols))}) ===")
        for s in self.sols[-n:]:
            print(f"  Sol {s['sol']:>4}  lm={s['landmarks']:>3}  "
                  f"roads={s['roads']}  kb={s['uplink_kb']:>7.1f}")

    # --- persistence ---

    def _save(self):
        MISSION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sols": self.sols,
            "milestones": [{"sol": s, "text": t} for s, t in self.milestones],
        }
        MISSION_LOG_PATH.write_text(json.dumps(data, indent=2))

    def load(self):
        if not MISSION_LOG_PATH.exists():
            return False
        try:
            data = json.loads(MISSION_LOG_PATH.read_text())
            self.sols = data.get("sols", [])
            self.milestones = [(m["sol"], m["text"])
                               for m in data.get("milestones", [])]
            print(f"[SOLOPS] loaded {len(self.sols)} sol(s) from log")
            return True
        except Exception as e:
            print(f"[SOLOPS] load failed: {e}")
            return False
