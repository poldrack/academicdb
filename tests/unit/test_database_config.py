"""
Tests for selecting the database configuration from environment variables.

Neon is opt-in via USE_NEON=true so the local app stays on SQLite until
the data migration is complete.
"""
import pytest

from academicdb_web.database import database_config


POOLED = 'postgresql://u:p@ep-x-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require'
UNPOOLED = 'postgresql://u:p@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require'
NEON_ENV = {
    'USE_NEON': 'true',
    'NEON_DATABASE_URL': POOLED,
    'NEON_DATABASE_URL_UNPOOLED': UNPOOLED,
}


@pytest.fixture
def base_dir(tmp_path):
    return tmp_path


def test_defaults_to_sqlite(base_dir):
    config = database_config({}, base_dir)
    assert config['ENGINE'] == 'django.db.backends.sqlite3'
    assert config['NAME'] == base_dir / 'db.sqlite3'


def test_neon_credentials_alone_do_not_switch_to_neon(base_dir):
    env = {k: v for k, v in NEON_ENV.items() if k != 'USE_NEON'}
    config = database_config(env, base_dir)
    assert config['ENGINE'] == 'django.db.backends.sqlite3'


def test_use_neon_selects_pooled_url(base_dir):
    config = database_config(NEON_ENV, base_dir)
    assert config['ENGINE'] == 'django.db.backends.postgresql'
    assert config['HOST'] == 'ep-x-pooler.us-east-2.aws.neon.tech'
    assert config['NAME'] == 'neondb'
    assert config['OPTIONS']['sslmode'] == 'require'


def test_pooled_neon_disables_server_side_cursors(base_dir):
    config = database_config(NEON_ENV, base_dir)
    assert config['DISABLE_SERVER_SIDE_CURSORS'] is True


def test_neon_unpooled_selects_direct_url(base_dir):
    env = {**NEON_ENV, 'NEON_UNPOOLED': 'true'}
    config = database_config(env, base_dir)
    assert config['HOST'] == 'ep-x.us-east-2.aws.neon.tech'
    assert config.get('DISABLE_SERVER_SIDE_CURSORS', False) is False


def test_use_neon_takes_precedence_over_database_url(base_dir):
    env = {**NEON_ENV, 'DATABASE_URL': 'sqlite:////tmp/other.sqlite3'}
    config = database_config(env, base_dir)
    assert config['HOST'] == 'ep-x-pooler.us-east-2.aws.neon.tech'


def test_use_neon_without_url_raises(base_dir):
    with pytest.raises(ValueError, match='NEON_DATABASE_URL'):
        database_config({'USE_NEON': 'true'}, base_dir)


def test_neon_unpooled_without_url_raises(base_dir):
    env = {'USE_NEON': 'true', 'NEON_DATABASE_URL': POOLED, 'NEON_UNPOOLED': 'true'}
    with pytest.raises(ValueError, match='NEON_DATABASE_URL_UNPOOLED'):
        database_config(env, base_dir)


def test_database_url_still_supported(base_dir):
    config = database_config({'DATABASE_URL': 'sqlite:////tmp/other.sqlite3'}, base_dir)
    assert config['ENGINE'] == 'django.db.backends.sqlite3'
    assert config['NAME'] == '/tmp/other.sqlite3'


def test_use_postgres_still_supported(base_dir):
    env = {'USE_POSTGRES': 'true', 'DB_NAME': 'adb', 'DB_HOST': 'db.local'}
    config = database_config(env, base_dir)
    assert config['ENGINE'] == 'django.db.backends.postgresql'
    assert config['NAME'] == 'adb'
    assert config['HOST'] == 'db.local'
