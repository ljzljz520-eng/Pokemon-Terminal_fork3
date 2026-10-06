import json
from os import environ
from subprocess import run

from . import TerminalProvider as _TProv
from ...transaction import AttributeSpec, TargetId


class TilixProvider(_TProv):
    PROVIDER_VERSION = "2"

    __setting_key = "com.gexperts.Tilix.Settings"
    __setting_field = "background-image"

    def is_compatible() -> bool:
        return "TILIX_ID" in environ

    def change_terminal(path: str):
        run(["gsettings", "set", TilixProvider.__setting_key,
             TilixProvider.__setting_field, json.dumps(str(path))], check=True)

    @classmethod
    def attribute_specs(cls):
        return [AttributeSpec("background-image", True, True,
                              "Global Tilix background image")]

    @classmethod
    def list_targets(cls):
        return [TargetId("tilix-settings",
                         environ.get("TILIX_ID", "default"))]

    @classmethod
    def read_attribute(cls, target, name):
        p = run(["gsettings", "get", cls.__setting_key,
                 cls.__setting_field], check=True,
                capture_output=True, text=True)
        value = p.stdout.strip()
        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        if value == "":
            return None, False
        return value, True

    @classmethod
    def write_attribute(cls, target, name, value):
        run(["gsettings", "set", cls.__setting_key,
             cls.__setting_field, json.dumps(str(value))], check=True)

    @classmethod
    def remove_attribute(cls, target, name):
        run(["gsettings", "reset", cls.__setting_key,
             cls.__setting_field], check=True)

    def clear():
        run(["gsettings", "reset", TilixProvider.__setting_key,
             TilixProvider.__setting_field], check=True)

    def __str__():
        return "Tilix"
