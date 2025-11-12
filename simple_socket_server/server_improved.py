#!/usr/bin/env python3
# simple_socket_server_improved.py
# Improvements to implement:
# 1. Correct headers and body reading and parsing
# 2. Set limit for headers and body size
# 3. Build proper HTTP response (handle POST request if Content-Length header exists)
# 4. Set a socket-level timeout for slow connections
# 5. Add simple routing (like /, /ping and POST /echo)
# 6. Implement basic error handling so server doesn't crash on bad inputs
# 7. Make it concurrent (right now server cannot accept other clients while handle_request runs)

import socket
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import json
from json import JSONDecodeError

HOST = '127.0.0.1'
PORT = 8000
BACKLOG = 5
RECV_BLOCK = 4096
MAX_HEADER_BYTES = 16 * 1024  # max sum of header bytes (16KB)
MAX_BODY_BYTES = 1 * 1024 * 1024  # max body size (1MB)
CONN_TIMEOUT = 5  # seconds


# read headers and body from request and return them as a tuple
def read_until_double_crlf(conn):
    '''Read bytes until the end of the HTTP header section (that marker is empty line, a sequence of CRLF CRLF (\r\n\r\n))
    Return (header_bytes, leftover_bytes) - leftover may contain part of the body.'''
    data = bytearray()
    while b'\r\n\r\n' not in data:
        # read up to RECV_BLOCK bytes from TCP stream
        chunk = conn.recv(RECV_BLOCK)
        if not chunk:  # recv() returns b"" on orderly disconnect
            break
        data.extend(chunk)
        if len(data) > MAX_HEADER_BYTES:  # immediately stop reading if headers exceed safe size
            raise ValueError('Headers too large')
    # split into header part and leftover after first CRLFCRLF. Using maxsplit=1 ensures we capture only the first boundary
    parts = data.split(b'\r\n\r\n', 1)
    headers_part = parts[0] if parts else b''
    leftover = parts[1] if len(parts) > 1 else b''
    return headers_part, leftover


def parse_headers(headers_bytes):
    # for demo/debugging purpose we use "replace" which ensures that invalid byte sequences don’t raise exceptions (they get a replacement character)
    text = headers_bytes.decode('utf-8', errors='replace')
    lines = text.split('\r\n')
    if not lines:
        raise ValueError('Empty request')
    request_line = lines[0]
    header_lines = lines[1:]
    headers = {}
    for line in header_lines:
        if not line:
            continue
        if ':' not in line:
            continue
        # split only on first ':', because header values can contain ':'
        name, value = line.split(':', 1)
        headers[name.strip().lower()] = value.strip()
    return request_line, headers


def read_exact(conn, initial_data: bytes, nbytes: int):
    '''Read exactly nbytes bytes, using initial_data as already-read fragment'''
    data = bytearray(initial_data)
    # combine initial data may be leftover already read after the headers with subsequent recv() calls
    while len(data) < nbytes:
        chunk = conn.recv(min(RECV_BLOCK, nbytes - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_BODY_BYTES:
            raise ValueError('Body too large')
    return bytes(data)


def build_response(status_code: int, body: bytes, content_type='text/html; charset=utf-8'):
    reason = {200: 'OK', 400: 'Bad Request', 404: 'Not Found',
              413: 'Payload Too Large', 500: 'Internal Server Error'}.get(status_code, 'OK')
    header_lines = [
        f'HTTP/1.1 {status_code} {reason}',
        f'Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')}',
        f'Content-Type: {content_type}',
        f'Content-Length: {len(body)}',
        'Connection: close',
        '',
        ''
    ]
    header_bytes = '\r\n'.join(header_lines).encode('utf-8')
    response = header_bytes + body
    return response


def handle_connection(conn, addr):
    try:
        # Set a socket-level timeout so subsequent blocking recv() calls raise socket.timeout if client is too slow or stalls
        conn.settimeout(CONN_TIMEOUT)
        headers_part, leftover = read_until_double_crlf(conn)
        request_line, headers = parse_headers(headers_part)

        # request line format: METHOD PATH PROTOCOL
        parts = request_line.split()
        if len(parts) < 3:
            response = build_response(400, b'<h1>400 Bad Request</h1>')
            conn.sendall(response)
            return

        method, raw_path, protocol = parts[0], parts[1], parts[2]
        parsed = urlparse(raw_path)
        path = parsed.path
        query = parse_qs(parsed.query)

        body = b''
        if method.upper() in ('POST', 'PUT', 'PATCH'):
            content_length = int(headers.get('content-length', '0') or '0')
            if content_length > MAX_BODY_BYTES:
                response = build_response(
                    413, b'<h1>413 Payload Too Large</h1>')
                conn.sendall(response)
            # leftover may already include part of the body
            body = read_exact(conn, leftover, content_length)

        # Simple routing
        if method.upper() == 'GET' and path == '/':
            html = f'<html><body><h1>Hello from improved server!</h1><p>{datetime.now(timezone.utc)} UTC</p></body></html>'
            response = build_response(200, html.encode('utf-8'))
            conn.sendall(response)
            return

        if method.upper() == 'GET' and path == '/ping':
            response = build_response(
                200, b'pong', content_type='text/plain; charset=utf-8')
            conn.sendall(response)
            return

        if method.upper() == 'POST' and path == '/echo':
            # echo headers and a preview of the body in simple HTML (for testing)
            body_preview = body.decode('utf-8', errors='replace')[:1000]
            html = '<html><body>'
            html += '<h1>/echo</h1>'
            html += '<h2>Received headers</h2><ul>'
            for k, v in headers.items():
                html += f'<li>{k}: {v}</li>'
            html += f'</ul><h2>Body (first 1000 chars)</h2><pre>{body_preview}</pre>'
            html += '</body></html>'
            response = build_response(200, html.encode('utf-8'))
            conn.sendall(response)
            return

        if method.upper() == 'POST' and path == '/echo-json':
            content_type = headers.get('content-type', '')
            if 'application/json' not in content_type:
                # Not JSON - respond 400 or 415. Here we use 400 for simplicity
                msg = b'{"error":"expected Content-Type: application/json"}'
                response = build_response(
                    400, msg, content_type='application/json; charset=utf-8')
                conn.sendall(response)
                return

            # body is bytes - decode or pass directly to json.loads after decoding
            try:
                text = body.decode('utf-8')  # decode bytes to string
            except Exception:
                response = build_response(
                    400, b'{"error":":"invalid utf-8 in request body"}', content_type='application/json; charset=utf-8')
                conn.sendall(response)
                return

            try:
                # parse JSON -> Python object (dict/list)
                parsed = json.loads(text)
            except JSONDecodeError as e:
                # invalid JSON -> 400 Bad Request
                err_obj = {'error': 'invalid json', 'detail': str(e)}
                err_bytes = json.dumps(
                    err_obj, ensure_ascii=False).encode('utf-8')
                response = build_response(
                    400, err_bytes, content_type='application/json; charset=utf-8')
                conn.sendall(response)
                return

            # No errors - Build response object: include received and some meta headers
            resp_obj = {
                'received': parsed,
                'meta': {
                    'content-length': headers.get('content-length', ''),
                    'content-type': headers.get('content-type', '')
                }
            }
            resp_bytes = json.dumps(
                resp_obj, ensure_ascii=False).encode('utf-8')
            response = build_response(
                200, resp_bytes, content_type='application/json; charset=utf-8')
            conn.sendall(response)
            return

        # default 404
        response = build_response(404, b'<h1>404 Not Found</h1>')
        conn.sendall(response)

    except socket.timeout:
        try:
            conn.sendall(build_response(400, b'<h1>400 Request Timeout</h1>'))
        except Exception:
            pass
    except ValueError as ve:
        # our code may raise 'Headers too large' or 'Body too large'
        try:
            conn.sendall(build_response(
                413, f'<h1>413</h1><p>{ve}</p>'.encode('utf-8')))
        except Exception:
            pass
    except Exception as e:
        # Prevent an unhandled exception from killing the whole server
        try:
            conn.sendall(build_response(
                500, b'<h1>500 Internal Server Error</h1>'))
        except Exception:
            pass
        print('Unhandled error while handling connection:', e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(BACKLOG)
        print(f'Listening on http://{HOST}:{PORT} ...')
        try:
            while True:
                conn, addr = s.accept()
                # This simple server still handles each connection synchronously, accept() and recv() are blocking
                print('Accepted connection from: ', addr)
                handle_connection(conn, addr)
        except KeyboardInterrupt:
            print('\nShutting down server.')


if __name__ == '__main__':
    run()
