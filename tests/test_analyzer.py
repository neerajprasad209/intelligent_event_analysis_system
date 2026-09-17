"""
Unit and Integration Tests for Event Intelligent System Analyzer Engine.

Required Test Coverage:
1. Valid input
2. Invalid input
3. Empty input
4. Multiple devices
5. Failed events
6. Repeated failures
7. Out-of-order events
8. Missing events
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
import pytest

try:
    from src import config
    from src.analyzer import (
        LogAnalysisSystem,
        LogEvent,
        diagnose_device,
        load_and_group_logs,
        parse_log_line,
    )
except ImportError:
    import config
    from analyzer import (
        LogAnalysisSystem,
        LogEvent,
        diagnose_device,
        load_and_group_logs,
        parse_log_line,
    )


def create_temp_logfile(content: str) -> Path:
    """Helper to create a temporary log file for testing."""
    tmp = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log", encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


# =====================================================================
# 1. VALID INPUT TESTS
# =====================================================================

def test_valid_input_happy_path():
    """
    Test 1: Valid input.
    Verifies that a well-formed log sequence for a device is accurately parsed,
    classified as HEALTHY, with correct event counts and summary stats.
    """
    content = (
        "2026-09-01 10:00:01 DEV-01 CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:02 DEV-01 AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:00:03 DEV-01 SESSION_START SUCCESS\n"
        "2026-09-01 10:00:10 DEV-01 DATA_TRANSFER SUCCESS\n"
        "2026-09-01 10:00:20 DEV-01 SESSION_END SUCCESS\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        assert report["summary"]["total_devices"] == 1
        assert report["summary"]["healthy_devices"] == 1
        assert report["summary"]["failed_devices"] == 0

        dev = report["devices"][0]
        assert dev["device_id"] == "DEV-01"
        assert dev["status"] == "HEALTHY"
        assert dev["event_count"] == 5
        assert "failure_type" not in dev
    finally:
        log_file.unlink()


def test_parse_log_line_valid():
    """Directly verifies parse_log_line produces LogEvent with exact fields for valid input."""
    raw = "2026-09-01 10:15:30 DEVICE-99 CONNECTION_START SUCCESS"
    event = parse_log_line(raw)
    assert event is not None
    assert event.device_id == "DEVICE-99"
    assert event.event_type == "CONNECTION_START"
    assert event.status == "SUCCESS"
    assert event.timestamp == datetime(2026, 9, 1, 10, 15, 30)


# =====================================================================
# 2. INVALID INPUT TESTS
# =====================================================================

def test_invalid_input_malformed_and_broken_lines():
    """
    Test 2: Invalid input.
    Verifies that corrupt, missing-token, extra-token, invalid date/time,
    and noisy punctuation lines are safely dropped without throwing exceptions.
    """
    content = (
        "GARBAGE LINE WITH NO STRUCTURE\n"
        "2026-09-01 10:09:01 DEV-10 CONNECTION_START\n"  # Only 4 tokens
        "2026-09-01 DEV-10 AUTHENTICATION SUCCESS\n"  # Missing time token
        "2026-99-99 99:99:99 DEV-10 SESSION_START SUCCESS\n"  # Impossible date/time
        "2026-02-30 10:00:00 DEV-10 SESSION_START SUCCESS\n"  # Invalid calendar date
        "DEV-10 SESSION_START SUCCESS\n"  # Missing timestamp
        "2026-09-01 10:09:05 DEV-10 DATA_TRANSFER SUCCESS EXTRA_TOKEN\n"  # 6 tokens
        "2026-09-01 10:09:05 DEV-10 DATA_TRANSFER SUCCESS,,, \n"  # Valid after strip
    )
    log_file = create_temp_logfile(content)
    try:
        grouped, total, malformed = load_and_group_logs(log_file)
        assert malformed == 7
        assert total == 8
        assert "DEV-10" in grouped
        assert len(grouped["DEV-10"]) == 1
        assert grouped["DEV-10"][0].event_type == "DATA_TRANSFER"
        assert grouped["DEV-10"][0].status == "SUCCESS"
    finally:
        log_file.unlink()


def test_invalid_input_nonexistent_file():
    """Verifies that attempting to load a non-existent file raises FileNotFoundError."""
    missing_path = Path("non_existent_log_file_12345.log")
    with pytest.raises(FileNotFoundError):
        load_and_group_logs(missing_path)


# =====================================================================
# 3. EMPTY INPUT TESTS
# =====================================================================

def test_empty_input_file():
    """
    Test 3: Empty input.
    Verifies that an empty file produces 0 devices and clean empty summaries.
    """
    log_file = create_temp_logfile("")
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        assert report["summary"]["total_devices"] == 0
        assert report["summary"]["healthy_devices"] == 0
        assert report["summary"]["failed_devices"] == 0
        assert report["devices"] == []
    finally:
        log_file.unlink()


def test_empty_input_whitespace_only():
    """Verifies that a log file containing only whitespace and blank lines yields empty results."""
    content = "   \n\n\t  \n   \r\n"
    log_file = create_temp_logfile(content)
    try:
        grouped, total, malformed = load_and_group_logs(log_file)
        assert len(grouped) == 0
        assert total == 0
        assert malformed == 0
    finally:
        log_file.unlink()


def test_diagnose_device_empty_events():
    """Verifies diagnose_device returns default healthy status when events list is empty."""
    diagnosis = diagnose_device("DEV-EMPTY", [])
    assert diagnosis["device_id"] == "DEV-EMPTY"
    assert diagnosis["status"] == config.STATUS_HEALTHY
    assert diagnosis["event_count"] == 0


# =====================================================================
# 4. MULTIPLE DEVICES TESTS
# =====================================================================

def test_multiple_devices_isolation_and_aggregation():
    """
    Test 4: Multiple devices.
    Verifies that interleaved logs from multiple devices are properly separated,
    alphabetically sorted by device_id, and correctly tallied in summary metrics.
    Ensures a failure on one device does NOT affect the healthy status of another.
    """
    content = (
        "2026-09-01 10:00:01 DEV-A CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:02 DEV-B CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:03 DEV-C CONNECTION_START SUCCESS\n"
        "2026-09-01 10:00:04 DEV-A AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:00:05 DEV-B AUTHENTICATION FAILED\n"  # DEV-B FAILED
        "2026-09-01 10:00:06 DEV-C AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:00:07 DEV-A SESSION_START SUCCESS\n"   # DEV-A HEALTHY
        "2026-09-01 10:00:08 DEV-C SESSION_START FAILED\n"    # DEV-C FAILED
        "2026-09-01 10:00:09 DEV-D CONNECTION_START SUCCESS\n" # DEV-D HEALTHY
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        assert report["summary"]["total_devices"] == 4
        assert report["summary"]["healthy_devices"] == 2
        assert report["summary"]["failed_devices"] == 2

        dev_map = {d["device_id"]: d for d in report["devices"]}
        assert set(dev_map.keys()) == {"DEV-A", "DEV-B", "DEV-C", "DEV-D"}

        # DEV-A: Healthy
        assert dev_map["DEV-A"]["status"] == config.STATUS_HEALTHY
        assert dev_map["DEV-A"]["event_count"] == 3

        # DEV-B: Failed at AUTHENTICATION
        assert dev_map["DEV-B"]["status"] == config.STATUS_FAILED
        assert dev_map["DEV-B"]["failure_type"] == config.FAILURE_AUTHENTICATION
        assert dev_map["DEV-B"]["event_count"] == 2

        # DEV-C: Failed at SESSION_START
        assert dev_map["DEV-C"]["status"] == config.STATUS_FAILED
        assert dev_map["DEV-C"]["failure_type"] == config.FAILURE_SESSION_ESTABLISHMENT
        assert dev_map["DEV-C"]["event_count"] == 3

        # DEV-D: Healthy single event
        assert dev_map["DEV-D"]["status"] == config.STATUS_HEALTHY
        assert dev_map["DEV-D"]["event_count"] == 1

        # Check devices list is sorted by device_id
        device_order = [d["device_id"] for d in report["devices"]]
        assert device_order == ["DEV-A", "DEV-B", "DEV-C", "DEV-D"]
    finally:
        log_file.unlink()


# =====================================================================
# 5. FAILED EVENTS TESTS
# =====================================================================

@pytest.mark.parametrize(
    "failed_event_type,expected_failure_type,expected_keyword",
    [
        ("AUTHENTICATION", config.FAILURE_AUTHENTICATION, "credentials"),
        ("SESSION_START", config.FAILURE_SESSION_ESTABLISHMENT, "session"),
        ("DATA_TRANSFER", config.FAILURE_DATA_TRANSMISSION, "network"),
        ("CONNECTION_DROP", config.FAILURE_CONNECTION_DROP, "connection"),
        ("UNKNOWN_EVENT", config.FAILURE_GENERAL_FAILURE, "diagnostic"),
    ]
)
def test_failed_events_root_cause_mappings(failed_event_type, expected_failure_type, expected_keyword):
    """
    Test 5: Failed events.
    Verifies that all distinct failure event types are mapped to their respective
    root causes and that tailored, actionable recommendations are populated.
    """
    content = (
        f"2026-09-01 10:00:01 DEV-FAIL CONNECTION_START SUCCESS\n"
        f"2026-09-01 10:00:02 DEV-FAIL {failed_event_type} FAILED\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["status"] == config.STATUS_FAILED
        assert dev["failure_type"] == expected_failure_type
        assert len(dev["recommendation"]) > 0
        assert any(expected_keyword in rec.lower() for rec in dev["recommendation"])
    finally:
        log_file.unlink()


def test_failed_events_multiple_failure_cascade():
    """
    Verifies that when multiple failures occur in cascade, the first chronological
    failure is identified as the root cause, not subsequent downstream failures.
    """
    content = (
        "2026-09-01 10:10:01 DEV-CASCADE CONNECTION_START SUCCESS\n"
        "2026-09-01 10:10:02 DEV-CASCADE AUTHENTICATION FAILED\n"  # 1st failure (root cause)
        "2026-09-01 10:10:03 DEV-CASCADE SESSION_START FAILED\n"   # 2nd failure
        "2026-09-01 10:10:04 DEV-CASCADE DATA_TRANSFER FAILED\n"   # 3rd failure
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["status"] == config.STATUS_FAILED
        assert dev["failure_type"] == config.FAILURE_AUTHENTICATION
    finally:
        log_file.unlink()


# =====================================================================
# 6. REPEATED FAILURES TESTS
# =====================================================================

def test_repeated_failures_and_confidence_capping():
    """
    Test 6: Repeated failures.
    Verifies that consecutive repeated failures with retries:
    - Count retries accurately.
    - Increment confidence score by 0.05 per retry from 0.75 base.
    - Clamps confidence at MAX_CONFIDENCE (0.98), never exceeding it.
    - Keeps the primary root cause consistent.
    """
    # 5 retries: 0.75 + (5 * 0.05) = 1.00 -> should cap at 0.98
    content = (
        "2026-09-01 10:06:01 DEV-RETRY CONNECTION_START SUCCESS\n"
        "2026-09-01 10:06:02 DEV-RETRY AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:06:03 DEV-RETRY SESSION_START FAILED\n"
        "2026-09-01 10:06:04 DEV-RETRY RETRY STARTED\n"
        "2026-09-01 10:06:05 DEV-RETRY SESSION_START FAILED\n"
        "2026-09-01 10:06:06 DEV-RETRY RETRY STARTED\n"
        "2026-09-01 10:06:07 DEV-RETRY SESSION_START FAILED\n"
        "2026-09-01 10:06:08 DEV-RETRY RETRY STARTED\n"
        "2026-09-01 10:06:09 DEV-RETRY SESSION_START FAILED\n"
        "2026-09-01 10:06:10 DEV-RETRY RETRY STARTED\n"
        "2026-09-01 10:06:11 DEV-RETRY SESSION_START FAILED\n"
        "2026-09-01 10:06:12 DEV-RETRY RETRY STARTED\n"
        "2026-09-01 10:06:13 DEV-RETRY SESSION_START FAILED\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["device_id"] == "DEV-RETRY"
        assert dev["status"] == config.STATUS_FAILED
        assert dev["failure_type"] == config.FAILURE_SESSION_ESTABLISHMENT
        assert dev["retry_count"] == 5
        # Confidence calculation: min(0.98, round(0.75 + (5 * 0.05), 2)) = 0.98
        assert dev["confidence"] == config.MAX_CONFIDENCE
        assert dev["confidence"] <= 0.98
    finally:
        log_file.unlink()


def test_repeated_failures_without_retries():
    """
    Verifies that multiple repeated failure events without explicit RETRY events
    maintain the baseline confidence (0.75) and 0 retry count.
    """
    content = (
        "2026-09-01 10:07:01 DEV-REPEAT CONNECTION_START SUCCESS\n"
        "2026-09-01 10:07:02 DEV-REPEAT AUTHENTICATION FAILED\n"
        "2026-09-01 10:07:03 DEV-REPEAT AUTHENTICATION FAILED\n"
        "2026-09-01 10:07:04 DEV-REPEAT AUTHENTICATION FAILED\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["status"] == config.STATUS_FAILED
        assert dev["failure_type"] == config.FAILURE_AUTHENTICATION
        assert dev["retry_count"] == 0
        assert dev["confidence"] == config.BASE_CONFIDENCE  # 0.75
    finally:
        log_file.unlink()


# =====================================================================
# 7. OUT-OF-ORDER EVENTS TESTS
# =====================================================================

def test_out_of_order_events_chronological_sorting():
    """
    Test 7: Out-of-order events.
    Verifies that events appearing out of chronological order in the raw log file
    are correctly sorted by timestamp before diagnostic evaluation.
    """
    content = (
        "2026-09-01 10:02:10 DEV-ORDER DATA_TRANSFER SUCCESS\n"
        "2026-09-01 10:02:01 DEV-ORDER CONNECTION_START SUCCESS\n"
        "2026-09-01 10:02:05 DEV-ORDER SESSION_START SUCCESS\n"
        "2026-09-01 10:02:02 DEV-ORDER AUTHENTICATION SUCCESS\n"
    )
    log_file = create_temp_logfile(content)
    try:
        grouped, _, _ = load_and_group_logs(log_file)
        events = grouped["DEV-ORDER"]
        assert events[0].event_type == "CONNECTION_START"
        assert events[1].event_type == "AUTHENTICATION"
        assert events[2].event_type == "SESSION_START"
        assert events[3].event_type == "DATA_TRANSFER"

        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()
        assert report["devices"][0]["status"] == config.STATUS_HEALTHY
    finally:
        log_file.unlink()


def test_out_of_order_events_failure_root_cause():
    """
    Verifies that when failures arrive out of sequence, the chronologically
    earlier failure is accurately selected as root cause.
    """
    content = (
        "2026-09-01 10:05:10 DEV-OOO DATA_TRANSFER FAILED\n"       # Logged first, but occurred 2nd
        "2026-09-01 10:05:01 DEV-OOO CONNECTION_START SUCCESS\n"
        "2026-09-01 10:05:02 DEV-OOO AUTHENTICATION FAILED\n"      # Logged later, but occurred 1st!
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["failure_type"] == config.FAILURE_AUTHENTICATION  # Correct chronological root cause
    finally:
        log_file.unlink()


# =====================================================================
# 8. MISSING EVENTS TESTS
# =====================================================================

def test_missing_events_incomplete_lifecycle():
    """
    Test 8: Missing events.
    Verifies that devices missing expected lifecycle steps (e.g., missing SESSION_START,
    jumping straight from AUTHENTICATION to DATA_TRANSFER, or missing CONNECTION_START)
    are handled gracefully without crashes or unexpected state corruption.
    """
    content = (
        # DEV-MISSING-1: Skips SESSION_START entirely
        "2026-09-01 10:04:01 DEV-MISS-1 CONNECTION_START SUCCESS\n"
        "2026-09-01 10:04:02 DEV-MISS-1 AUTHENTICATION SUCCESS\n"
        "2026-09-01 10:04:03 DEV-MISS-1 DATA_TRANSFER SUCCESS\n"
        # DEV-MISSING-2: Starts directly with DATA_TRANSFER (missing connection & auth)
        "2026-09-01 10:04:10 DEV-MISS-2 DATA_TRANSFER SUCCESS\n"
        # DEV-MISSING-3: Single isolated event
        "2026-09-01 10:04:15 DEV-MISS-3 SESSION_END SUCCESS\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        assert report["summary"]["total_devices"] == 3
        assert report["summary"]["healthy_devices"] == 3
        assert report["summary"]["failed_devices"] == 0

        dev_map = {d["device_id"]: d for d in report["devices"]}
        assert dev_map["DEV-MISS-1"]["status"] == config.STATUS_HEALTHY
        assert dev_map["DEV-MISS-1"]["event_count"] == 3

        assert dev_map["DEV-MISS-2"]["status"] == config.STATUS_HEALTHY
        assert dev_map["DEV-MISS-2"]["event_count"] == 1

        assert dev_map["DEV-MISS-3"]["status"] == config.STATUS_HEALTHY
        assert dev_map["DEV-MISS-3"]["event_count"] == 1
    finally:
        log_file.unlink()


def test_missing_events_with_failure():
    """
    Verifies that a device with missing lifecycle stages that encounters a failure
    is correctly diagnosed as FAILED with the appropriate root cause.
    """
    content = (
        # Skips CONNECTION_START and AUTHENTICATION, directly attempts SESSION_START and fails
        "2026-09-01 10:04:05 DEV-MISS-FAIL SESSION_START FAILED\n"
        "2026-09-01 10:04:06 DEV-MISS-FAIL RETRY STARTED\n"
        "2026-09-01 10:04:07 DEV-MISS-FAIL SESSION_START FAILED\n"
    )
    log_file = create_temp_logfile(content)
    try:
        analyzer = LogAnalysisSystem(log_file)
        report = analyzer.analyze()

        dev = report["devices"][0]
        assert dev["device_id"] == "DEV-MISS-FAIL"
        assert dev["status"] == config.STATUS_FAILED
        assert dev["failure_type"] == config.FAILURE_SESSION_ESTABLISHMENT
        assert dev["retry_count"] == 1
        assert dev["confidence"] == 0.80
    finally:
        log_file.unlink()


# =====================================================================
# SYSTEM & CONFIGURATION TESTS
# =====================================================================

def test_save_report_persistence():
    """Verifies that save_report writes a valid formatted JSON file to disk."""
    report_data = {
        "summary": {"total_devices": 1, "healthy_devices": 1, "failed_devices": 0},
        "devices": [{"device_id": "DEV-TEST", "status": "HEALTHY", "event_count": 1}]
    }
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp:
        tmp_path = Path(tmp.name)

    try:
        analyzer = LogAnalysisSystem()
        saved_path = analyzer.save_report(report_data, tmp_path)
        assert saved_path.exists()

        with open(saved_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == report_data
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_dynamic_filenames():
    """Verify log and output report follow required dynamic naming patterns."""
    app_log = config.get_app_log_file()
    today_str = datetime.now().strftime("%Y-%m-%d")
    assert app_log.name == f"LOG_{today_str}.log"
    assert app_log.parent == config.LOGS_DIR

    output_report = config.get_output_report_file()
    assert output_report.name.startswith(f"OUTPUT_{today_str}_")
    assert output_report.name.endswith(".json")
    assert output_report.parent == config.OUTPUT_DIR
