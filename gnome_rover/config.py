"""Mission configuration: one file to rule them all.

Loads from ~/GnomeROVER/mission.yaml (or mission.ini fallback).
Falls back to hard-coded defaults if nothing is found.
"""
import os
from pathlib import Path
from typing import Any, Dict


DEFAULT_CONFIG_PATH = Path.home() / "GnomeROVER" / "mission.yaml"

DEFAULTS: Dict[str, Any] = {
    # --- clock ---
    "clock.time_scale": 60.0,
    "clock.landing_lat": 18.4447,
    "clock.landing_lon": 77.4508,
    "clock.landing_name": "Jezero",

    # --- power ---
    "power.low_threshold": 25.0,
    "power.critical_threshold": 10.0,
    "power.charge_exit": 90.0,
    "power.charge_hysteresis": 85.0,
    "power.drain_normal": 0.10,
    "power.drain_conserve": 0.02,
    "power.charge_rate": 0.15,

    # --- mesh ---
    "mesh.default_range_m": 30.0,
    "mesh.repeater_range_m": 50.0,
    "mesh.missing_threshold_s": 15.0,

    # --- comms ---
    "comms.uplink_bandwidth_kbps": 250.0,
    "comms.earth_base_delay_s": 600.0,
    "comms.earth_delay_swing_s": 300.0,

    # --- terrain ---
    "terrain.scenario": "jezero",
    "terrain.seed": 42,
    "terrain.roughness": 0.6,

    # --- site selection ---
    "sites.max_rock_dist": 4.0,
    "sites.min_crevice_dist": 6.0,
    "sites.min_ice_dist": 8.0,
    "sites.max_base_dist": 40.0,
    "sites.ok_threshold": 0.6,

    # --- ISRU ---
    "isru.drill_rate_kg_per_sol": 0.5,
    "isru.extraction_efficiency": 0.6,
    "isru.spawn_o2_required_kg": 50.0,
    "isru.spawn_h2_required_kg": 6.0,
    "isru.spawn_cooldown_sols": 8,
    "isru.spawn_max_distance_m": 25.0,
    "isru.spawn_min_distance_m": 6.0,

    # --- wave1 ---
    "wave1.min_findings": 6,
    "wave1.survey_timeout_s": 120,
    "wave1.survey_min_battery": 40,

    # --- weather ---
    "weather.storm_rate": 0.02,
    "weather.storm_threshold_tau": 2.5,

    # --- persistence ---
    "persist.save_path": "~/GnomeROVER/mission_save.json",
    "persist.autosave_interval_s": 300.0,

    # --- plugins ---
    "plugins.dir": "~/GnomeROVER/plugins",
}


class Config:
    def __init__(self, path: Path = None, **overrides):
        self.path = path or DEFAULT_CONFIG_PATH
        self._data = dict(DEFAULTS)
        self._load_file()
        for k, v in overrides.items():
            self._data[k] = v
        self._overrides = overrides

    def _load_file(self):
        if not self.path.exists():
            return
        text = self.path.read_text()
        if self.path.suffix in (".yaml", ".yml"):
            self._load_yaml(text)
        else:
            self._load_ini(text)

    def _load_yaml(self, text: str):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(text) or {}
            self._flatten_into(data)
        except ImportError:
            # fall back to simple parser
            self._load_ini(text)

    def _load_ini(self, text: str):
        """Very simple parser: 'section.key: value' or 'key: value'."""
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            self._data[key] = self._coerce(val)

    def _flatten_into(self, d: Dict, prefix: str = ""):
        for k, v in d.items():
            full = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
            if isinstance(v, dict):
                self._flatten_into(v, full)
            else:
                self._data[full] = v

    def _coerce(self, val: str):
        v = val.strip()
        if v.lower() in ("true", "yes", "on"):
            return True
        if v.lower() in ("false", "no", "off"):
            return False
        try:
            if "." in v:
                return float(v)
            return int(v)
        except ValueError:
            return v.strip('"\'')

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def all(self):
        return dict(self._data)

    def write_example(self, path: Path = None):
        """Write a fully-populated example config file."""
        path = path or DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# GnomeROVER mission config",
                 "# Generated defaults — edit freely, restart to apply",
                 ""]
        last_section = ""
        for k in sorted(self._data.keys()):
            section = k.split(".", 1)[0]
            if section != last_section:
                lines.append(f"\n# --- {section} ---")
                last_section = section
            v = self._data[k]
            lines.append(f"{k}: {v}")
        path.write_text("\n".join(lines) + "\n")
        print(f"[CONFIG] wrote example to {path}")
        return path


# --- global singleton ---

_GLOBAL: Config = None


def get_config() -> Config:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Config()
    return _GLOBAL


def reset_config(**overrides):
    global _GLOBAL
    _GLOBAL = Config(**overrides)
    return _GLOBAL
