import os
from subprocess import CalledProcessError, run

from . import TerminalProvider as _TProv
from ...transaction import AttributeSpec, TargetId

def print_kitty_error(err: CalledProcessError):
    print("Failed to set kitty background. Did you configure"
          " kitty remote control correctly? (See Readme).")
    if msg := err.stderr:
        print(f"Output from kitty: \"{msg.decode().strip()}\".")


class KittyProvider(_TProv):
    def is_compatible() -> bool:
        return "KITTY_WINDOW_ID" in os.environ

    def change_terminal(path: str):
        try:
            run(["kitty", "@", "set-background-image", path], check=True, capture_output=True)
        except CalledProcessError as err:
            print_kitty_error(err)

    @classmethod
    def attribute_specs(cls):
        # kitty remote control offers no way to query the previous image.
        return [AttributeSpec("background-image", readable=False,
                              writable=True,
                              description="Background image of the window")]

    @classmethod
    def list_targets(cls):
        return [TargetId("kitty-window",
                         os.environ.get("KITTY_WINDOW_ID", "default"))]

    @classmethod
    def write_attribute(cls, target, name, value):
        # Unlike change_terminal, transaction writes surface failures so the
        # apply result reports them instead of claiming success.
        run(["kitty", "@", "set-background-image", str(value)],
            check=True, capture_output=True)

    def clear():
        try:
            run(["kitty", "@", "set-background-image", "none"], check=True, capture_output=True)
        except CalledProcessError as err:
            print_kitty_error(err)

    def __str__():
        return "Kitty"
