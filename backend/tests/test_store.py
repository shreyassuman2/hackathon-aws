import boto3
import pytest
from moto import mock_aws

from runway.store import ConflictError, DynamoStore, LocalStore, NotFound


@pytest.fixture(params=["local", "dynamodb"])
def store(request, tmp_path, monkeypatch):
    if request.param == "local":
        yield LocalStore(tmp_path / "s.json", "co1")
        return
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName="runway",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )
        yield DynamoStore("runway", "co1", region="us-east-1")


def test_crud_roundtrip(store):
    rec = store.put("thing", {"name": "a", "amount": 12.5, "tags": ["x"], "nested": {"n": 1}})
    got = store.get("thing", rec["id"])
    assert got["amount"] == 12.5 and got["tags"] == ["x"] and got["nested"] == {"n": 1} and got["version"] == 1
    store.put("other", {"name": "b"})
    assert [r["name"] for r in store.list("thing")] == ["a"]
    store.delete("thing", rec["id"])
    assert store.get("thing", rec["id"]) is None


def test_optimistic_lock(store):
    rec = store.put("neg", {"status": "opening"})
    store.update("neg", rec["id"], {"status": "waiting"}, expect_version=1)
    with pytest.raises(ConflictError):
        store.update("neg", rec["id"], {"status": "closed"}, expect_version=1)
    assert store.get("neg", rec["id"])["status"] == "waiting"


def test_update_missing_raises(store):
    with pytest.raises(NotFound):
        store.update("neg", "nope", {"a": 1})
