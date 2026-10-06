import atexit
import multiprocessing
import random
import signal
import sys
from threading import Thread, Event

from . import scripter
from .platform import PlatformNamedEvent


def __slideshow_worker(filtered, delay, domain, event_name):
    """
    Runs the slideshow inside a capture/apply/restore transaction.

    Restore happens on the stop event and on SIGTERM/SIGINT; if the process is
    killed outright, the lease (renewed on every apply) eventually expires and
    a later 'recover' or 'clear' performs the restore instead.
    """
    stop_requested = Event()

    def __request_stop(signum=None, frame=None):
        stop_requested.set()

    signal.signal(signal.SIGTERM, __request_stop)
    signal.signal(signal.SIGINT, __request_stop)

    tx = None
    try:
        with PlatformNamedEvent(event_name) as event:
            listener = Thread(target=event.wait, daemon=True)
            listener.start()
            # Lease outlives a few slides, renewing on every apply.
            tx = scripter.begin_transaction(
                domain, lease_seconds=max(60.0, delay * 60 * 3))
            shuffled = filtered[:]
            random.shuffle(shuffled)
            queue = iter(shuffled)
            while not stop_requested.is_set() and listener.is_alive():
                next_pkmn = next(queue, None)
                if next_pkmn is None:
                    random.shuffle(shuffled)
                    queue = iter(shuffled)
                    continue
                tx.apply(next_pkmn.get_path())
                stop_requested.wait(delay * 60)
    except BaseException:
        if tx is not None:
            tx.restore("error")
        raise
    else:
        if tx is not None:
            tx.restore("exit")


def start(filtered, delay, domain, event_name):
    p = multiprocessing.Process(
        target=__slideshow_worker,
        args=(filtered, delay, domain, event_name,),
        daemon=True)
    p.start()
    # HACK remove multiprocessing's exit handler to prevent it killing our child.
    atexit.unregister(multiprocessing.util._exit_function)
    return p.pid


def stop(event_name):
    with PlatformNamedEvent(event_name) as e:
        e.signal()
