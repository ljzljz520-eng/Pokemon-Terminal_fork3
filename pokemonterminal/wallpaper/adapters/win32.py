import ctypes
import sys

from . import WallpaperProvider as _WProv
from ...transaction import AttributeSpec, TargetId

if sys.platform == "win32":
    import winreg


class Win32Provider(_WProv):
    PROVIDER_VERSION = "2"

    __SPI_SETDESKWALLPAPER = 20
    __reg_subkey = r"Control Panel\Desktop"
    # restore order matters: style/tile first, picture SPI last applies them
    __keys = (("scaling", "WallpaperStyle"),
              ("tile", "TileWallpaper"),
              ("image", "WallPaper"))

    def change_wallpaper(path: str):
        if not ctypes.windll.user32.SystemParametersInfoW(
                Win32Provider.__SPI_SETDESKWALLPAPER, 0, path, 0):
            raise ctypes.WinError()

    # ------------------------------------------------------------- registry
    @classmethod
    def __read_reg(cls, name: str) -> str:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            cls.__reg_subkey) as key:
            return winreg.QueryValueEx(key, name)[0]

    @classmethod
    def __write_reg(cls, name: str, value) -> None:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.__reg_subkey,
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))

    def is_compatible() -> bool:
        return sys.platform == "win32"

    @classmethod
    def attribute_specs(cls):
        return [
            AttributeSpec("scaling", True, True,
                          "WallpaperStyle (10=fill, 6=sized, 2=stretch...)"),
            AttributeSpec("tile", True, True, "TileWallpaper 0/1"),
            AttributeSpec("image", True, True, "Desktop background picture"),
        ]

    @classmethod
    def list_targets(cls):
        return [TargetId("desktop", "default")]

    @classmethod
    def read_attribute(cls, target, name):
        reg_name = dict(cls.__keys)[name]
        return cls.__read_reg(reg_name), True

    @classmethod
    def write_attribute(cls, target, name, value):
        reg_name = dict(cls.__keys)[name]
        if name == "image":
            cls.__write_reg(reg_name, value)
            if not ctypes.windll.user32.SystemParametersInfoW(
                    cls.__SPI_SETDESKWALLPAPER, 0, str(value), 0):
                raise ctypes.WinError()
        else:
            cls.__write_reg(reg_name, value)

    def __str__():
        return "Windows Desktop"
