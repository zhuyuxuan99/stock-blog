import os
import sys
import subprocess

# 先运行数据获取脚本
print('=' * 50)
print('  步骤 1: 获取最新股票数据')
print('=' * 50)

result = subprocess.run([sys.executable, 'fetch_stock_prices.py'], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print(result.stderr)

# 然后启动 HTTPS 服务器
print()
print('=' * 50)
print('  步骤 2: 启动 HTTPS 服务器')
print('=' * 50)

import http.server
import ssl
import socketserver

PORT = 8443
HTTP_PORT = 8080

cert_file = os.path.join(os.path.dirname(__file__), 'certs', 'server.crt')
key_file = os.path.join(os.path.dirname(__file__), 'certs', 'server.key')

os.chdir(os.path.dirname(__file__) or '.')

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f'  {self.client_address[0]} - [{self.log_date_time_string()}] {format % args}')

    def extensions_map(self):
        return {
            **http.server.SimpleHTTPRequestHandler.extensions_map,
            '.html': 'text/html; charset=utf-8',
        }

print(f'  HTTP:  http://localhost:{HTTP_PORT}/')
print(f'  HTTPS: https://localhost:{PORT}/')
print('=' * 50)

import threading
def run_http():
    with socketserver.TCPServer(('', HTTP_PORT), Handler) as httpd:
        httpd.serve_forever()

http_thread = threading.Thread(target=run_http, daemon=True)
http_thread.start()
print(f'  HTTP 服务器已启动 (端口 {HTTP_PORT})')

with socketserver.TCPServer(('', PORT), Handler) as httpd:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    print(f'  HTTPS 服务器已启动 (端口 {PORT})')
    print()
    print('按 Ctrl+C 停止服务器')
    print('-' * 50)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n服务器已停止')
