"""
Django management command to backup the PostgreSQL database
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Backup the PostgreSQL database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='backups',
            help='Directory to store backups (default: backups/)'
        )
        parser.add_argument(
            '--format',
            choices=['sql', 'custom', 'tar'],
            default='custom',
            help='Backup format: sql (plain text), custom (compressed), tar'
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compress SQL output with gzip (only for sql format)'
        )

    def handle(self, *args, **options):
        # Get database configuration
        db_config = settings.DATABASES['default']

        if db_config['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('This command only works with PostgreSQL databases')

        # Create backup directory if it doesn't exist
        backup_dir = Path(options['output_dir'])
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        db_name = db_config['NAME']

        # Set file extension based on format
        ext_map = {
            'sql': '.sql',
            'custom': '.dump',
            'tar': '.tar'
        }
        extension = ext_map[options['format']]
        if options['format'] == 'sql' and options['compress']:
            extension += '.gz'

        backup_file = backup_dir / f"{db_name}_backup_{timestamp}{extension}"

        # Build pg_dump command
        pg_dump_cmd = [
            'pg_dump',
            '-h', db_config.get('HOST', 'localhost'),
            '-p', str(db_config.get('PORT', 5432)),
            '-U', db_config.get('USER', 'postgres'),
            '-d', db_name,
            '--no-password',
            '--verbose',
        ]

        # Add format-specific options
        if options['format'] == 'custom':
            pg_dump_cmd.extend(['-Fc', '-f', str(backup_file)])
        elif options['format'] == 'tar':
            pg_dump_cmd.extend(['-Ft', '-f', str(backup_file)])
        else:  # sql format
            if options['compress']:
                pg_dump_cmd.append('-O')  # No owner
            else:
                pg_dump_cmd.extend(['-f', str(backup_file)])

        # Set PGPASSWORD environment variable if password is configured
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']

        try:
            self.stdout.write(f"Starting backup of database '{db_name}'...")
            self.stdout.write(f"Backup file: {backup_file}")

            if options['format'] == 'sql' and options['compress']:
                # Pipe pg_dump output through gzip
                with open(backup_file, 'wb') as f:
                    pg_dump = subprocess.Popen(
                        pg_dump_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env
                    )
                    gzip = subprocess.Popen(
                        ['gzip', '-9'],
                        stdin=pg_dump.stdout,
                        stdout=f,
                        stderr=subprocess.PIPE
                    )
                    pg_dump.stdout.close()
                    gzip_out, gzip_err = gzip.communicate()
                    pg_dump_out, pg_dump_err = pg_dump.communicate()

                    if pg_dump.returncode != 0:
                        raise CommandError(f"pg_dump failed: {pg_dump_err.decode()}")
                    if gzip.returncode != 0:
                        raise CommandError(f"gzip failed: {gzip_err.decode()}")
            else:
                # Run pg_dump directly
                result = subprocess.run(
                    pg_dump_cmd,
                    capture_output=True,
                    text=True,
                    env=env
                )

                if result.returncode != 0:
                    raise CommandError(f"Backup failed: {result.stderr}")

            # Get file size
            file_size = backup_file.stat().st_size / (1024 * 1024)  # Convert to MB

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Backup completed successfully!\n"
                    f"  File: {backup_file}\n"
                    f"  Size: {file_size:.2f} MB"
                )
            )

            # Show restore command
            self.stdout.write("\nTo restore this backup, use:")
            if options['format'] == 'custom':
                self.stdout.write(f"  pg_restore -h localhost -U {db_config.get('USER')} -d {db_name} {backup_file}")
            elif options['format'] == 'tar':
                self.stdout.write(f"  pg_restore -h localhost -U {db_config.get('USER')} -d {db_name} -Ft {backup_file}")
            else:  # sql format
                if options['compress']:
                    self.stdout.write(f"  gunzip -c {backup_file} | psql -h localhost -U {db_config.get('USER')} -d {db_name}")
                else:
                    self.stdout.write(f"  psql -h localhost -U {db_config.get('USER')} -d {db_name} < {backup_file}")

        except subprocess.CalledProcessError as e:
            raise CommandError(f"Backup failed: {e}")
        except Exception as e:
            raise CommandError(f"Unexpected error: {e}")