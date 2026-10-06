# Used for creating, running and analyzing applescript and bash scripts.
import sys

from . import transaction as _transaction
from .terminal import get_current_terminal_adapters
from .wallpaper import get_current_wallpaper_adapters

TERMINAL_PROVIDER = None
WALLPAPER_PROVIDER = None

_TERMINAL_DOMAIN = "terminal"
_WALLPAPER_DOMAIN = "wallpaper"


def __init_terminal_provider():
    global TERMINAL_PROVIDER
    if TERMINAL_PROVIDER is not None:
        return TERMINAL_PROVIDER
    providers = get_current_terminal_adapters()
    if len(providers) > 1:
        # All this if is really not supposed to happen at all whatsoever
        # really what kind of person has 2 simultaneous T.E???
        print("Multiple providers found, please select the appropriate one.")
        for i, x in enumerate(providers):
            print(f'{i}. {x.__str__()}')
        print("If some of these make no sense or are irrelevant please file " +
              "an issue in https://github.com/LazoCoder/Pokemon-Terminal")
        print("=> ", end='')
        inp = None
        while inp is None:
            try:
                inp = int(input())
                if inp >= len(providers):
                    raise ValueError()
            except ValueError as _:
                print("Invalid number, try again!")
        TERMINAL_PROVIDER = providers[inp]
    elif len(providers) <= 0:
        print("Your terminal emulator isn't supported at this time.")
        sys.exit()
    else:
        TERMINAL_PROVIDER = providers[0]
    return TERMINAL_PROVIDER


def __init_wallpaper_provider():
    global WALLPAPER_PROVIDER
    if WALLPAPER_PROVIDER is not None:
        return WALLPAPER_PROVIDER
    providers = get_current_wallpaper_adapters()
    if len(providers) > 1:
        # All this if is really not supposed to happen at all whatsoever
        # really what kind of person has 2 simultaneous D.E???
        print("Multiple providers found, please select the appropriate one.")
        for i, x in enumerate(providers):
            print(f'{i}. {x.__str__()}')
        print("If some of these make no sense or are irrelevant please file " +
              "an issue in https://github.com/LazoCoder/Pokemon-Terminal")
        print("=> ", end='')
        inp = None
        while inp is None:
            try:
                inp = int(input())
                if inp >= len(providers):
                    raise ValueError()
            except ValueError as _:
                print("Invalid number, try again!")
        WALLPAPER_PROVIDER = providers[inp]
    elif len(providers) <= 0:
        print("Your desktop environment isn't supported at this time.")
        sys.exit()
    else:
        WALLPAPER_PROVIDER = providers[0]
    return WALLPAPER_PROVIDER


def begin_transaction(domain, lease_seconds=None):
    """Capture pre-state of every target and persist the transaction."""
    if domain == _TERMINAL_DOMAIN:
        provider = __init_terminal_provider()
    elif domain == _WALLPAPER_DOMAIN:
        provider = __init_wallpaper_provider()
    else:
        raise ValueError("Unknown domain: {}".format(domain))
    return _transaction.Transaction.capture(
        provider, domain, lease_seconds=lease_seconds)


def _print_reports(reports):
    for report in reports:
        for line in report.summary_lines():
            print(line)


def clear_terminal():
    """
    Restore every tracked terminal transaction (original image/theme). Falls
    back to the legacy image-only clear when nothing is tracked, explicitly
    stating the original state is unknown.
    """
    provider = __init_terminal_provider()
    reports = _transaction.restore_all(_TERMINAL_DOMAIN)
    if reports:
        _print_reports(reports)
    else:
        print("No tracked terminal state; performing legacy image clear "
              "(original configuration unknown, best effort only).")
        provider.clear()


def clear_wallpaper():
    """Restore every tracked wallpaper transaction (original scaling/multi-head)."""
    __init_wallpaper_provider()
    reports = _transaction.restore_all(_WALLPAPER_DOMAIN)
    if reports:
        _print_reports(reports)
    else:
        print("No tracked wallpaper state; nothing to restore.")


def recover():
    """Restore transactions whose lease expired (crashed/killed slideshows)."""
    reports = _transaction.recover()
    if reports:
        _print_reports(reports)
    else:
        print("No expired transactions found.")
    return reports


def change_terminal(image_file_path):
    if not isinstance(image_file_path, str):
        print("A image path must be passed to the change terminal function.")
        return
    tx = begin_transaction(_TERMINAL_DOMAIN)
    tx.apply(image_file_path)


def change_wallpaper(image_file_path):
    if not isinstance(image_file_path, str):
        print("A image path must be passed to the change wallpapper function.")
        return
    tx = begin_transaction(_WALLPAPER_DOMAIN)
    tx.apply(image_file_path)
