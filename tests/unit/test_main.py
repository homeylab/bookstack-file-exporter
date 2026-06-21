"""Tests for __main__.main() return type and sys.exit wiring."""
# pylint: disable=missing-class-docstring,missing-function-docstring
import sys
from unittest.mock import patch

from bookstack_file_exporter import run
from bookstack_file_exporter.__main__ import main

# Real argv so main() runs the real get_args -> get_log_level -> resolve_log_format
# -> build_handler chain. Only the genuine boundaries are patched per test:
# run.entrypoint (network + disk) and logging.basicConfig (global root logger).
_ARGV = ("--log-format", "text")


class TestMainReturnType:
    def test_main_returns_int(self):
        """main() must return an int so sys.exit() gets a proper code."""
        with patch.object(run, "entrypoint", return_value=0), \
             patch("bookstack_file_exporter.__main__.logging.basicConfig"):
            result = main(_ARGV)
        assert isinstance(result, int)

    def test_main_propagates_entrypoint_return_value(self):
        """main() must return exactly what entrypoint() returns."""
        sentinel = 42
        with patch.object(run, "entrypoint", return_value=sentinel), \
             patch("bookstack_file_exporter.__main__.logging.basicConfig"):
            result = main(_ARGV)
        assert result == sentinel


class TestSysExitWiring:
    def test_sys_exit_receives_main_return_value(self):
        """sys.exit(main()) must propagate entrypoint's int to the process exit code."""
        sentinel = 7
        with patch.object(run, "entrypoint", return_value=sentinel), \
             patch("bookstack_file_exporter.__main__.logging.basicConfig"), \
             patch("sys.exit") as mock_exit:
            # Simulate the guard block: sys.exit(main())
            sys.exit(main(_ARGV))
        mock_exit.assert_called_once_with(sentinel)

    def test_main_failure_code_reaches_sys_exit(self):
        """A failure code (1) from entrypoint must reach sys.exit unchanged."""
        with patch.object(run, "entrypoint", return_value=1), \
             patch("bookstack_file_exporter.__main__.logging.basicConfig"), \
             patch("sys.exit") as mock_exit:
            sys.exit(main(_ARGV))
        mock_exit.assert_called_once_with(1)
