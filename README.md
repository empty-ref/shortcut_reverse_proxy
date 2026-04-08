# mini_nginx

## Install req

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements-dev.txt
```

## Run echo

Start two echo-upstreams:

```bash
make echo PORT=9001
make echo PORT=9002
```

FastAPI echo-upstreams:

```bash
make echo-fastapi PORT=9001
make echo-fastapi PORT=9002
```

Run proxy:
Proxy config is loaded from `config.yml` in the project root.

```bash
make proxy
```

## Test requests

single request:

```bash
curl -v "http://127.0.0.1:8080/"
```

several request:

```bash
for i in {1..10}; do curl -i -s http://127.0.0.1:8080/$i & done; wait
```

## k6 testing

Run:

```bash
make k6
```
