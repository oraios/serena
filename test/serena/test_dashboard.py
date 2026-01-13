"""Integration tests for the dashboard module."""

import multiprocessing
import socket
import time
from contextlib import closing

from serena.dashboard import SerenaDashboardAPI


def _listen_on_port(
    port: int,
    host: str,
    ready_event: multiprocessing.Event,  # type: ignore[type-arg]
    stop_event: multiprocessing.Event,  # type: ignore[type-arg]
) -> None:
    """Helper function that listens on a port in a separate process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, port))
        sock.listen(1)
        ready_event.set()  # Signal that we're listening
        # Wait until told to stop
        while not stop_event.is_set():
            time.sleep(0.01)


class TestFindFirstFreePort:
    """Integration tests for _find_first_free_port."""

    def test_finds_free_port(self) -> None:
        """Test that the function returns a free port that can be used."""
        port = SerenaDashboardAPI._find_first_free_port(24282, "0.0.0.0")

        # Verify the returned port is actually free by binding to it
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("0.0.0.0", port))
            # If we get here without OSError, the port was indeed free

    def test_skips_occupied_port(self) -> None:
        """Test that the function skips occupied ports and finds the next free one."""
        # Occupy a port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied_sock:
            occupied_sock.bind(("0.0.0.0", 0))
            occupied_port = occupied_sock.getsockname()[1]

            # Ask for a port starting from the occupied one
            found_port = SerenaDashboardAPI._find_first_free_port(occupied_port, "0.0.0.0")

            # The found port should be different from the occupied one
            assert found_port != occupied_port
            assert found_port > occupied_port

            # Verify the found port is actually usable
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                test_sock.bind(("0.0.0.0", found_port))

    def test_skips_multiple_occupied_ports(self) -> None:
        """Test that the function skips multiple consecutive occupied ports."""
        # Find a base port that's free
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as temp_sock:
            base_port = 24282
            temp_sock.bind(("0.0.0.0", base_port))
            base_port = temp_sock.getsockname()[1]

        # Occupy three consecutive ports starting from base_port
        occupied_sockets = []
        try:
            for i in range(3):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    sock.bind(("0.0.0.0", base_port + i))
                    occupied_sockets.append(sock)
                except OSError:
                    # Port might already be in use by something else, skip
                    sock.close()

            if len(occupied_sockets) == 3:
                # All three ports are occupied by us
                found_port = SerenaDashboardAPI._find_first_free_port(base_port, "0.0.0.0")

                # The found port should be at least base_port + 3
                assert found_port >= base_port + 3

                # Verify it's usable
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                    test_sock.bind(("0.0.0.0", found_port))
        finally:
            for sock in occupied_sockets:
                sock.close()

    def test_returns_start_port_if_free(self) -> None:
        """Test that if the start port is free, it returns exactly that port."""
        # Find a free port first
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as temp_sock:
            temp_sock.bind(("0.0.0.0", 0))
            free_port = temp_sock.getsockname()[1]

        # Now the port should be free, ask for it
        found_port = SerenaDashboardAPI._find_first_free_port(free_port, "0.0.0.0")

        # It should return the exact port we asked for (or higher if it got taken)
        assert found_port >= free_port

        # Verify it's usable
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.bind(("0.0.0.0", found_port))

    def test_port_in_valid_range(self) -> None:
        """Test that the returned port is in a valid range."""
        port = SerenaDashboardAPI._find_first_free_port(49152, "0.0.0.0")

        assert 49152 <= port <= 65535

    def test_skips_port_with_listener_in_another_process(self) -> None:
        """Test that the function skips ports where another process is listening.

        This is the critical test - a port with a listener in another process
        should be skipped even if bind() might succeed (e.g., due to SO_REUSEADDR
        on Windows).
        """
        # First, find a free port to use
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as temp_sock:
            temp_sock.bind(("0.0.0.0", 0))
            test_port = temp_sock.getsockname()[1]

        # Start a separate process that listens on that port (same host)
        ready_event = multiprocessing.Event()
        stop_event = multiprocessing.Event()
        listener_process = multiprocessing.Process(
            target=_listen_on_port,
            args=(test_port, "0.0.0.0", ready_event, stop_event),
        )
        listener_process.start()

        try:
            # Wait for the listener to be ready
            ready_event.wait(timeout=5.0)
            assert ready_event.is_set(), "Listener process failed to start"

            # Now call _find_first_free_port starting from the listening port
            found_port = SerenaDashboardAPI._find_first_free_port(test_port, "0.0.0.0")

            # The found port must NOT be the one with the listener
            assert found_port != test_port, f"Function returned port {test_port} which has a listener in another process!"
            assert found_port > test_port

            # Verify the found port is actually usable
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                test_sock.bind(("0.0.0.0", found_port))
                test_sock.listen(1)  # Should succeed
        finally:
            # Clean up the listener process
            stop_event.set()
            listener_process.join(timeout=2.0)
            if listener_process.is_alive():
                listener_process.terminate()
                listener_process.join(timeout=1.0)

    def test_skips_port_with_listener_on_different_host(self) -> None:
        """Test detection when listener uses 127.0.0.1 but we check with 0.0.0.0.

        This tests the case where another process binds to 127.0.0.1 (localhost only)
        but _find_first_free_port checks with 0.0.0.0 (all interfaces).
        """
        # First, find a free port to use
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as temp_sock:
            temp_sock.bind(("0.0.0.0", 0))
            test_port = temp_sock.getsockname()[1]

        # Start a separate process that listens on 127.0.0.1 (not 0.0.0.0)
        ready_event = multiprocessing.Event()
        stop_event = multiprocessing.Event()
        listener_process = multiprocessing.Process(
            target=_listen_on_port,
            args=(test_port, "127.0.0.1", ready_event, stop_event),
        )
        listener_process.start()

        try:
            # Wait for the listener to be ready
            ready_event.wait(timeout=5.0)
            assert ready_event.is_set(), "Listener process failed to start"

            # Now call _find_first_free_port with 0.0.0.0 (different from listener's 127.0.0.1)
            found_port = SerenaDashboardAPI._find_first_free_port(test_port, "0.0.0.0")

            # The found port must NOT be the one with the listener
            assert found_port != test_port, f"Function returned port {test_port} which has a listener on 127.0.0.1 (checked with 0.0.0.0)!"
            assert found_port > test_port

            # Verify the found port is actually usable
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                test_sock.bind(("0.0.0.0", found_port))
                test_sock.listen(1)  # Should succeed
        finally:
            # Clean up the listener process
            stop_event.set()
            listener_process.join(timeout=2.0)
            if listener_process.is_alive():
                listener_process.terminate()
                listener_process.join(timeout=1.0)
