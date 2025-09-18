HOMEDIR=$(HOME)
DBDIR = ${HOMEDIR}/.cache/academicdb

IMAGE_VERSION = v1.0.1

# Load environment variables from .env file if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

# Determine which Docker image to use based on environment variable
ifeq ($(USE_LOCAL_DOCKER_IMAGE),true)
    DOCKER_IMAGE = academicdb:latest
else
    DOCKER_IMAGE = poldrack/academicdb2:${IMAGE_VERSION}
endif

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

# Docker commands
docker-full-restart: docker-clean docker-rm-db docker-build docker-run-orcid
docker-rebuild: docker-clean docker-build docker-run-orcid

docker-rm-db:
	-rm /Users/poldrack/.cache/academicdb/*

docker-build:
	docker build -t academicdb:latest .

docker-buildx:
	docker buildx build --platform linux/amd64,linux/arm64 -t poldrack/academicdb2:latest -t poldrack/academicdb2:${IMAGE_VERSION} --push .

docker-run:
	docker run -d \
		--name academicdb \
		-p 8000:8000 \
		-v ${DBDIR}:/app/data \
		-v $(PWD)/data:/app/datafiles \
		-e SQLITE_PATH=/app/data/db.sqlite3 \
		academicdb:latest

docker-run-admin:
	docker run -d \
		--name academicdb \
		-p 8000:8000 \
		-v ${DBDIR}:/app/data \
		-v $(PWD)/data:/app/datafiles \
		-e SQLITE_PATH=/app/data/db.sqlite3 \
		-e DJANGO_SUPERUSER_USERNAME=admin \
		-e DJANGO_SUPERUSER_EMAIL=admin@example.com \
		-e DJANGO_SUPERUSER_PASSWORD=secure_password \
		academicdb:latest

check_orcid:
	@if [ -z "$(ORCID_CLIENT_ID)" ] || [ -z "$(ORCID_CLIENT_SECRET)" ]; then \
		echo "❌ Error: ORCID credentials required"; \
		echo ""; \
		if [ -f .env ]; then \
			echo "Found .env file but ORCID credentials are missing or empty."; \
			echo "Please add to your .env file:"; \
			echo "  ORCID_CLIENT_ID=your-actual-client-id"; \
			echo "  ORCID_CLIENT_SECRET=your-actual-client-secret"; \
		else \
			echo "Please create a .env file with:"; \
			echo "  ORCID_CLIENT_ID=your-actual-client-id"; \
			echo "  ORCID_CLIENT_SECRET=your-actual-client-secret"; \
		fi; \
		echo ""; \
		echo "Get credentials from: https://orcid.org/developer-tools"; \
		exit 1; \
	else \
		echo "✅ ORCID credentials found."; \
	fi

docker-run-orcid: check_orcid
	@echo "🚀 Starting container with ORCID authentication..."
	@echo "   Docker Image: $(DOCKER_IMAGE)"
	@echo "   ORCID Client ID: $(ORCID_CLIENT_ID)"
	@mkdir -p ${DBDIR}
	@mkdir -p $(PWD)/backups
	docker run -d \
		--name academicdb \
		-p 8000:8000 \
		-v ${DBDIR}:/app/data \
		-v $(PWD)/backups:/app/backups \
		-v $(PWD)/data:/app/datafiles \
		-e SQLITE_PATH=/app/data/db.sqlite3 \
		-e DEBUG=false \
		-e SECRET_KEY=stable-key-for-local-development-do-not-use-in-production \
		-e ORCID_CLIENT_ID=$(ORCID_CLIENT_ID) \
		-e ORCID_CLIENT_SECRET=$(ORCID_CLIENT_SECRET) \
		-e SCOPUS_API_KEY=$(SCOPUS_API_KEY) \
		-e SCOPUS_INST_TOKEN=$(SCOPUS_INST_TOKEN) \
		${DOCKER_IMAGE}

docker-stop:
	docker stop academicdb

docker-remove:
	docker rm academicdb

docker-clean:
	docker stop academicdb || true
	docker rm academicdb || true

docker-logs:
	docker logs academicdb

docker-shell:
	docker exec -it academicdb bash

docker-restart:
	docker restart academicdb

docker-status:
	docker ps | grep academicdb || echo "Container not running"

docker-setup-orcid:
	@echo "🔧 ORCID Setup Helper"
	@echo ""
	@echo "1. Go to: https://orcid.org/developer-tools"
	@echo "2. Create a new application with:"
	@echo "   - Name: Academic Database"
	@echo "   - Website: http://127.0.0.1:8000"
	@echo "   - Redirect URI: http://127.0.0.1:8000/accounts/orcid/login/callback/"
	@echo "3. Copy your Client ID and Client Secret"
	@echo "4. Run:"
	@echo "   export ORCID_CLIENT_ID=your-client-id"
	@echo "   export ORCID_CLIENT_SECRET=your-client-secret"
	@echo "   make docker-clean && make docker-run-orcid"

