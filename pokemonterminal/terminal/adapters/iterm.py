import os
import subprocess

from . import TerminalProvider as _TProv
from ...transaction import AttributeSpec, TargetId


class ItermProvider(_TProv):
    PROVIDER_VERSION = "2"

    # OSA script that will change the terminal background image
    __osa_script_fmt = """tell application "iTerm2"
    \ttell current session of current window
    \t\tset background image to "{}"
    \tend tell
end tell"""

    __session_id_script = """tell application "iTerm2"
    \treturn id of current session of current window
end tell"""

    __read_script = """tell application "iTerm2"
    \treturn (background image of current session of current window) as string
end tell"""

    __clear_script = """tell application "iTerm2"
    \ttell current session of current window
    \t\tset background image to ""
    \tend tell
end tell"""

    def is_compatible() -> bool:
        return "ITERM_PROFILE" in os.environ

    def __run_osascript(stream):
        p = subprocess.Popen(["osascript"], stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE)
        p.stdin.write(stream)
        p.communicate()
        p.stdin.close()

    @staticmethod
    def __run_osascript_checked(source: str) -> str:
        p = subprocess.run(["osascript"], input=source.encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace").strip())
        return p.stdout.decode("utf-8", "replace")

    def change_terminal(path: str):
        stdin = ItermProvider.__osa_script_fmt.format(path)
        ItermProvider.__run_osascript(str.encode(stdin))

    @classmethod
    def attribute_specs(cls):
        return [AttributeSpec("background-image", True, True,
                              "Background image of the current session")]

    @classmethod
    def list_targets(cls):
        """Bind to the current session's id; fall back to the profile name."""
        try:
            session_id = cls.__run_osascript_checked(
                cls.__session_id_script).strip()
        except Exception:
            session_id = "profile:" + os.environ.get("ITERM_PROFILE", "default")
        return [TargetId("iterm-session", session_id)]

    @classmethod
    def read_attribute(cls, target, name):
        picture = cls.__run_osascript_checked(cls.__read_script).strip()
        if picture in ("missing value", ""):
            return None, False
        return picture, True

    @classmethod
    def write_attribute(cls, target, name, value):
        script = cls.__osa_script_fmt.format(
            str(value).replace("\\", "\\\\").replace('"', '\\"'))
        cls.__run_osascript_checked(script)

    @classmethod
    def remove_attribute(cls, target, name):
        cls.__run_osascript_checked(cls.__clear_script)

    def clear():
        stdin = ItermProvider.__osa_script_fmt.format("")
        ItermProvider.__run_osascript(str.encode(stdin))

    def __str__():
        return "iTerm 2"
