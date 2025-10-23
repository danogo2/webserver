import socket
from datetime import datetime, timezone

HOST = '127.0.0.1'  # localhost
PORT = 8000


def handle_request(conn):
    request = conn.recv(4096).decode('utf-8', errors='ignore')
    print('--- request start ---')
    print(request.splitlines()[0])  # show first line ('GET / HTTP/1.1')
    print('--- request end ---\n')

    # Simple HTML response (without any routing)
    body = f'<html><body><h1>Hello from a simple socket server!</h1><p>{datetime.now(timezone.utc)}</p></body></html>'
    response_lines = ['HTTP/1.1 200 OK', f'Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}',
                      'Content-Type: text/html; charset=utf-8', f'Content-Length: {len(body.encode('utf-8'))}', 'Connection: close', '', body]
    response = '\r\n'.join(response_lines).encode('utf-8')
    conn.sendall(response)


def run():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)
        print(f'Listening on http://{HOST}:{PORT} ...')
        while True:
            conn, addr = s.accept()
            print(f'Client connection: {conn}')
            print(f'Client address: {addr}')
            with conn:
                handle_request(conn)


if __name__ == '__main__':
    run()
