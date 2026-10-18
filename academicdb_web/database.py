"""
Select the Django database configuration from environment variables.

Order of precedence:
1. USE_NEON=true: Neon PostgreSQL (pooled by default; NEON_UNPOOLED=true
   for the direct connection, e.g. when running migrations)
2. DATABASE_URL
3. USE_POSTGRES=true with DB_* variables
4. SQLite in BASE_DIR
"""
import dj_database_url


def _is_true(env, key):
    return env.get(key, 'false').lower() == 'true'


def _require(env, key):
    value = env.get(key)
    if not value:
        raise ValueError(f'USE_NEON=true requires {key} to be set')
    return value


def _neon_config(env):
    unpooled = _is_true(env, 'NEON_UNPOOLED')
    key = 'NEON_DATABASE_URL_UNPOOLED' if unpooled else 'NEON_DATABASE_URL'
    config = dj_database_url.parse(
        _require(env, key),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=True,
    )
    if not unpooled:
        # PgBouncer transaction pooling does not support server-side cursors
        config['DISABLE_SERVER_SIDE_CURSORS'] = True
    return config


def _postgres_config(env):
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env.get('DB_NAME', 'academicdb'),
        'USER': env.get('DB_USER', 'postgres'),
        'PASSWORD': env.get('DB_PASSWORD', ''),
        'HOST': env.get('DB_HOST', 'localhost'),
        'PORT': env.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 10,
        }
    }


def database_config(env, base_dir):
    """Return the 'default' DATABASES entry for the given environment."""
    if _is_true(env, 'USE_NEON'):
        return _neon_config(env)
    if env.get('DATABASE_URL'):
        return dj_database_url.parse(
            env['DATABASE_URL'],
            conn_max_age=600,
            conn_health_checks=True,
        )
    if _is_true(env, 'USE_POSTGRES'):
        return _postgres_config(env)
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': base_dir / 'db.sqlite3',
    }
