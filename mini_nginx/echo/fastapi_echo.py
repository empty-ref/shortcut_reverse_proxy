import argparse

import uvicorn
from fastapi import FastAPI, Request, Response

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=9010)
args = parser.parse_args()

SERVER_PORT = args.port
app = FastAPI(title='mini-nginx echo')


@app.get('/{path:path}')
async def echo_get(path: str, request: Request) -> Response:
    query = f'?{request.url.query}' if request.url.query else ''
    body = f'echo from {SERVER_PORT} /{path}{query}\n'
    return Response(content=body.encode(), media_type='text/plain')


@app.post('/{path:path}')
async def echo_post(path: str, request: Request) -> Response:
    payload = await request.body()
    body = f'echo from {SERVER_PORT} POST /{path}: '.encode() + payload + b'\n'
    return Response(content=body, media_type='text/plain')


@app.head('/{path:path}')
async def echo_head(path: str, request: Request) -> Response:
    query = f'?{request.url.query}' if request.url.query else ''
    body = f'echo from {SERVER_PORT} /{path}{query}\n'.encode()
    return Response(content=b'', headers={'Content-Length': str(len(body))})


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=SERVER_PORT, log_level='info')
