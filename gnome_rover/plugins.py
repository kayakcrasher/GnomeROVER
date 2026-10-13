"""Plugin loader: auto-discover RoverModule subclasses from a directory."""
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, Type, List
from .modules import RoverModule


DEFAULT_PLUGIN_DIR = Path.home() / "GnomeROVER" / "plugins"


class PluginLoader:
    def __init__(self, plugin_dir: Path = DEFAULT_PLUGIN_DIR):
        self.plugin_dir = plugin_dir
        self.registry: Dict[str, Type[RoverModule]] = {}
        self.errors: List[str] = []

    def scan(self) -> Dict[str, Type[RoverModule]]:
        """Find all *.py files in the plugin dir, load their RoverModule subclasses."""
        self.registry.clear()
        self.errors.clear()
        if not self.plugin_dir.exists():
            return self.registry
        for py in sorted(self.plugin_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            self._load_one(py)
        return self.registry

    def _load_one(self, path: Path):
        try:
            mod_name = f"gnome_plugin_{path.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                self.errors.append(f"{path.name}: bad spec")
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            found = 0
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if (issubclass(obj, RoverModule)
                        and obj is not RoverModule
                        and obj.__module__ == mod.__name__):
                    self.registry[name] = obj
                    found += 1
            if found == 0:
                self.errors.append(f"{path.name}: no RoverModule subclasses found")
        except Exception as e:
            self.errors.append(f"{path.name}: {type(e).__name__}: {e}")

    def instantiate(self, name: str):
        cls = self.registry.get(name)
        if not cls:
            return None
        try:
            return cls()
        except TypeError:
            # constructor may need a name arg
            try:
                return cls(name.lower())
            except Exception as e:
                self.errors.append(f"instantiate {name}: {e}")
                return None
        except Exception as e:
            self.errors.append(f"instantiate {name}: {e}")
            return None

    def pretty(self):
        if not self.registry:
            print(f"[PLUGINS] no plugins found in {self.plugin_dir}")
        else:
            print(f"[PLUGINS] {len(self.registry)} available in {self.plugin_dir}:")
            for name in sorted(self.registry.keys()):
                print(f"  {name}")
        if self.errors:
            print("[PLUGINS] errors:")
            for e in self.errors:
                print(f"  {e}")


# --- example plugin ---

EXAMPLE_PLUGIN = '''"""Example plugin: a simple beacon that reports position periodically."""
from gnome_rover.modules import RoverModule


class BeaconModule(RoverModule):
    def __init__(self):
        super().__init__("Beacon")
        self.pulses = 0

    def update(self, dt: float):
        if self.enabled:
            self.pulses += 1
            self._data = {"pulses": self.pulses}
'''


def write_example_plugin(plugin_dir: Path = DEFAULT_PLUGIN_DIR) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    p = plugin_dir / "beacon.py"
    p.write_text(EXAMPLE_PLUGIN)
    print(f"[PLUGINS] wrote example plugin to {p}")
    return p
