import subprocess as _sp
import sys

from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec, TargetId


class DarwinProvider(_WProv):
    PROVIDER_VERSION = "2"

    __osa_script_fmt = """tell application "System Events"
    \ttell current desktop
    \t\tset picture to "{}"
    \tend tell
end tell"""

    # Enumerate every desktop (one per display) and read its picture.
    __read_script = """tell application "System Events"
    \tset output to ""
    \trepeat with i from 1 to (count of desktops)
    \t\tset output to output & ((i as string) & tab & ((picture of desktop i) as string) & linefeed)
    \tend repeat
    \treturn output
end tell"""

    __read_current_script = """tell application "System Events"
    \treturn (picture of current desktop) as string
end tell"""

    __set_one_fmt = """tell application "System Events"
    \tset picture of desktop {} to "{}"
end tell"""

    __clear_one_fmt = """tell application "System Events"
    \tset picture of desktop {} to missing value
end tell"""

    __clear_current_script = """tell application "System Events"
    \ttell current desktop
    \t\tset picture to missing value
    \tend tell
end tell"""

    def __run_osascript(stream):
        p = _sp.Popen(["osascript"], stdout=_sp.PIPE,
                      stdin=_sp.PIPE)
        p.stdin.write(stream)
        p.communicate()
        p.stdin.close()

    @staticmethod
    def __run_osascript_checked(source: str) -> str:
        p = _sp.run(["osascript"], input=source.encode("utf-8"),
                    stdout=_sp.PIPE, stderr=_sp.PIPE)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace").strip())
        return p.stdout.decode("utf-8", "replace")

    @classmethod
    def __read_desktops(cls):
        out = cls.__run_osascript_checked(cls.__read_script)
        rows = []
        for line in out.splitlines():
            line = line.strip()
            if not line or "\t" not in line:
                continue
            index, picture = line.split("\t", 1)
            if index.isdigit():
                rows.append((index, picture.strip()))
        if not rows:
            raise RuntimeError("no desktops reported")
        return rows

    def change_wallpaper(path: str):
        script = DarwinProvider.__osa_script_fmt.format(path)
        DarwinProvider.__run_osascript(str.encode(script))

    @classmethod
    def attribute_specs(cls):
        return [AttributeSpec("image", True, True,
                              "Background picture of each desktop/display")]

    @classmethod
    def list_targets(cls):
        """
        Enumerate per-display desktops when System Events allows it; otherwise
        fall back to the single 'current desktop' target. Reads on the fallback
        target may still fail and will be reported as unreadable/irreversible.
        """
        try:
            rows = cls.__read_desktops()
        except Exception:
            return [TargetId("desktop", "default")]
        return [TargetId("desktop", index) for index, _ in rows]

    @classmethod
    def read_attribute(cls, target, name):
        if target.key == "default":
            picture = cls.__run_osascript_checked(
                cls.__read_current_script).strip()
        else:
            picture = None
            for index, value in cls.__read_desktops():
                if index == target.key:
                    picture = value
                    break
            if picture is None:
                raise RuntimeError("desktop {} not found".format(target.key))
        if picture == "missing value":
            return None, False
        return picture, True

    @classmethod
    def write_attribute(cls, target, name, value):
        if target.key == "default":
            cls.change_wallpaper(value)
            return
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        cls.__run_osascript_checked(
            cls.__set_one_fmt.format(target.key, escaped))

    @classmethod
    def remove_attribute(cls, target, name):
        if target.key == "default":
            cls.__run_osascript_checked(cls.__clear_current_script)
        else:
            cls.__run_osascript_checked(
                cls.__clear_one_fmt.format(target.key))

    def is_compatible() -> bool:
        return sys.platform == "darwin"

    def __str__():
        return "MacOS Desktop Environment"
