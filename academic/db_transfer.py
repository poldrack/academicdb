"""
Count rows and copy all data between Django database aliases.

Data moves as a Django JSON fixture with natural keys, so the same path
serves migration (SQLite -> Neon), backups and restores into any engine.
"""
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import connections, transaction


# Recreated by `migrate`, or not worth moving
EXCLUDED_MODELS = frozenset({
    'contenttypes.contenttype',
    'auth.permission',
    'sessions.session',
})

# Rows created by `migrate`/`flush` (default example.com site, pk 1);
# loaddata overwrites them by pk, so they don't make a target "non-empty"
MIGRATE_SEEDED_MODELS = frozenset({'sites.site'})


class TargetNotEmptyError(Exception):
    pass


def _label(model):
    return model._meta.label_lower


def _transferable_models():
    return [
        m for m in apps.get_models()
        if m._meta.managed and not m._meta.proxy
        and _label(m) not in EXCLUDED_MODELS
    ]


def model_counts(using):
    """Row count per model label for every transferable model."""
    return {
        _label(m): m._default_manager.using(using).count()
        for m in _transferable_models()
    }


def count_mismatches(source, target):
    """(label, source_count, target_count) for each label whose counts differ."""
    labels = sorted(set(source) | set(target))
    return [
        (label, source.get(label, 0), target.get(label, 0))
        for label in labels
        if source.get(label, 0) != target.get(label, 0)
    ]


def dump_fixture(using, path):
    """Dump all transferable data to a JSON fixture (gzipped if path ends in .gz)."""
    call_command(
        'dumpdata',
        database=using,
        natural_foreign=True,
        natural_primary=False,  # keep pks (SITE_ID=1, user ids)
        exclude=sorted(EXCLUDED_MODELS),
        output=str(path),
        verbosity=0,
    )


def _check_target_empty(using):
    nonempty = [
        label for label, count in model_counts(using).items()
        if count > 0 and label not in MIGRATE_SEEDED_MODELS
    ]
    if nonempty:
        raise TargetNotEmptyError(
            f"Target database '{using}' is not empty: {', '.join(sorted(nonempty))}"
        )


def _reset_sequences(using):
    connection = connections[using]
    if connection.vendor != 'postgresql':
        return
    statements = connection.ops.sequence_reset_sql(no_style(), _transferable_models())
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def load_fixture(path, using):
    """Load a fixture into an empty database, then reset Postgres sequences."""
    _check_target_empty(using)
    with transaction.atomic(using=using):
        call_command('loaddata', str(path), database=using, verbosity=0)
        _reset_sequences(using)


def counts_path_for(fixture):
    """Sidecar counts file for a backup fixture: X.json.gz -> X.counts.json."""
    fixture = Path(fixture)
    return fixture.with_name(fixture.name.removesuffix('.json.gz') + '.counts.json')


def copy_all_data(source, target, tmp_dir):
    """Copy everything from source to target; return any count mismatches."""
    path = Path(tmp_dir) / 'transfer.json.gz'
    dump_fixture(source, path)
    load_fixture(path, target)
    return count_mismatches(model_counts(source), model_counts(target))
