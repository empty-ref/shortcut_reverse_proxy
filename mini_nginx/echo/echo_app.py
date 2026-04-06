import argparse
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=9001)
args = parser.parse_args()


SERVER_PORT = args.port


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # time.sleep(3)
        body = f'echo from {SERVER_PORT} {self.path}\n'.encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', '0'))
        body_in = self.rfile.read(content_length)
        body = f'echo from {SERVER_PORT} POST: '.encode() + body_in + b'\n'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        body = f'echo from {SERVER_PORT} {self.path}\n'.encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', SERVER_PORT), Handler).serve_forever()
