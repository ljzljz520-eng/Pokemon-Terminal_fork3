import shlex
import subprocess
import sys
from pathlib import Path
from shutil import which

from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec, TargetId


class FehProvider(_WProv):
    PROVIDER_VERSION = "2"

    __compatible_wm = ["I3_PID", "_OPENBOX_PID"]
    __modes = ("bg-center", "bg-fill", "bg-max", "bg-scale", "bg-tile")

    @staticmethod
    def __fehbg_path() -> Path:
        return Path.home() / ".fehbg"

    def change_wallpaper(path: str):
        command = ["feh", "--bg-fill", path]
        if not FehProvider.__fehbg_path().is_file():
            command.insert(1, "--no-fehbg")
        subprocess.run(command, check=True)

    @classmethod
    def __parse_fehbg(cls):
        """
        ~/.fehbg is a shell script holding the exact previous feh invocation,
        including multi-head (xinerama) image lists and placement mode.
        """
        path = cls.__fehbg_path()
        if not path.is_file():
            raise RuntimeError("~/.fehbg does not exist")
        mode = None
        images = []
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            for token in tokens:
                if token in ("feh", "/usr/bin/feh", "/bin/feh"):
                    continue
                if token in ("--no-fehbg", "--no-xinerama"):
                    continue
                if token in ("--" + m for m in cls.__modes):
                    mode = token[2:]  # strip "--"
                    continue
                if token.startswith("-"):
                    continue
                images.append(token)
        if not images:
            raise RuntimeError("no images found in ~/.fehbg")
        return {"mode": mode or "bg-fill", "images": images}

    def __get_root_props() -> str:
        return subprocess.check_output(["xprop", "-root", "-notype"]).decode(sys.stdout.encoding)

    def is_compatible() -> bool:
        tools_are_available = which("feh") is not None and which("xprop") is not None
        if tools_are_available:
            root_props = FehProvider.__get_root_props()
            return any(wm_signature in root_props for wm_signature in FehProvider.__compatible_wm)
        else:
            return False

    @classmethod
    def attribute_specs(cls):
        return [AttributeSpec(
            "image", True, True,
            "Previous feh picture(s) and placement mode from ~/.fehbg")]

    @classmethod
    def list_targets(cls):
        return [TargetId("x-root", "default")]

    @classmethod
    def read_version(cls, target):
        path = cls.__fehbg_path()
        if not path.is_file():
            return None
        stat = path.stat()
        return "{}:{}".format(stat.st_mtime_ns, stat.st_size)

    @classmethod
    def read_attribute(cls, target, name):
        parsed = cls.__parse_fehbg()
        return parsed, True

    @classmethod
    def write_attribute(cls, target, name, value):
        images = value["images"] if isinstance(value, dict) else [value]
        mode = value.get("mode", "bg-fill") if isinstance(value, dict) else "bg-fill"
        command = ["feh", "--" + mode, *images]
        if not cls.__fehbg_path().is_file():
            command.insert(1, "--no-fehbg")
        subprocess.run(command, check=True)

    def __str__():
        return "feh wallpaper tool"
