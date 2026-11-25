import pytest

from coding_tutor.live import server


class FakeHandler:
    client_address = ("203.0.113.9", 51234)

    def log_date_time_string(self):
        return "25/Nov/2026 10:00:00"


def test_print_request_prints_time_request_and_status_without_the_address(capsys):
    server.print_request(FakeHandler(), '"%s" %s %s', "POST /api/v1/events HTTP/1.1", "202", "17")
    out = capsys.readouterr().out
    assert out == '[25/Nov/2026 10:00:00] "POST /api/v1/events HTTP/1.1" 202 17\n'
    assert "203.0.113.9" not in out


def test_request_handler_is_quiet_unless_asked():
    assert server.request_handler(False) is server.QuietHandler
    assert server.request_handler(True) is server.LoggingHandler
    assert server.LoggingHandler.log_message is server.print_request


@pytest.mark.parametrize(("argv", "log"), [([], False), (["--log"], True)])
def test_parse_args_log_flag(argv, log):
    assert server.parse_args(argv).log is log


def test_parse_args_rejects_unknown_flags():
    with pytest.raises(SystemExit):
        server.parse_args(["--lo"])  # no abbreviations
