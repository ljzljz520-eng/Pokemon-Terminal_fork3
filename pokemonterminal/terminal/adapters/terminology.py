import os
from os import environ
from subprocess import run

from . import TerminalProvider as _TProv
from ...transaction import AttributeSpec, TargetId


class TerminologyProvider(_TProv):
    def is_compatible() -> bool:
        return environ.get("TERMINOLOGY") == '1'

    def change_terminal(path: str):
        run(["tybg", path], check=True)

    @classmethod
    def attribute_specs(cls):
        # tybg exposes no way to query the previous background.
        return [AttributeSpec("background-image", readable=False,
                              writable=True,
                              description="Background image of the window")]

    @classmethod
    def list_targets(cls):
        return [TargetId("terminology-window",
                         environ.get("WINDOWID", "default"))]

    def clear():
        run("tybg", check=True)

    def __str__():
        return "Terminology"
