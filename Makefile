run-mongo-local:
	sudo docker-compose up -d

test:
	python -m pytest src/test/test*.py

install:
	poetry build && pip install -U .
