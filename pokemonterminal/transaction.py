"""
State-capture transactions for terminal/background providers.

A Transaction follows capture -> apply -> restore:

* capture: enumerate provider targets (sessions, outputs, monitors) and record
  every attribute's pre-state together with capability flags
  (readable/writable) and a target version token. Attributes the platform
  cannot expose are recorded as UNREADABLE and therefore IRREVERSIBLE --
  restore never pretends it could undo them.
* apply: write the requested image to every target, then re-read all readable
  attributes. The post-apply readings are the baseline of exactly what state
  we left behind.
* restore: replay captured values only onto targets whose identity still
  matches and whose live state still equals our apply baseline. If the user
  (or another program) actively changed a setting while the slideshow ran,
  that attribute is reported as CONFLICT and left untouched.

Transactions are persisted as JSON so that a crashed slideshow process can be
resolved by a later invocation (lease expiry) or an explicit recovery.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_VERSION = 1

# Capture statuses
CAPTURED = "captured"
UNREADABLE = "unreadable"

# Restore result statuses
RESTORED = "restored"
CONFLICT = "conflict"
IRREVERSIBLE = "irreversible"
NOT_WRITABLE = "not-writable"
MISSING_TARGET = "missing-target"
IDENTITY_MISMATCH = "identity-mismatch"
PROVIDER_UNAVAILABLE = "provider-unavailable"
UNTOUCHED = "untouched"
RESTORE_FAILED = "restore-failed"
APPLIED = "applied"
APPLY_FAILED = "apply-failed"

# Restore reasons
REASON_EXIT = "exit"
REASON_ERROR = "error"
REASON_CLEAR = "clear"
REASON_LEASE = "lease-expired"

_MISSING = object()


class TransactionError(Exception):
    """Base class for transaction related errors."""


class AttributeReadError(TransactionError):
    """Raised by providers when an attribute cannot be read."""


class AttributeWriteError(TransactionError):
    """Raised by providers when an attribute cannot be written."""


@dataclass(frozen=True)
class AttributeSpec:
    """Description of an attribute offered (or not) by a provider."""
    name: str
    readable: bool
    writable: bool
    description: str = ""

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "readable": self.readable,
            "writable": self.writable,
            "description": self.description,
        }

    @staticmethod
    def from_json(data: Dict[str, Any]) -> "AttributeSpec":
        return AttributeSpec(data["name"], data["readable"],
                             data["writable"], data.get("description", ""))


@dataclass(frozen=True)
class TargetId:
    """Stable identity of a target (session/output/monitor) within a provider."""
    kind: str
    key: str

    def __str__(self) -> str:
        return "{}:{}".format(self.kind, self.key)


@dataclass(frozen=True)
class CapturedAttribute:
    """The pre-state of one attribute, or an honest record that it is unknown."""
    name: str
    readable: bool
    writable: bool
    status: str
    value: Any = None
    present: bool = True
    error: Optional[str] = None

    @property
    def reversible(self) -> bool:
        """Only values that were successfully read and can be written back."""
        return self.writable and self.status == CAPTURED

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "readable": self.readable,
            "writable": self.writable,
            "status": self.status,
            "value": self.value,
            "present": self.present,
            "error": self.error,
        }

    @staticmethod
    def from_json(data: Dict[str, Any]) -> "CapturedAttribute":
        return CapturedAttribute(
            data["name"], data["readable"], data["writable"], data["status"],
            data.get("value"), data.get("present", True), data.get("error"))


@dataclass
class TargetSnapshot:
    """Pre-state capture of one target."""
    kind: str
    key: str
    version: Optional[str]
    attributes: Dict[str, CapturedAttribute] = field(default_factory=dict)

    @property
    def target_id(self) -> TargetId:
        return TargetId(self.kind, self.key)


@dataclass
class AttributeResult:
    """Outcome of applying to, or restoring one attribute on one target."""
    target: str
    attribute: str
    status: str
    detail: str = ""

    def to_json(self) -> Dict[str, Any]:
        return {"target": self.target, "attribute": self.attribute,
                "status": self.status, "detail": self.detail}

    @staticmethod
    def from_json(data: Dict[str, Any]) -> "AttributeResult":
        return AttributeResult(data["target"], data["attribute"],
                               data["status"], data.get("detail", ""))


@dataclass
class RestoreReport:
    """Aggregated result of restoring one transaction."""
    transaction_id: str
    domain: str
    reason: str
    results: List[AttributeResult] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    @property
    def settled(self) -> bool:
        """True when the report is final (file can be discarded)."""
        blocking = {IDENTITY_MISMATCH, PROVIDER_UNAVAILABLE}
        return all(r.status not in blocking for r in self.results)

    def summary_lines(self) -> List[str]:
        lines = ["Transaction {} restore ({}):".format(
            self.transaction_id, self.reason)]
        counts = self.counts()
        if counts:
            lines.append("  " + ", ".join(
                "{} {}".format(v, k) for k, v in sorted(counts.items())))
        for r in self.results:
            if r.status not in (RESTORED, UNTOUCHED):
                lines.append("  [{}] {} - {}{}".format(
                    r.status, r.target, r.attribute,
                    ": {}".format(r.detail) if r.detail else ""))
        return lines


def state_dir() -> Path:
    """Directory where live transaction files are kept."""
    override = os.environ.get("POKEMON_TERMINAL_STATE_DIR")
    path = Path(override) if override else Path.home() / ".pokemon-terminal" / "transactions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_transaction_identity(kind: str) -> str:
    """
    Build a stable hash of the environment the provider operates on (host,
    display/wayland session, specific terminal session markers). Snapshots are
    bound to this identity so a transaction captured on one display/session is
    never restored onto a different one.
    """
    markers = (
        "DISPLAY", "WAYLAND_DISPLAY", "XAUTHLOCALHOSTNAME", "TERM_PROGRAM",
        "ITERM_PROFILE", "KITTY_WINDOW_ID", "TILIX_ID", "TERMINOLOGY",
        "WT_SESSION", "CONEMUPID",
    )
    parts = [socket.gethostname(), kind, os.environ.get("TERM_SESSION", "")]
    for var in markers:
        value = os.environ.get(var)
        if value:
            parts.append("{}={}".format(var, value))
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _check_json_safe(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _check_json_safe(item)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TransactionError("dict keys must be strings")
            _check_json_safe(v)
        return
    raise TransactionError("value of type {} is not JSON safe".format(
        type(value).__name__))


def _normalize_reading(reading: Any) -> Any:
    """
    A read returns either a plain value, or a (value, present) tuple when the
    underlying setting may exist without a value.
    """
    if isinstance(reading, tuple):
        value, present = reading
        return value, bool(present)
    return reading, True


def _safe_call(func, *args):
    try:
        return func(*args), None
    except Exception as err:  # provider errors are captured, not raised
        return None, "{}: {}".format(type(err).__name__, err)


@dataclass
class Transaction:
    """A capture/apply/restore transaction bound to one provider."""
    domain: str
    provider_module: str
    provider_name: str
    provider_version: str
    identity: str
    targets: List[TargetSnapshot]
    tx_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: float = field(default_factory=time.time)
    lease_seconds: Optional[float] = None
    lease_expires_at: Optional[float] = None
    # target key -> attribute name -> value / present recorded after our apply
    baseline: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    baseline_present: Dict[str, Dict[str, bool]] = field(default_factory=dict)
    baseline_version: Dict[str, Optional[str]] = field(default_factory=dict)
    finished: bool = False
    finish_reason: Optional[str] = None
    last_apply: List[AttributeResult] = field(default_factory=list)

    # ---------------------------------------------------------------- capture
    @classmethod
    def capture(cls, provider, domain: str,
                lease_seconds: Optional[float] = None) -> "Transaction":
        specs = list(provider.attribute_specs())
        if not specs:
            raise TransactionError(
                "{} declares no attributes".format(provider.__name__))
        primary = getattr(provider, "PRIMARY_ATTRIBUTE", None)
        if primary is None or not any(s.name == primary for s in specs):
            raise TransactionError(
                "{} primary attribute {!r} missing from specs".format(
                    provider.__name__, primary))

        targets: List[TargetSnapshot] = []
        for tid in provider.list_targets():
            version, _ = _safe_call(provider.read_version, tid)
            attrs: Dict[str, CapturedAttribute] = {}
            for spec in specs:
                if not spec.readable:
                    attrs[spec.name] = CapturedAttribute(
                        spec.name, spec.readable, spec.writable, UNREADABLE,
                        value=None, present=False,
                        error="provider exposes no read access")
                    continue
                try:
                    value, present = _normalize_reading(
                        provider.read_attribute(tid, spec.name))
                    _check_json_safe(value)
                    attrs[spec.name] = CapturedAttribute(
                        spec.name, True, spec.writable, CAPTURED, value, present)
                except Exception as err:
                    attrs[spec.name] = CapturedAttribute(
                        spec.name, True, spec.writable, UNREADABLE,
                        value=None, present=False,
                        error="{}: {}".format(type(err).__name__, err))
            targets.append(TargetSnapshot(tid.kind, tid.key, version, attrs))

        tx = cls(
            domain=domain,
            provider_module=provider.__module__,
            provider_name=provider.__name__,
            provider_version=str(provider.provider_version()),
            identity=str(provider.transaction_identity()),
            targets=targets,
            lease_seconds=lease_seconds)
        tx.renew_lease()
        tx.save()
        return tx

    # ----------------------------------------------------------------- apply
    def apply(self, image_path: str) -> List[AttributeResult]:
        """Write the primary attribute (the image) on every target."""
        provider = self.resolve_provider()
        primary = provider.PRIMARY_ATTRIBUTE
        results: List[AttributeResult] = []
        for snap in self.targets:
            tid = snap.target_id
            label = str(tid)
            try:
                provider.write_attribute(tid, primary, image_path)
            except Exception as err:
                results.append(AttributeResult(
                    label, primary, APPLY_FAILED,
                    "{}: {}".format(type(err).__name__, err)))
                continue
            results.append(AttributeResult(label, primary, APPLIED))
            self._record_baseline(provider, snap)
        self.last_apply = results
        self.renew_lease()
        self.save()
        return results

    def _record_baseline(self, provider, snap: TargetSnapshot) -> None:
        tid = snap.target_id
        values: Dict[str, Any] = {}
        present: Dict[str, bool] = {}
        for name, attr in snap.attributes.items():
            if attr.readable:
                try:
                    value, is_present = _normalize_reading(
                        provider.read_attribute(tid, name))
                    _check_json_safe(value)
                except Exception:
                    continue
                values[name] = value
                present[name] = is_present
        self.baseline[snap.key] = values
        self.baseline_present[snap.key] = present
        version, _ = _safe_call(provider.read_version, tid)
        self.baseline_version[snap.key] = version

    # --------------------------------------------------------------- restore
    def restore(self, reason: str = REASON_EXIT) -> RestoreReport:
        report = RestoreReport(self.tx_id, self.domain, reason)
        if self.finished:
            return report

        provider = self.resolve_provider()
        compatible, err = _safe_call(provider.is_compatible)
        if not compatible:
            report.results.append(AttributeResult(
                "-", "-", PROVIDER_UNAVAILABLE,
                err or "{} is no longer compatible".format(self.provider_name)))
            self.save()
            return report

        identity, err = _safe_call(provider.transaction_identity)
        if err is not None or identity != self.identity:
            report.results.append(AttributeResult(
                "-", "-", IDENTITY_MISMATCH,
                "snapshot {!r} != current {!r}".format(self.identity, identity)))
            self.save()
            return report

        current, err = _safe_call(provider.list_targets)
        if err is not None:
            report.results.append(AttributeResult(
                "-", "-", PROVIDER_UNAVAILABLE, err))
            self.save()
            return report
        current_keys = {t.key: t for t in current}

        for snap in self.targets:
            label = str(snap.target_id)
            cur_target = current_keys.get(snap.key)
            base_values = self.baseline.get(snap.key, {})
            base_present = self.baseline_present.get(snap.key, {})
            for name, attr in snap.attributes.items():
                status, detail = self._restore_one(
                    provider, snap, cur_target, name, attr,
                    base_values, base_present)
                report.results.append(
                    AttributeResult(label, name, status, detail))

        self.finished = True
        self.finish_reason = reason
        if report.settled:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        else:
            self.save()
        return report

    @staticmethod
    def _restore_one(provider, snap: TargetSnapshot, cur_target,
                     name: str, attr: CapturedAttribute,
                     base_values: Dict[str, Any],
                     base_present: Dict[str, bool]):
        if cur_target is None:
            return MISSING_TARGET, "target no longer exists"
        if name not in base_values:
            # We never got a post-apply reading: state is unverifiable.
            if attr.status == CAPTURED:
                return IRREVERSIBLE, "no readable state after apply"
            return IRREVERSIBLE, attr.error or "state could not be read"
        if not attr.reversible:
            if attr.readable and not attr.writable:
                return NOT_WRITABLE, "attribute is read-only"
            return IRREVERSIBLE, attr.error or "pre-state was unreadable"

        live_value, live_present, err = _read_live(provider, cur_target, name)
        if err is not None:
            # Cannot prove the user didn't change it: do not clobber.
            return CONFLICT, "cannot verify current value ({})".format(err)
        if live_present != base_present.get(name, True) \
                or live_value != base_values.get(name, _MISSING):
            return CONFLICT, "value changed externally during the session"

        try:
            if attr.present:
                provider.write_attribute(cur_target, name, attr.value)
            else:
                provider.remove_attribute(cur_target, name)
        except Exception as err:
            return RESTORE_FAILED, "{}: {}".format(type(err).__name__, err)
        return RESTORED, ""

    #------------------------------------------------------------------ lease
    def renew_lease(self) -> None:
        if self.lease_seconds:
            self.lease_expires_at = time.time() + float(self.lease_seconds)

    def lease_expired(self, now: Optional[float] = None) -> bool:
        if self.lease_expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.lease_expires_at

    # ------------------------------------------------------------- providers
    def resolve_provider(self):
        module = importlib.import_module(self.provider_module)
        try:
            return getattr(module, self.provider_name)
        except AttributeError:
            raise TransactionError(
                "provider {}.{} no longer exists".format(
                    self.provider_module, self.provider_name))

    # ----------------------------------------------------------- persistence
    @property
    def path(self) -> Path:
        return state_dir() / "{}-{}.json".format(self.domain, self.tx_id)

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_json(), fh, indent=2)
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, path) -> "Transaction":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_json(json.load(fh))

    def to_json(self) -> Dict[str, Any]:
        return {
            "state_version": STATE_VERSION,
            "tx_id": self.tx_id,
            "domain": self.domain,
            "provider": {
                "module": self.provider_module,
                "name": self.provider_name,
                "version": self.provider_version,
                "identity": self.identity,
            },
            "created_at": self.created_at,
            "lease_seconds": self.lease_seconds,
            "lease_expires_at": self.lease_expires_at,
            "targets": [
                {
                    "kind": t.kind,
                    "key": t.key,
                    "version": t.version,
                    "attributes": {
                        n: a.to_json() for n, a in t.attributes.items()
                    },
                }
                for t in self.targets
            ],
            "baseline": self.baseline,
            "baseline_present": self.baseline_present,
            "baseline_version": self.baseline_version,
            "finished": self.finished,
            "finish_reason": self.finish_reason,
            "last_apply": [r.to_json() for r in self.last_apply],
        }

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "Transaction":
        provider = data["provider"]
        targets = [
            TargetSnapshot(
                t["kind"], t["key"], t.get("version"),
                {n: CapturedAttribute.from_json(a)
                 for n, a in t["attributes"].items()})
            for t in data["targets"]
        ]
        return cls(
            domain=data["domain"],
            provider_module=provider["module"],
            provider_name=provider["name"],
            provider_version=provider.get("version", "0"),
            identity=provider.get("identity", ""),
            targets=targets,
            tx_id=data["tx_id"],
            created_at=data.get("created_at", time.time()),
            lease_seconds=data.get("lease_seconds"),
            lease_expires_at=data.get("lease_expires_at"),
            baseline=data.get("baseline", {}),
            baseline_present=data.get("baseline_present", {}),
            baseline_version=data.get("baseline_version", {}),
            finished=data.get("finished", False),
            finish_reason=data.get("finish_reason"),
            last_apply=[AttributeResult.from_json(r)
                        for r in data.get("last_apply", [])])


def _read_live(provider, target: TargetId, name: str):
    try:
        value, present = _normalize_reading(
            provider.read_attribute(target, name))
        _check_json_safe(value)
        return value, present, None
    except Exception as err:
        return None, False, "{}: {}".format(type(err).__name__, err)


# ------------------------------------------------------------- disk helpers
def stored_transactions(domain: Optional[str] = None):
    for file in sorted(state_dir().glob("*.json")):
        try:
            tx = Transaction.load(file)
        except Exception:
            continue
        if domain is None or tx.domain == domain:
            yield tx


def restore_all(domain: Optional[str] = None) -> List[RestoreReport]:
    """
    Force-restore every live transaction (used by 'clear'). Restores run even
    when the lease has not expired; external-change protection still applies.
    """
    reports: List[RestoreReport] = []
    for tx in list(stored_transactions(domain)):
        if tx.finished:
            try:
                tx.path.unlink()
            except OSError:
                pass
            continue
        reports.append(tx.restore(REASON_CLEAR))
    return reports


def recover(domains=("terminal", "wallpaper")) -> List[RestoreReport]:
    """
    Restore transactions whose lease has expired (owner process crashed or was
    killed). Non-expired and ownerless (lease=None) transactions are left
    alone.
    """
    now = time.time()
    reports: List[RestoreReport] = []
    for domain in domains:
        for tx in list(stored_transactions(domain)):
            if tx.finished:
                try:
                    tx.path.unlink()
                except OSError:
                    pass
                continue
            if tx.lease_expired(now):
                reports.append(tx.restore(REASON_LEASE))
    return reports
