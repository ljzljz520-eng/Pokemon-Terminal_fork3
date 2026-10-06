import json
from os import environ
from subprocess import run
from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec, TargetId


class SwayProvider(_WProv):
    PROVIDER_VERSION = "2"

    def change_wallpaper(path: str):
        run(["swaymsg", f"output * background {path} fill"], check=True)

    @staticmethod
    def __outputs():
        p = run(["swaymsg", "-t", "get_outputs"], check=True,
                capture_output=True, text=True)
        data = json.loads(p.stdout)
        names = [o["name"] for o in data if o.get("active")]
        if not names:
            raise RuntimeError("no active sway outputs")
        return names

    def is_compatible() -> bool:
        return "sway" in environ.get("DESKTOP_SESSION", default='').lower()

    @classmethod
    def attribute_specs(cls):
        # swaymsg cannot report a previously set background: irreversible.
        return [AttributeSpec("image", readable=False, writable=True,
                              description="Background picture of each output")]

    @classmethod
    def list_targets(cls):
        return [TargetId("output", name) for name in cls.__outputs()]

    @classmethod
    def write_attribute(cls, target, name, value):
        run(["swaymsg",
             f"output {target.key} background {value} fill"], check=True)

    def __str__():
        return "sway"
