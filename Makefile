run-mongo:
	sudo docker-compose up -d
run-redis:
	sudo redis-server /etc/redis/6379.conf

test:
	python -m pytest src/test/test*.py

