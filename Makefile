test:
	uv run python -m pytest tests

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

