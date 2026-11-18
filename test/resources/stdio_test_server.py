# SPDX-License-Identifier: MIT
"""Minimal framed JSON-RPC peer for stdio transport lifecycle tests."""

import json
import sys
import time


def send(payload):
    body = json.dumps(payload).encode()
    sys.stdout.buffer.write(b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    sys.stdout.buffer.flush()


send({"jsonrpc": "2.0", "method": "ready", "params": {}})
while True:
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit(0)
        if line == b"\r\n":
            break
        key, value = line.decode().split(":", 1)
        headers[key.lower()] = value.strip()
    message = json.loads(sys.stdin.buffer.read(int(headers["content-length"])))
    if message["method"] == "exit":
        if sys.argv[1] == "uncooperative":
            time.sleep(60)
        break
    if message["method"] == "crash":
        sys.exit(1)
    send({"jsonrpc": "2.0", "id": message["id"], "result": None})
