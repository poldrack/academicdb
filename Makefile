test:
	python -m pytest src/test/test*.py

run:
	uv run python manage.py runserver

kill:
	pkill -f "python manage.py runserver"
