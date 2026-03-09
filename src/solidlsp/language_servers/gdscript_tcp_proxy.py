"""
TCP transport adapter for Godot's GDScript language server.

Godot exposes its language server via TCP (default: 127.0.0.1:6005), while SolidLSP
expects a stdio-speaking server process. This module bridges stdio <-> TCP.
"""

import argparse
import socket
import sys
import threading

BUFFER_SIZE = 64 * 1024


def _pipe_stdin_to_socket(sock: socket.socket) -> None:
    stdin = sys.stdin.buffer
    try:
        while True:
            data = stdin.read(BUFFER_SIZE)
            if not data:
                break
            sock.sendall(data)
    except (BrokenPipeError, OSError):
        # The remote endpoint may close first; that's expected during shutdown.
        pass
    finally:
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _pipe_socket_to_stdout(sock: socket.socket) -> None:
    stdout = sys.stdout.buffer
    try:
        while True:
            data = sock.recv(BUFFER_SIZE)
            if not data:
                break
            stdout.write(data)
            stdout.flush()
    except OSError:
        pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bridge stdio to Godot's TCP-based GDScript LSP endpoint.")
    parser.add_argument("--host", default="127.0.0.1", help="Godot LSP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=6005, help="Godot LSP port (default: 6005)")
    parser.add_argument("--connect-timeout", type=float, default=10.0, help="TCP connect timeout in seconds (default: 10)")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        sock = socket.create_connection((args.host, args.port), timeout=args.connect_timeout)
    except OSError as e:
        print(f"Failed to connect to Godot LSP at {args.host}:{args.port}: {e}", file=sys.stderr)
        return 2

    sock.settimeout(None)
    stdin_thread = threading.Thread(target=_pipe_stdin_to_socket, args=(sock,), name="gdscript-stdin-to-tcp", daemon=True)
    stdout_thread = threading.Thread(target=_pipe_socket_to_stdout, args=(sock,), name="gdscript-tcp-to-stdout", daemon=True)

    stdin_thread.start()
    stdout_thread.start()

    # Main thread follows server output lifecycle: once remote closes, we exit.
    stdout_thread.join()
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()
    stdin_thread.join(timeout=0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
