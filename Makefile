run-mongo:
	sudo docker-compose up -d
run-redis:
	sudo redis-server /etc/redis/6379.conf

test:
	python -m pytest src/test/test*.py

dbbuilder:
	python scripts/dbbuilder.py -b /home/poldrack/Dropbox/Documents/Vita/autoCV -o -p -i

render_cv:
	python scripts/render_cv.py -r
