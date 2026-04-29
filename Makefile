
PYTHON ?= python

.PHONY: proxy echo echo-fastapi k6 k6-stress

proxy-asyncio:
	$(PYTHON) -m mini_nginx.main_asyncio

proxy-threads:
	$(PYTHON) -m mini_nginx.main_threads

proxy-proces:
	$(PYTHON) -m mini_nginx.main_multiprocessing

echo:
	$(PYTHON) -m mini_nginx.echo.echo_app --port $(PORT)

echo-fastapi:
	$(PYTHON) -m mini_nginx.echo.fastapi_echo --port $(PORT)

k6:
	k6 run k6/load.js

k6-stress:
	k6 run k6/stress.js
