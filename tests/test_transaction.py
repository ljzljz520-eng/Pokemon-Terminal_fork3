#!/usr/bin/env python3

# To run the tests, use: python3 -m pytest tests/test_transaction.py

import pytest

from pokemonterminal.transaction import (
    AttributeSpec,
    CAPTURED,
    CONFLICT,
    IDENTITY_MISMATCH,
    IRREVERSIBLE,
    MISSING_TARGET,
    NOT_WRITABLE,
    RESTORED,
    TargetId,
    Transaction,
    recover,
    restore_all,
)


class FakeProvider:
    """In-memory transactional provider used to exercise the framework."""
    PROVIDER_VERSION = "fake-1"
    PRIMARY_ATTRIBUTE = "image"

    # mutated by fixtures/tests
    state = {}
    live_targets = []
    specs = []
    identity = "fake-identity"
    compatible = True
    bad_value = False

    @classmethod
    def provider_version(cls):
        return cls.PROVIDER_VERSION

    @classmethod
    def transaction_identity(cls):
        return cls.identity

    @classmethod
    def attribute_specs(cls):
        return cls.specs

    @classmethod
    def list_targets(cls):
        return [TargetId("fake", key) for key in cls.live_targets]

    @classmethod
    def read_version(cls, target):
        return None

    @classmethod
    def read_attribute(cls, target, name):
        if cls.bad_value:
            return object(), True
        return cls.state[target.key][name], True

    @classmethod
    def write_attribute(cls, target, name, value):
        cls.state.setdefault(target.key, {})[name] = value

    @classmethod
    def remove_attribute(cls, target, name):
        cls.state.get(target.key, {}).pop(name, None)

    @classmethod
    def is_compatible(cls):
        return cls.compatible


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("POKEMON_TERMINAL_STATE_DIR", str(tmp_path))
    FakeProvider.state = {
        "a": {"image": "/orig/a.jpg", "note": "alpha"},
        "b": {"image": "/orig/b.jpg", "note": "bravo"},
    }
    FakeProvider.live_targets = ["a", "b"]
    FakeProvider.specs = [
        AttributeSpec("image", True, True, "background picture"),
        AttributeSpec("note", True, True, "side setting"),
    ]
    FakeProvider.identity = "fake-identity"
    FakeProvider.compatible = True
    FakeProvider.bad_value = False
    yield FakeProvider


def _status_map(report):
    return {(r.target, r.attribute): r.status for r in report.results}


def test_capture_apply_restore_roundtrip(fake):
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    assert fake.state["a"]["image"] == "/new/pikachu.jpg"
    assert fake.state["a"]["note"] == "alpha"  # untouched setting

    report = tx.restore("exit")
    statuses = _status_map(report)
    assert set(statuses.values()) == {RESTORED}
    assert len(statuses) == 4

    assert fake.state["a"]["image"] == "/orig/a.jpg"
    assert fake.state["b"]["image"] == "/orig/b.jpg"
    assert fake.state["a"]["note"] == "alpha"
    assert not tx.path.exists()  # settled transaction file removed


def test_unreadable_attribute_is_irreversible(fake):
    fake.specs = [AttributeSpec("image", readable=False, writable=True)]
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    report = tx.restore("exit")
    assert all(r.status == IRREVERSIBLE for r in report.results)
    # Never writes back while pretending success: applied image stays in place.
    assert fake.state["a"]["image"] == "/new/pikachu.jpg"
    assert fake.state["b"]["image"] == "/new/pikachu.jpg"
    assert not tx.path.exists()


def test_external_change_reports_conflict_and_preserves(fake):
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    # User actively picks their own picture on target "a" mid-session.
    fake.state["a"]["image"] = "/user/own-choice.jpg"

    report = tx.restore("clear")
    statuses = _status_map(report)
    assert statuses[("fake:a", "image")] == CONFLICT
    assert statuses[("fake:b", "image")] == RESTORED
    assert fake.state["a"]["image"] == "/user/own-choice.jpg"
    assert fake.state["b"]["image"] == "/orig/b.jpg"


def test_side_setting_change_also_detected(fake):
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    fake.state["b"]["note"] = "user-edited-note"

    report = tx.restore("exit")
    statuses = _status_map(report)
    assert statuses[("fake:b", "note")] == CONFLICT
    assert fake.state["b"]["note"] == "user-edited-note"


def test_missing_target_is_reported(fake):
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    fake.live_targets = ["b"]  # target a disconnected/closed

    report = tx.restore("exit")
    statuses = _status_map(report)
    assert statuses[("fake:a", "image")] == MISSING_TARGET
    assert statuses[("fake:a", "note")] == MISSING_TARGET
    assert statuses[("fake:b", "image")] == RESTORED


def test_identity_mismatch_blocks_and_keeps_file(fake):
    tx = Transaction.capture(fake, "terminal")
    fake.identity = "a-different-display"

    reports = restore_all("terminal")
    assert len(reports) == 1
    assert any(r.status == IDENTITY_MISMATCH for r in reports[0].results)
    # Not settled: state kept so it can be restored in the right environment.
    assert tx.path.exists()


def test_provider_unavailable_keeps_file(fake):
    tx = Transaction.capture(fake, "terminal")
    fake.compatible = False

    report = tx.restore("exit")
    assert not report.settled
    assert tx.path.exists()


def test_read_only_attribute_not_writable(fake):
    fake.specs = [
        AttributeSpec("image", True, True),
        AttributeSpec("note", True, False),
    ]
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    report = tx.restore("exit")
    statuses = _status_map(report)
    assert statuses[("fake:a", "note")] == NOT_WRITABLE
    assert statuses[("fake:b", "note")] == NOT_WRITABLE
    assert statuses[("fake:a", "image")] == RESTORED


def test_unreadable_value_due_to_bad_type(fake):
    fake.bad_value = True
    tx = Transaction.capture(fake, "terminal")

    snaps = {s.key: s for s in tx.targets}
    for target in ("a", "b"):
        attr = snaps[target].attributes["image"]
        assert attr.status == "unreadable"
        assert attr.error
        assert not attr.reversible


def test_lease_expiry_recovers_only_stale(fake):
    tx = Transaction.capture(fake, "terminal", lease_seconds=100)
    tx.apply("/new/pikachu.jpg")

    assert recover() == []  # lease still valid

    tx.lease_expires_at = 0  # simulate crashed owner, stale lease
    tx.save()

    reports = recover()
    assert len(reports) == 1
    assert reports[0].reason == "lease-expired"
    assert fake.state["a"]["image"] == "/orig/a.jpg"
    assert not tx.path.exists()


def test_ownerless_transaction_not_auto_recovered(fake):
    # Single-shot applies have no lease: they wait for an explicit clear.
    tx = Transaction.capture(fake, "terminal")
    tx.apply("/new/pikachu.jpg")

    assert recover() == []
    assert tx.path.exists()

    reports = restore_all("terminal")
    assert len(reports) == 1
    assert fake.state["a"]["image"] == "/orig/a.jpg"


def test_persistence_roundtrip(fake):
    tx = Transaction.capture(fake, "wallpaper", lease_seconds=42)
    tx.apply("/new/pikachu.jpg")

    loaded = Transaction.load(tx.path)
    assert loaded.to_json() == tx.to_json()
    assert loaded.domain == "wallpaper"
    assert loaded.provider_version == "fake-1"
    assert loaded.lease_expires_at is not None


def test_renew_lease_postpones_expiry(fake):
    tx = Transaction.capture(fake, "terminal", lease_seconds=10)
    first = tx.lease_expires_at
    tx.renew_lease()
    assert tx.lease_expires_at >= first
