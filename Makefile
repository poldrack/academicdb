test:
	DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests -v

test-unit:
	DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/unit -v

test-characterization:
	DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest tests/characterization -v

test-coverage:
	DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run pytest --cov=academic --cov=academicdb_web --cov-report=html --cov-report=term tests

coverage-report:
	DJANGO_SETTINGS_MODULE=academicdb_web.settings.test uv run coverage report --show-missing

run:
	uv run python manage.py runserver

kill:
	pkill -f "python manage.py runserver"

backup:
	uv run python manage.py backup_db

restore-latest:
	@echo "Finding latest backup file..."
	@LATEST_BACKUP=$$(ls -t backups/*.dump backups/*.tar backups/*.sql backups/*.sql.gz 2>/dev/null | head -1); \
	if [ -z "$$LATEST_BACKUP" ]; then \
		echo "Error: No backup files found in backups/ directory"; \
		exit 1; \
	else \
		echo "Latest backup: $$LATEST_BACKUP"; \
		echo "Restoring database from $$LATEST_BACKUP with --clean option..."; \
		uv run python manage.py restore_db "$$LATEST_BACKUP" --clean -y; \
	fi

