import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "write_lp", Path(__file__).parents[1] / "examples" / "grafana-influxdb3" / "write_lp.py"
)
writer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(writer)


class Server:
    def __init__(self, script):
        self.script = list(script)  # one status per request; the last repeats
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append(
                    {"path": self.path, "auth": self.headers.get("Authorization"), "body": body}
                )
                status = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def server():
    created = []

    def make(*script):
        s = Server(script or [204])
        created.append(s)
        return s

    yield make
    for s in created:
        s.close()


def lp_file(tmp_path, count, newline=b"\n"):
    path = tmp_path / "observations.lp"
    path.write_bytes(newline.join(f"m,t=a v={i} {i}".encode() for i in range(count)) + newline)
    return path


def run(path, s, **kw):
    return writer.write_file(path, s.url, "db", token="secret-token", sleep=lambda x: None, **kw)


def test_batches_are_bounded_authenticated_and_all_or_nothing(tmp_path, server):
    s = server()
    receipt = run(lp_file(tmp_path, 25), s, batch_lines=10)
    assert receipt["complete"] and receipt["batches"] == 3
    assert [r["body"].count(b"\n") for r in s.requests] == [10, 10, 5]
    assert all(r["auth"] == "Bearer secret-token" for r in s.requests)
    assert "precision=nanosecond" in s.requests[0]["path"]
    assert "accept_partial=false" in s.requests[0]["path"]
    assert "secret-token" not in (tmp_path / "observations.lp.write-receipt.json").read_text()


def test_resume_skips_acknowledged_batches_for_the_same_payload(tmp_path, server):
    path = lp_file(tmp_path, 25)
    first = server(204, 400)  # batch 0 succeeds, batch 1 is rejected
    receipt = run(path, first, batch_lines=10)
    assert not receipt["complete"] and receipt["failed_batch"] == 1
    assert receipt["acknowledged_batches"] == [0] and len(first.requests) == 2
    second = server(204)
    receipt = run(path, second, batch_lines=10)
    assert receipt["complete"] and len(second.requests) == 2  # only batches 1 and 2 are sent


def test_changed_payload_ignores_the_old_receipt(tmp_path, server):
    path = lp_file(tmp_path, 5)
    run(path, server(), batch_lines=10)
    path.write_bytes(path.read_bytes() + b"m,t=a v=99 99\n")
    s = server()
    run(path, s, batch_lines=10)
    assert len(s.requests) == 1  # full replay, safe because point identity is stable


def test_server_errors_are_retried_but_rejections_are_not(tmp_path, server):
    flaky = server(503, 503, 204)
    assert run(lp_file(tmp_path, 3), flaky, batch_lines=10, retries=2)["complete"]
    assert len(flaky.requests) == 3
    rejected = server(400)
    (tmp_path / "other").mkdir()
    receipt = run(lp_file(tmp_path / "other", 3), rejected, batch_lines=10, retries=3)
    assert (
        not receipt["complete"] and len(rejected.requests) == 1 and receipt["error"] == "HTTP 400"
    )


def test_exhausted_retries_leave_a_resumable_receipt(tmp_path, server):
    s = server(500)
    receipt = run(lp_file(tmp_path, 3), s, batch_lines=10, retries=1)
    assert not receipt["complete"] and receipt["failed_batch"] == 0 and len(s.requests) == 2


def test_crlf_files_and_blank_lines_are_tolerated(tmp_path, server):
    s = server()
    run(lp_file(tmp_path, 3, newline=b"\r\n"), s, batch_lines=10)
    assert b"\r" not in s.requests[0]["body"] and s.requests[0]["body"].count(b"\n") == 3


def test_plain_http_is_refused_except_on_loopback(tmp_path):
    path = lp_file(tmp_path, 1)
    with pytest.raises(ValueError, match="loopback"):
        writer.write_file(path, "http://influx.example.com:8181", "db", token="t")
    with pytest.raises(ValueError, match="Use an http"):
        writer.write_file(path, "ftp://localhost", "db", token="t")


def test_bounds_are_enforced(tmp_path):
    path = lp_file(tmp_path, 5)
    with pytest.raises(ValueError, match="Expected 1-3"):
        writer.write_file(path, "http://127.0.0.1:1", "db", token="t", max_lines=3)
    with pytest.raises(ValueError, match="byte bound"):
        writer.batches([b"x" * 50], 10, 20)


def test_unreachable_server_is_a_clean_failure_without_leaking_the_token(tmp_path):
    receipt = writer.write_file(
        lp_file(tmp_path, 2),
        "http://127.0.0.1:1",
        "db",
        token="secret-token",
        retries=0,
        timeout=1,
        sleep=lambda x: None,
    )
    assert not receipt["complete"] and "secret-token" not in json.dumps(receipt)


def test_cli_requires_the_token_from_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("INFLUXDB3_TOKEN", raising=False)
    monkeypatch.setattr(
        "sys.argv",
        [
            "write_lp",
            "--file",
            str(lp_file(tmp_path, 1)),
            "--url",
            "http://127.0.0.1:1",
            "--database",
            "d",
        ],
    )
    assert writer.main() == 2
    assert "INFLUXDB3_TOKEN" in capsys.readouterr().out
