import boto3
import pytest
from moto import mock_aws

from s3_migration_tools.inventory import compute_diff, index_objects
from s3_migration_tools.transfer import copy_many


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="src")
        client.create_bucket(Bucket="dst")
        yield client


def test_sync_copies_missing_and_different(s3):
    s3.put_object(Bucket="src", Key="a.txt", Body=b"hello", ContentType="text/plain")
    s3.put_object(Bucket="src", Key="dir/b.bin", Body=b"x" * 1000)
    s3.put_object(Bucket="dst", Key="dir/b.bin", Body=b"old")
    s3.put_object(Bucket="dst", Key="extra.txt", Body=b"only here")

    diff = compute_diff(index_objects(s3, "src"), index_objects(s3, "dst"))
    assert {o.key for o in diff.missing} == {"a.txt"}
    assert {o.key for o in diff.different} == {"dir/b.bin"}
    assert {o.key for o in diff.extra} == {"extra.txt"}

    result = copy_many(diff.to_copy, s3, "src", s3, "dst", workers=2)
    assert not result.failed
    assert s3.get_object(Bucket="dst", Key="a.txt")["ContentType"] == "text/plain"

    after = compute_diff(index_objects(s3, "src"), index_objects(s3, "dst"))
    assert not after.to_copy
