from abc import ABC, abstractmethod

from pokemonterminal.transaction import (
    AttributeReadError,
    AttributeSpec,
    AttributeWriteError,
    TargetId,
    default_transaction_identity,
)

class TerminalProvider(ABC):
    """
    Interface representing all the different terminal emulators supported
    by pokemon-terminal if you want to implement a TE, create a module in this
    folder that implements this interface, reflection will do the rest.
    """

    #: schema version, bumped when attribute semantics change
    PROVIDER_VERSION = "1"
    #: name of the attribute written by apply()
    PRIMARY_ATTRIBUTE = "background-image"
    #: kind of targets exposed by this provider
    TRANSACTION_KIND = "terminal-session"

    @staticmethod
    @abstractmethod
    def change_terminal(path: str):
        """
        This sets the wallpaper of the corresponding TE of this adapter.
        :param path The full path of the required pokemon image
        """
        pass

    @staticmethod
    @abstractmethod
    def is_compatible() -> bool:
        """
        checks for compatibility
        :return a boolean saying whether or not the current adaptor is
        compatible with the running TE
        """
        pass

    @staticmethod
    @abstractmethod
    def clear():
        """
        Clear the terminal's background image.
        """
        pass

    # --------------------------------------------------- transaction primitives
    @classmethod
    def provider_version(cls) -> str:
        return cls.PROVIDER_VERSION

    @classmethod
    def transaction_identity(cls) -> str:
        """Hash of the environment the snapshots are bound to."""
        return default_transaction_identity(cls.TRANSACTION_KIND)

    @classmethod
    def attribute_specs(cls):
        """
        Attributes offered by the provider. The honest default claims write
        access but no read access: many terminals cannot report their current
        configuration, so capture must mark it irreversible instead of
        pretending the previous state is known.
        """
        return [AttributeSpec(cls.PRIMARY_ATTRIBUTE, readable=False,
                              writable=True,
                              description="Terminal background picture")]

    @classmethod
    def list_targets(cls):
        """Targets (sessions/windows) the provider operates on."""
        return [TargetId(cls.TRANSACTION_KIND, "default")]

    @classmethod
    def read_version(cls, target: TargetId):
        """Opaque revision token of the target state, or None if unknown."""
        return None

    @classmethod
    def read_attribute(cls, target: TargetId, name: str):
        """Read one attribute; raise to signal it is unreadable."""
        raise AttributeReadError(
            "{} cannot read {}: no read API".format(cls.__name__, name))

    @classmethod
    def write_attribute(cls, target: TargetId, name: str, value):
        """Write one attribute."""
        if name == cls.PRIMARY_ATTRIBUTE:
            cls.change_terminal(value)
            return
        raise AttributeWriteError(
            "{} does not support writing {}".format(cls.__name__, name))

    @classmethod
    def remove_attribute(cls, target: TargetId, name: str):
        """Remove an attribute (restore of a setting that was originally unset)."""
        raise AttributeWriteError(
            "{} cannot remove {}".format(cls.__name__, name))
