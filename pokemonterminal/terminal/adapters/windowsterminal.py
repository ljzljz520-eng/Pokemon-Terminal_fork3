import json
import os
import re
from pathlib import Path

from . import TerminalProvider as _TProv
from ...transaction import AttributeSpec, TargetId

class WindowsTerminalProvider(_TProv):
    PROVIDER_VERSION = "2"

    __attribute_names = (
        "backgroundImage",
        "backgroundImageOpacity",
        "backgroundImageStretchMode",
        "backgroundImageAlignment",
    )

    def set_background_image(path: str):
        if path is None:
            WindowsTerminalProvider._update({"backgroundImage": (None, False)})
        else:
            WindowsTerminalProvider._update({"backgroundImage": (path, True)})

    @staticmethod
    def settings_path() -> Path:
        return Path(os.environ['LOCALAPPDATA']) / 'Packages' / \
            'Microsoft.WindowsTerminal_8wekyb3d8bbwe' / 'LocalState' / \
            'settings.json'

    @classmethod
    def _load(cls):
        text = cls.settings_path().read_text(encoding='utf8')
        # comments are stripped before json parsing
        return json.loads(cls.comment_remover(text))

    @classmethod
    def _defaults(cls, data):
        profiles = data.setdefault('profiles', {})
        if isinstance(profiles, list):
            data['profiles'] = profiles = {
                'defaults': {},
                'list': profiles,
            }
        defaults = profiles.setdefault('defaults', {})
        if not isinstance(defaults, dict):
            defaults = profiles['defaults'] = {}
        return defaults

    @classmethod
    def _update(cls, changes):
        path = cls.settings_path()
        data = cls._load()
        defaults = cls._defaults(data)
        for name, (value, present) in changes.items():
            if present:
                defaults[name] = value
            else:
                defaults.pop(name, None)
        # loses original indentation and comments (same as before)
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                        encoding='utf8')

    def comment_remover(text: str) -> str:
        def replacer(match: re.Match):
            s = match.group(0)
            if s.startswith('/'):
                return " " # note: a space and not an empty string
            else:
                return s
        pattern = re.compile(
            r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
            re.DOTALL | re.MULTILINE
        )
        return re.sub(pattern, replacer, text)

    def is_compatible() -> bool:
        return "WT_SESSION" in os.environ

    @classmethod
    def attribute_specs(cls):
        return [
            AttributeSpec("backgroundImage", True, True,
                          "Background image path"),
            AttributeSpec("backgroundImageOpacity", True, True,
                          "Image opacity 0.0-1.0"),
            AttributeSpec("backgroundImageStretchMode", True, True,
                          "none/fill/uniform/uniformToFill"),
            AttributeSpec("backgroundImageAlignment", True, True,
                          "center/left/right/top/bottom/..."),
        ]

    @classmethod
    def list_targets(cls):
        return [TargetId("wt-profile", "defaults")]

    @classmethod
    def read_version(cls, target):
        stat = cls.settings_path().stat()
        return "{}:{}".format(stat.st_mtime_ns, stat.st_size)

    @classmethod
    def read_attribute(cls, target, name):
        defaults = cls._defaults(cls._load())
        return defaults.get(name), name in defaults

    @classmethod
    def write_attribute(cls, target, name, value):
        cls._update({name: (value, True)})

    @classmethod
    def remove_attribute(cls, target, name):
        cls._update({name: (None, False)})

    def change_terminal(path: str):
        WindowsTerminalProvider.set_background_image(path)

    def clear():
        WindowsTerminalProvider.set_background_image(None)

    def __str__():
        return "Windows Terminal"
