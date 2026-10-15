import json
from pathlib import Path

import pytest

from le_results.errors import ToolkitError
from le_results.synthetic import demo
from le_results.timeseries import escape_tag, export_line_protocol, observation_line, timestamp_ns


def test_timestamp_precision_timezone_and_distinct_same_time_observations():
    assert timestamp_ns("1970-01-01T01:00:00.123456789+01:00") == 123456789
    row = {
        "testRunId": "run",
        "timestamp": "2026-01-01T00:00:00.1234567Z",
        "duration": 0,
        "measurementId": "timer",
        "userSessionId": "session",
    }
    a, aid = observation_line(row, "measurements", "source")
    b, bid = observation_line({**row, "userSessionId": "other"}, "measurements", "source")
    c, cid = observation_line({**row, "duration": 1}, "measurements", "source")
    assert len({aid, bid, cid}) == 3
    assert a.split()[-1] == b.split()[-1] == c.split()[-1]
    assert "value=0.0" in a
    assert observation_line(
        {**row, "capture_id": "later", "timestamp_utc": "derived"}, "measurements", "source"
    ) == (a, aid)


def test_escaping_missing_values_and_no_categorical_conversion():
    assert escape_tag("a,b =c\\d") == "a\\,b\\ \\=c\\\\d"
    row = {
        "timestamp": "2026-01-01T00:00:00Z",
        "measurement": None,
        "displayName": "metric, one",
        "unit": "%",
    }
    line, _ = observation_line(row, "session_metrics", "source")
    assert "value_present=false" in line and ",value=" not in line
    assert "metric\\,\\ one" in line
    for invalid in (True, "failed", float("nan")):
        with pytest.raises(ToolkitError):
            observation_line({**row, "measurement": invalid}, "session_metrics", "source")
    with pytest.raises(ToolkitError):
        escape_tag("injection\npoint")
    for invalid in (None, "2026-01-01T00:00:00", "2026-01-01T00:00:00.1234567890Z"):
        with pytest.raises(ToolkitError):
            timestamp_ns(invalid)


def test_file_export_is_bounded_complete_only_and_never_advances_checkpoint(tmp_path: Path):
    demo(tmp_path / "source")
    capture = tmp_path / "source/baseline"
    with pytest.raises(ToolkitError, match="bound"):
        export_line_protocol(capture, tmp_path / "too-many", 2)
    assert not (tmp_path / "too-many").exists()
    receipt = export_line_protocol(capture, tmp_path / "batch", 3)
    assert receipt["exported_points"] == 3
    assert receipt["status"] == "prepared-not-written"
    assert receipt["checkpoint_advanced"] is False
    assert len((tmp_path / "batch/observations.lp").read_text().splitlines()) == 3
    manifest = capture / "manifest.json"
    data = json.loads(manifest.read_text())
    data["status"] = "partial"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ToolkitError, match="partial"):
        export_line_protocol(capture, tmp_path / "partial")
    assert not (tmp_path / "partial").exists()


def test_endpoint_provenance_and_equivalent_timestamp_identity_are_preserved():
    row = {
        "timestamp": "2026-01-01T00:00:00.0000001Z",
        "duration": 1,
        "testRunId": "run",
        "_testRunId_from_endpoint": True,
    }
    line, identity = observation_line(row, "measurements", "source")
    equivalent, other = observation_line(
        {**row, "timestamp": "2026-01-01T01:00:00.000000100+01:00"}, "measurements", "source"
    )
    assert identity == other
    assert "result_id_source=endpoint" in line and "_testRunId_from_endpoint" in line
    assert "result_id_source=endpoint" in equivalent
    for value in (2**53 + 1, 10**1000):
        with pytest.raises(ToolkitError, match="exact"):
            observation_line({**row, "duration": value}, "measurements", "source")
