"""
Django management command to restore a PostgreSQL database from backup
"""
import os
import subprocess
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection as db_connection


class Command(BaseCommand):
    help = 'Restore a PostgreSQL database from backup'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            type=str,
            help='Path to the backup file to restore'
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Drop existing database objects before restore'
        )
        parser.add_argument(
            '--no-owner',
            action='store_true',
            help='Do not restore ownership of objects'
        )
        parser.add_argument(
            '--data-only',
            action='store_true',
            help='Restore only the data, not the schema'
        )
        parser.add_argument(
            '--schema-only',
            action='store_true',
            help='Restore only the schema, not the data'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )
        parser.add_argument(
            '-y', '--yes',
            action='store_true',
            help='Assume yes to all prompts (same as --force)'
        )
        parser.add_argument(
            '--create-db',
            action='store_true',
            help='Create the database before restoring (requires superuser privileges)'
        )

    def handle(self, *args, **options):
        # Get database configuration
        db_config = settings.DATABASES['default']

        if db_config['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('This command only works with PostgreSQL databases')

        backup_file = Path(options['backup_file'])
        if not backup_file.exists():
            raise CommandError(f"Backup file not found: {backup_file}")

        db_name = db_config['NAME']

        # Confirmation prompt (skip if --force or -y is provided)
        if not options['force'] and not options['yes']:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  WARNING: This will restore database '{db_name}' from:\n"
                    f"   {backup_file}\n"
                )
            )
            if options['clean']:
                self.stdout.write(
                    self.style.WARNING(
                        "   --clean flag is set: ALL EXISTING DATA WILL BE DROPPED!\n"
                    )
                )
            confirm = input("Are you sure you want to continue? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Restore cancelled.")
                return

        # Determine file format based on extension
        file_ext = ''.join(backup_file.suffixes)
        is_compressed_sql = file_ext.endswith('.sql.gz')
        is_sql = file_ext.endswith('.sql') and not is_compressed_sql
        is_custom = file_ext.endswith('.dump')
        is_tar = file_ext.endswith('.tar')

        # Set PGPASSWORD environment variable if password is configured
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']

        try:
            # Close existing database connections
            db_connection.close()

            if options['create_db']:
                self.stdout.write(f"Creating database '{db_name}' if it doesn't exist...")
                create_cmd = [
                    'createdb',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-p', str(db_config.get('PORT', 5432)),
                    '-U', db_config.get('USER', 'postgres'),
                    '--no-password',
                    db_name
                ]
                # Ignore error if database already exists
                subprocess.run(create_cmd, env=env, capture_output=True)

            self.stdout.write(f"Starting restore of database '{db_name}'...")
            self.stdout.write(f"Restore file: {backup_file}")

            if is_compressed_sql:
                # Decompress and pipe to psql
                psql_cmd = [
                    'psql',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-p', str(db_config.get('PORT', 5432)),
                    '-U', db_config.get('USER', 'postgres'),
                    '-d', db_name,
                    '--no-password'
                ]

                with open(backup_file, 'rb') as f:
                    gunzip = subprocess.Popen(
                        ['gunzip', '-c'],
                        stdin=f,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    psql = subprocess.Popen(
                        psql_cmd,
                        stdin=gunzip.stdout,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                        text=True
                    )
                    gunzip.stdout.close()
                    psql_out, psql_err = psql.communicate()

                    if psql.returncode != 0:
                        raise CommandError(f"psql failed: {psql_err}")

            elif is_sql:
                # Use psql for plain SQL files
                psql_cmd = [
                    'psql',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-p', str(db_config.get('PORT', 5432)),
                    '-U', db_config.get('USER', 'postgres'),
                    '-d', db_name,
                    '--no-password',
                    '-f', str(backup_file)
                ]

                result = subprocess.run(
                    psql_cmd,
                    capture_output=True,
                    text=True,
                    env=env
                )

                if result.returncode != 0:
                    raise CommandError(f"Restore failed: {result.stderr}")

            else:
                # Use pg_restore for custom and tar formats
                pg_restore_cmd = [
                    'pg_restore',
                    '-h', db_config.get('HOST', 'localhost'),
                    '-p', str(db_config.get('PORT', 5432)),
                    '-U', db_config.get('USER', 'postgres'),
                    '-d', db_name,
                    '--no-password',
                    '--verbose'
                ]

                # Add format-specific options
                if is_custom:
                    pg_restore_cmd.extend(['-Fc'])
                elif is_tar:
                    pg_restore_cmd.extend(['-Ft'])

                # Add optional flags
                if options['clean']:
                    pg_restore_cmd.append('--clean')
                if options['no_owner']:
                    pg_restore_cmd.append('--no-owner')
                if options['data_only']:
                    pg_restore_cmd.append('--data-only')
                if options['schema_only']:
                    pg_restore_cmd.append('--schema-only')

                # Add the backup file
                pg_restore_cmd.append(str(backup_file))

                # Run pg_restore
                result = subprocess.run(
                    pg_restore_cmd,
                    capture_output=True,
                    text=True,
                    env=env
                )

                # pg_restore may return non-zero even on partial success
                # Check for critical errors
                if result.returncode != 0 and "ERROR" in result.stderr:
                    self.stdout.write(
                        self.style.WARNING(f"Some warnings/errors occurred:\n{result.stderr}")
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Restore completed successfully!\n"
                    f"  Database: {db_name}\n"
                    f"  Restored from: {backup_file}"
                )
            )

            # Show some basic statistics
            try:
                with db_connection.cursor() as cursor:
                    # Count tables
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                    """)
                    table_count = cursor.fetchone()[0]

                    self.stdout.write(f"\nDatabase statistics:")
                    self.stdout.write(f"  Tables: {table_count}")

                    # Try to count publications if the table exists
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'academic_publication'
                    """)
                    if cursor.fetchone()[0] > 0:
                        cursor.execute("SELECT COUNT(*) FROM academic_publication")
                        pub_count = cursor.fetchone()[0]
                        self.stdout.write(f"  Publications: {pub_count}")
            except Exception:
                # Ignore errors in statistics gathering
                pass

        except subprocess.CalledProcessError as e:
            raise CommandError(f"Restore failed: {e}")
        except Exception as e:
            raise CommandError(f"Unexpected error: {e}")