"""
Tests for uploading backups to Neon object storage (S3-compatible) and pruning.
No network: the S3 client is stubbed with botocore's Stubber.
"""
import boto3
import pytest
from botocore.stub import ANY, Stubber
from django.core.management import call_command
from django.core.management.base import CommandError

from academic.remote_backup import prune_backups, s3_client_from_env, upload_backup


STAMP = 'academicdb_20261018_120000'
PREFIX = 'academicdb-backups/'


@pytest.fixture
def client():
    return boto3.client(
        's3', region_name='us-east-1',
        aws_access_key_id='x', aws_secret_access_key='x',
    )


@pytest.fixture
def stub(client):
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def fixture(tmp_path):
    path = tmp_path / f'{STAMP}.json.gz'
    path.write_bytes(b'data')
    (tmp_path / f'{STAMP}.counts.json').write_text('{}')
    return path


def stamps(n):
    return [f'academicdb_202601{d:02d}_120000' for d in range(1, n + 1)]


def listing(keys):
    return {'Contents': [{'Key': k} for k in keys], 'IsTruncated': False}


def test_s3_client_from_env_requires_endpoint():
    with pytest.raises(ValueError, match='AWS_ENDPOINT_URL_S3'):
        s3_client_from_env({
            'AWS_ACCESS_KEY_ID': 'a', 'AWS_SECRET_ACCESS_KEY': 'b', 'AWS_REGION': 'us-east-2',
        })


def test_upload_backup_puts_fixture_and_counts(client, stub, fixture):
    for name in (f'{STAMP}.json.gz', f'{STAMP}.counts.json'):
        stub.add_response('put_object', {}, {'Bucket': 'bkt', 'Key': PREFIX + name, 'Body': ANY})
    assert upload_backup(client, 'bkt', fixture) == [
        f'{PREFIX}{STAMP}.json.gz',
        f'{PREFIX}{STAMP}.counts.json',
    ]


def test_prune_keeps_newest_timestamps(client, stub):
    all_stamps = stamps(28)
    keys = [f'{PREFIX}{s}{ext}' for s in all_stamps for ext in ('.json.gz', '.counts.json')]
    stub.add_response('list_objects_v2', listing(keys), {'Bucket': 'bkt', 'Prefix': PREFIX})
    oldest = [f'{PREFIX}{s}{ext}' for s in all_stamps[:2] for ext in ('.json.gz', '.counts.json')]
    stub.add_response('delete_objects', {}, {
        'Bucket': 'bkt',
        'Delete': {'Objects': [{'Key': k} for k in sorted(oldest)]},
    })
    assert sorted(prune_backups(client, 'bkt', keep=26)) == sorted(oldest)


def test_prune_only_touches_backup_prefix(client, stub):
    keys = [f'{PREFIX}notes.txt'] + [f'{PREFIX}{s}.json.gz' for s in stamps(3)]
    stub.add_response('list_objects_v2', listing(keys), {'Bucket': 'bkt', 'Prefix': PREFIX})
    stub.add_response('delete_objects', {}, {
        'Bucket': 'bkt',
        'Delete': {'Objects': [{'Key': f'{PREFIX}{stamps(3)[0]}.json.gz'}]},
    })
    deleted = prune_backups(client, 'bkt', keep=2)
    assert f'{PREFIX}notes.txt' not in deleted
    assert deleted == [f'{PREFIX}{stamps(3)[0]}.json.gz']


def test_prune_with_nothing_to_delete_makes_no_delete_call(client, stub):
    keys = [f'{PREFIX}{s}.json.gz' for s in stamps(2)]
    stub.add_response('list_objects_v2', listing(keys), {'Bucket': 'bkt', 'Prefix': PREFIX})
    assert prune_backups(client, 'bkt', keep=26) == []


@pytest.mark.django_db
def test_backup_upload_requires_bucket(monkeypatch, tmp_path):
    monkeypatch.delenv('BACKUP_BUCKET', raising=False)
    with pytest.raises(CommandError, match='BACKUP_BUCKET'):
        call_command('backup_database', output_dir=str(tmp_path), upload=True)


FULL_ENV = {
    'AWS_ENDPOINT_URL_S3': 'https://s3.example.test', 'AWS_ACCESS_KEY_ID': 'a',
    'AWS_SECRET_ACCESS_KEY': 'b', 'AWS_REGION': 'us-east-2',
}


def test_s3_client_sends_checksums_only_when_required():
    # S3-compatible stores (Neon) may reject boto3's default CRC32 checksums
    config = s3_client_from_env(FULL_ENV).meta.config
    assert config.request_checksum_calculation == 'when_required'
    assert config.response_checksum_validation == 'when_required'


def test_prune_raises_when_delete_reports_errors(client, stub):
    keys = [f'{PREFIX}{s}.json.gz' for s in stamps(3)]
    stub.add_response('list_objects_v2', listing(keys), {'Bucket': 'bkt', 'Prefix': PREFIX})
    stub.add_response('delete_objects', {
        'Errors': [{'Key': keys[0], 'Code': 'AccessDenied', 'Message': 'denied'}],
    }, {'Bucket': 'bkt', 'Delete': {'Objects': [{'Key': keys[0]}]}})
    with pytest.raises(RuntimeError, match='AccessDenied'):
        prune_backups(client, 'bkt', keep=2)
