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
from datetime import datetime
from urllib.parse import urlparse, parse_qs

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
    while len(data) < nbytes:
        chunk = conn.recv(min(RECV_BLOCK, nbytes - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_BODY_BYTES:
            raise ValueError('Body too large')
    return bytes(data)
