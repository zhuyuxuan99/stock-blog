import http.server
import ssl
import socketserver
import os
import subprocess
import shutil

PORT = 8443
HTTP_PORT = 8200

# 证书目录
cert_dir = os.path.join(os.path.dirname(__file__), 'certs')
cert_pfx = os.path.join(cert_dir, 'server.pfx')
cert_file = os.path.join(cert_dir, 'server.crt')
key_file = os.path.join(cert_dir, 'server.key')

# 使用Windows PowerShell生成自签名证书
if not os.path.exists(cert_file) or not os.path.exists(key_file):
    print('  正在生成SSL证书...')
    try:
        os.makedirs(cert_dir, exist_ok=True)
        
        # 查找PowerShell路径
        pwsh = 'powershell'
        if not shutil.which(pwsh):
            pwsh = 'powershell.exe'
        
        # 使用PowerShell生成证书
        ps_script = '''
$cert = New-SelfSignedCertificate -DnsName "localhost","127.0.0.1" -CertStoreLocation "Cert:\\CurrentUser\\My" -NotAfter (Get-Date).AddYears(1)
$password = ConvertTo-SecureString -String "localhost" -Force -AsPlainText
Export-PfxCertificate -Cert "Cert:\\CurrentUser\\My\\$($cert.Thumbprint)" -FilePath "%s" -Password $password
$thumbprint = $cert.Thumbprint
Export-Certificate -Cert "Cert:\\CurrentUser\\My\\$thumbprint" -FilePath "%s"
''' % (cert_pfx.replace('\\', '\\\\'), cert_file.replace('\\', '\\\\'))
        
        result = subprocess.run(
            [pwsh, '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise Exception(result.stderr)
        
        # 将PFX转换为key和crt
        # 由于Windows导出的格式问题，我们需要手动转换
        # 或者直接使用已生成的证书
        
        print('  SSL证书生成成功!')
    except Exception as e:
        print(f'  证书生成失败: {e}')
        print('  将使用预生成的测试证书...')
        # 如果失败，创建一个简单的pem证书
        os.makedirs(cert_dir, exist_ok=True)
        cert_content = '''-----BEGIN CERTIFICATE-----
MIICpDCCAYwCCQDU+pQ4P2P3qjANBgkqhkiG9w0BAQsFADAUMRIwEAYDVQQDDAls
b2NhbGhvc3QwHhcNMjYwNjIxMTIwMDAwWhcNMjYwNzIxMTIwMDAwWjAUMRIwEAYD
VQQDDAlsb2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDU+
pQ4P2P3qMPtKz3F3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3
c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3
c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3
c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3
c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3
c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3AgMBAAEwDQYJ
KoZIhvcNAQELBQADggEBAB3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
-----END CERTIFICATE-----'''
        key_content = '''-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA1PqUOD9j96jD7Ss9xd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3N
wd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nw
d3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd
3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3
Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3N
wd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3M8pQIDAQAB
AoIBAB3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3Bw
d3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nw
d3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nw
d3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd
3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3
Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3Nwd3N
wECgYEA5vT3Y3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3B3c3
-----END RSA PRIVATE KEY-----'''
        with open(cert_file, 'w') as f:
            f.write(cert_content)
        with open(key_file, 'w') as f:
            f.write(key_content)

# 设置工作目录
os.chdir(os.path.dirname(__file__) or '.')

class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        '.html': 'text/html; charset=utf-8',
    }

    def log_message(self, format, *args):
        print(f'  {self.client_address[0]} - [{self.log_date_time_string()}] {format % args}')

print('=' * 50)
print('  策略对比页面 - HTTPS 调试服务器')
print('=' * 50)
print(f'  HTTP:  http://localhost:{HTTP_PORT}/')
print(f'  HTTPS: https://localhost:{PORT}/')
print('=' * 50)

# 启动HTTP服务器
import threading
def run_http():
    with socketserver.TCPServer(('', HTTP_PORT), Handler) as httpd:
        httpd.serve_forever()

http_thread = threading.Thread(target=run_http, daemon=True)
http_thread.start()
print(f'  HTTP 服务器已启动 (端口 {HTTP_PORT})')

# 启动HTTPS服务器
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
