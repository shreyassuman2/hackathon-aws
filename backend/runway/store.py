"""Persistence: one tiny interface, two backends.

Data model (DynamoDB single-table, mirrored by the local backend):
    PK = "CO#<company_id>"        every record belongs to one company
    SK = "<entity>#<id>"           entity is a short name such as "alert" or "negotiation"

All reads are a Query on the company partition with `begins_with(SK, entity#)`, so there are
no table scans. Filtering and sorting happen in Python, which is fine at startup scale (thousands
of rows per company). If a list gets big, add a GSI rather than scanning.

Records are plain dicts. Every record has `id`, `created_at`, `updated_at` and `version`.
`update(..., expect_version=n)` is an optimistic-lock write. The negotiation engine depends on
it so that two workers (or a crashed one restarting) never double-apply a step.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from runway.config import get_settings

Record = dict[str, Any]


class ConflictError(Exception):
    """Raised when an optimistic-lock write loses the race."""


class NotFound(KeyError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


class Store(Protocol):
    def get(self, entity: str, id: str) -> Record | None: ...
    def list(self, entity: str) -> list[Record]: ...
    def put(self, entity: str, record: Record) -> Record: ...
    def update(self, entity: str, id: str, patch: Record, *, expect_version: int | None = None) -> Record: ...
    def delete(self, entity: str, id: str) -> None: ...


# ── helpers shared by both backends ───────────────────────────────────────────


def _stamp_new(record: Record) -> Record:
    rec = dict(record)
    rec.setdefault("id", new_id())
    ts = now_iso()
    rec.setdefault("created_at", ts)
    rec["updated_at"] = rec.get("updated_at") or ts
    rec["version"] = int(rec.get("version") or 0) + 1
    return rec


def find(
    store: Store,
    entity: str,
    where: Callable[[Record], bool] | None = None,
    *,
    order_by: str | None = None,
    desc: bool = False,
    limit: int | None = None,
) -> list[Record]:
    """Filter, sort and limit a list() call in one go."""
    rows = store.list(entity)
    if where:
        rows = [r for r in rows if where(r)]
    if order_by:
        rows.sort(key=lambda r: (r.get(order_by) is None, r.get(order_by)), reverse=desc)
    return rows[:limit] if limit else rows


def find_one(store: Store, entity: str, where: Callable[[Record], bool], **kw: Any) -> Record | None:
    rows = find(store, entity, where, limit=1, **kw)
    return rows[0] if rows else None


# ── Local JSON-file backend (dev + tests) ─────────────────────────────────────


class LocalStore:
    """A JSON file on disk. Thread-safe within one process, atomic on write.

    Good enough for running the API and the negotiation worker side by side on one
    laptop: every operation re-reads the file, so both processes see each other's writes.
    """

    def __init__(self, path: str | Path, company_id: str):
        self.path = Path(path)
        self.company_id = company_id
        self._lock = threading.RLock()

    def _load(self) -> dict[str, dict[str, Record]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text() or "{}").get(self.company_id, {})

    def _save(self, data: dict[str, dict[str, Record]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        whole = json.loads(self.path.read_text() or "{}") if self.path.exists() else {}
        whole[self.company_id] = data
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(whole, f, indent=1, default=str)
        os.replace(tmp, self.path)

    def get(self, entity: str, id: str) -> Record | None:
        with self._lock:
            rec = self._load().get(entity, {}).get(id)
            return dict(rec) if rec else None

    def list(self, entity: str) -> list[Record]:
        with self._lock:
            return [dict(r) for r in self._load().get(entity, {}).values()]

    def put(self, entity: str, record: Record) -> Record:
        with self._lock:
            data = self._load()
            rec = _stamp_new(record)
            data.setdefault(entity, {})[rec["id"]] = rec
            self._save(data)
            return dict(rec)

    def put_many(self, entity: str, records: Iterable[Record]) -> int:
        with self._lock:
            data = self._load()
            bucket = data.setdefault(entity, {})
            n = 0
            for r in records:
                rec = _stamp_new(r)
                bucket[rec["id"]] = rec
                n += 1
            self._save(data)
            return n

    def update(self, entity: str, id: str, patch: Record, *, expect_version: int | None = None) -> Record:
        with self._lock:
            data = self._load()
            cur = data.get(entity, {}).get(id)
            if cur is None:
                raise NotFound(f"{entity}#{id}")
            if expect_version is not None and int(cur.get("version") or 0) != expect_version:
                raise ConflictError(f"{entity}#{id} is at v{cur.get('version')}, expected v{expect_version}")
            cur.update(patch)
            cur["updated_at"] = now_iso()
            cur["version"] = int(cur.get("version") or 0) + 1
            self._save(data)
            return dict(cur)

    def delete(self, entity: str, id: str) -> None:
        with self._lock:
            data = self._load()
            data.get(entity, {}).pop(id, None)
            self._save(data)

    def reset(self) -> None:
        with self._lock:
            self._save({})


# ── DynamoDB backend (AWS) ────────────────────────────────────────────────────


def _to_dynamo(v: Any) -> Any:
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return {k: _to_dynamo(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_to_dynamo(x) for x in v]
    return v


def _from_dynamo(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _from_dynamo(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_from_dynamo(x) for x in v]
    return v


class DynamoStore:
    def __init__(self, table_name: str, company_id: str, *, region: str, endpoint_url: str | None = None):
        import boto3  # imported lazily so local dev never needs AWS credentials

        self.company_id = company_id
        self.table = boto3.resource("dynamodb", region_name=region, endpoint_url=endpoint_url).Table(table_name)
        self._pk = f"CO#{company_id}"

    def _key(self, entity: str, id: str) -> dict[str, str]:
        return {"pk": self._pk, "sk": f"{entity}#{id}"}

    @staticmethod
    def _clean(item: dict[str, Any]) -> Record:
        item = _from_dynamo(item)
        item.pop("pk", None)
        item.pop("sk", None)
        return item

    def get(self, entity: str, id: str) -> Record | None:
        item = self.table.get_item(Key=self._key(entity, id)).get("Item")
        return self._clean(item) if item else None

    def list(self, entity: str) -> list[Record]:
        from boto3.dynamodb.conditions import Key

        out: list[Record] = []
        kwargs: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(self._pk) & Key("sk").begins_with(f"{entity}#")
        }
        while True:
            resp = self.table.query(**kwargs)
            out.extend(self._clean(i) for i in resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                return out
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def put(self, entity: str, record: Record) -> Record:
        rec = _stamp_new(record)
        self.table.put_item(Item=_to_dynamo({**rec, **self._key(entity, rec["id"])}))
        return rec

    def put_many(self, entity: str, records: Iterable[Record]) -> int:
        n = 0
        with self.table.batch_writer() as batch:
            for r in records:
                rec = _stamp_new(r)
                batch.put_item(Item=_to_dynamo({**rec, **self._key(entity, rec["id"])}))
                n += 1
        return n

    def update(self, entity: str, id: str, patch: Record, *, expect_version: int | None = None) -> Record:
        from botocore.exceptions import ClientError

        patch = {**patch, "updated_at": now_iso()}
        names = {f"#f{i}": k for i, k in enumerate(patch)}
        values = {f":v{i}": _to_dynamo(v) for i, v in enumerate(patch.values())}
        sets = [f"#f{i} = :v{i}" for i in range(len(patch))]
        names["#ver"] = "version"
        values[":one"] = 1
        sets.append("#ver = #ver + :one")
        cond = "attribute_exists(pk)"
        if expect_version is not None:
            cond += " AND #ver = :expected"
            values[":expected"] = expect_version
        try:
            resp = self.table.update_item(
                Key=self._key(entity, id),
                UpdateExpression="SET " + ", ".join(sets),
                ConditionExpression=cond,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                if expect_version is not None and self.get(entity, id) is not None:
                    raise ConflictError(f"{entity}#{id} changed underneath us") from e
                raise NotFound(f"{entity}#{id}") from e
            raise
        return self._clean(resp["Attributes"])

    def delete(self, entity: str, id: str) -> None:
        self.table.delete_item(Key=self._key(entity, id))


# ── factory ───────────────────────────────────────────────────────────────────

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        s = get_settings()
        if s.store == "dynamodb":
            _store = DynamoStore(s.dynamodb_table, s.company_id, region=s.aws_region, endpoint_url=s.dynamodb_endpoint)
        else:
            _store = LocalStore(s.local_store_path, s.company_id)
    return _store


def set_store(store: Store | None) -> None:
    """Swap the store (tests use this)."""
    global _store
    _store = store
