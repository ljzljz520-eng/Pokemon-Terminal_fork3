import json
from os import environ
from subprocess import run

from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec


class GnomeProvider(_WProv):
    PROVIDER_VERSION = "2"

    __session_names = ["gnome", "ubuntu"]
    __schema = "org.gnome.desktop.background"

    # attribute -> gsettings key
    __keys = {
        "image": "picture-uri",
        "image-dark": "picture-uri-dark",
        "scaling": "picture-options",
    }

    def change_wallpaper(path: str):
        GnomeProvider.__write_key("picture-uri", "file://{}".format(path))

    @staticmethod
    def __read_key(key: str) -> str:
        p = run(["gsettings", "get", GnomeProvider.__schema, key],
                check=True, capture_output=True, text=True)
        return GnomeProvider.__parse_variant(p.stdout.strip())

    @staticmethod
    def __write_key(key: str, value) -> None:
        # json.dumps gives a valid GVariant literal (quoted strings, booleans)
        run(["gsettings", "set", GnomeProvider.__schema, key,
             json.dumps(value)], check=True)

    @staticmethod
    def __parse_variant(text: str):
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            pass
        if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
            return text[1:-1]
        if text in ("true", "false"):
            return text == "true"
        return text

    def is_compatible() -> bool:
        return environ.get("DESKTOP_SESSION", default='').lower() \
            in GnomeProvider.__session_names

    @classmethod
    def attribute_specs(cls):
        return [
            AttributeSpec("image", True, True,
                          "Picture used in the light color scheme"),
            AttributeSpec("image-dark", True, True,
                          "Picture used in the dark color scheme"),
            AttributeSpec("scaling", True, True,
                          "Placement: zoom, stretch, scaled, none, wallpaper"),
        ]

    @classmethod
    def read_attribute(cls, target, name):
        return cls.__read_key(cls.__keys[name])

    @classmethod
    def write_attribute(cls, target, name, value):
        cls.__write_key(cls.__keys[name], value)

    def __str__():
        return "GNOME Shell Desktop"
