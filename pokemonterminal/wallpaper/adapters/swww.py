from subprocess import run
from shutil import which
from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec, TargetId


class SwwwProvider(_WProv):
    PROVIDER_VERSION = "2"

    __marker = "currently displaying:"

    def change_wallpaper(path: str):
        run(["swww", "img", path], check=True)

    @staticmethod
    def __query():
        p = run(["swww", "query"], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError("swww query failed")
        outputs = {}
        for line in p.stdout.splitlines():
            if ":" not in line:
                continue
            name, rest = line.split(":", 1)
            if SwwwProvider.__marker in rest:
                path = rest.split(SwwwProvider.__marker, 1)[1]
                # strip annotations like ", with ..."
                path = path.split(",", 1)[0].strip()
                outputs[name.strip()] = path
        if not outputs:
            raise RuntimeError("swww reported no outputs")
        return outputs

    def is_compatible() -> bool:
        # check if swww is installed
        if not which("swww"):
            return False

        # check if it's working (i.e. the daemon is running)
        if run(["swww", "query"], capture_output=True).returncode != 0:
            return False

        return True

    @classmethod
    def attribute_specs(cls):
        return [AttributeSpec("image", True, True,
                              "Picture displayed on each output")]

    @classmethod
    def list_targets(cls):
        return [TargetId("output", name)
                for name in cls.__query().keys()]

    @classmethod
    def read_attribute(cls, target, name):
        outputs = cls.__query()
        if target.key not in outputs:
            raise RuntimeError("output {} not found".format(target.key))
        return outputs[target.key], True

    @classmethod
    def write_attribute(cls, target, name, value):
        run(["swww", "img", "--outputs", target.key, value], check=True)

    def __str__():
        return "swww"
