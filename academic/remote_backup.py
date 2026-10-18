"""
Upload backups to Neon object storage (S3-compatible) and prune old ones.
"""
import re
from pathlib import Path

import boto3

from academic.db_transfer import counts_path_for


BACKUP_PREFIX = 'academicdb-backups/'
KEEP_BACKUPS = 26  # about six months of weekly backups
ENV_KEYS = ('AWS_ENDPOINT_URL_S3', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION')
BACKUP_KEY = re.compile(
    re.escape(BACKUP_PREFIX) + r'academicdb_(\d{8}_\d{6})\.(json\.gz|counts\.json)$'
)
DELETE_BATCH = 1000  # S3 delete_objects limit


def s3_client_from_env(env):
    for key in ENV_KEYS:
        if not env.get(key):
            raise ValueError(f'{key} must be set for remote backups')
    return boto3.client(
        's3',
        endpoint_url=env['AWS_ENDPOINT_URL_S3'],
        aws_access_key_id=env['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=env['AWS_SECRET_ACCESS_KEY'],
        region_name=env['AWS_REGION'],
    )


def upload_backup(client, bucket, fixture):
    """Upload a fixture and its counts sidecar; return the object keys."""
    keys = []
    for path in (Path(fixture), counts_path_for(fixture)):
        key = BACKUP_PREFIX + path.name
        client.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
        keys.append(key)
    return keys


def _backup_keys_by_stamp(client, bucket):
    by_stamp = {}
    paginator = client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=BACKUP_PREFIX):
        for obj in page.get('Contents', []):
            match = BACKUP_KEY.match(obj['Key'])
            if match:
                by_stamp.setdefault(match.group(1), []).append(obj['Key'])
    return by_stamp


def prune_backups(client, bucket, keep=KEEP_BACKUPS):
    """Delete all but the newest `keep` backups; return the deleted keys."""
    by_stamp = _backup_keys_by_stamp(client, bucket)
    old_stamps = sorted(by_stamp)[:-keep] if len(by_stamp) > keep else []
    doomed = sorted(key for stamp in old_stamps for key in by_stamp[stamp])
    for i in range(0, len(doomed), DELETE_BATCH):
        batch = doomed[i:i + DELETE_BATCH]
        client.delete_objects(
            Bucket=bucket, Delete={'Objects': [{'Key': k} for k in batch]}
        )
    return doomed
