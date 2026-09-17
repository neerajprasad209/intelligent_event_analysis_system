"""
Event Intelligent System - Core Analyzer Engine

Reads, parses, sanitizes, and evaluates device log events to diagnose
device health status, detect root causes for failures, and provide
actionable operational recommendations.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

try:
    from src import config
except ImportError:
    import config

# Initialize loguru logging with configuration sinks
config.setup_logger()


@dataclass
class LogEvent:
    """Represents a single parsed and validated log event."""
    timestamp: datetime
    device_id: str
    event_type: str
    status: str


def parse_log_line(line: str) -> Optional[LogEvent]:
    """
    Parses and validates a single log line.
    Handles messy inputs, trailing punctuation (e.g., ',,, '),
    extra whitespaces, and malformed timestamps gracefully.
    
    Expected format: YYYY-MM-DD HH:MM:SS DEVICE_ID EVENT_TYPE STATUS
    """
    cleaned_line = line.strip().rstrip(",;.")
    if not cleaned_line:
        return None

    tokens = cleaned_line.split()
    if len(tokens) != 5:
        # Malformed line (missing fields or too many fields)
        return None

    date_str, time_str, device_id, event_type, status = tokens

    # Sanitize status and event_type from any trailing punctuation
    status = status.rstrip(",;.")
    event_type = event_type.rstrip(",;.")

    # Validate timestamp
    timestamp_str = f"{date_str} {time_str}"
    try:
        dt = datetime.strptime(timestamp_str, config.TIMESTAMP_FORMAT)
    except ValueError:
        # Invalid date or time format (e.g., 2026-99-99 99:99:99)
        return None

    return LogEvent(
        timestamp=dt,
        device_id=device_id,
        event_type=event_type,
        status=status,
    )


def load_and_group_logs(file_path: Path) -> Tuple[Dict[str, List[LogEvent]], int, int]:
    """
    Reads a log file, parses valid lines, ignores malformed/incomplete lines,
    and groups events by device ID in chronological order.
    
    Returns:
        tuple: (grouped_events_dict, total_lines_read, malformed_lines_count)
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Log file not found at: {file_path}")

    grouped_events: Dict[str, List[LogEvent]] = {}
    total_lines = 0
    malformed_lines = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue  # Skip blank lines

            total_lines += 1
            event = parse_log_line(line)
            if event is None:
                malformed_lines += 1
                logger.debug(f"Skipping malformed log line: {line}")
                continue

            grouped_events.setdefault(event.device_id, []).append(event)

    # Sort each device's events chronologically
    for device_id in grouped_events:
        grouped_events[device_id].sort(key=lambda ev: ev.timestamp)

    return grouped_events, total_lines, malformed_lines


def diagnose_device(device_id: str, events: List[LogEvent]) -> Dict:
    """
    Diagnoses a device based on its chronological sequence of events.
    Determines HEALTHY or FAILED status, diagnoses root cause failure type,
    counts retries, computes diagnostic confidence, and generates recommendations.
    """
    event_count = len(events)
    if event_count == 0:
        return {
            "device_id": device_id,
            "status": config.STATUS_HEALTHY,
            "event_count": 0,
        }

    # Identify failure indicators and retries
    failed_events = [e for e in events if e.status == config.LOG_STATUS_FAILED]
    retry_events = [
        e for e in events
        if e.event_type == "RETRY" or e.status == "RETRY" or "RETRY" in e.event_type
    ]
    retry_count = len(retry_events)

    is_failed = len(failed_events) > 0

    if not is_failed:
        return {
            "device_id": device_id,
            "status": config.STATUS_HEALTHY,
            "event_count": event_count,
        }

    # Determine failure type and root cause
    # Prioritize the first distinct failure point in the lifecycle
    primary_failed_event = failed_events[0]
    failure_type = config.EVENT_FAILURE_TYPE_MAP.get(
        primary_failed_event.event_type,
        config.FAILURE_GENERAL_FAILURE
    )

    # Compute diagnostic confidence
    confidence = min(
        config.MAX_CONFIDENCE,
        round(config.BASE_CONFIDENCE + (retry_count * config.RETRY_CONFIDENCE_BOOST), 2)
    )

    # Get actionable recommendations
    recommendations = config.RECOMMENDATIONS_MAP.get(
        failure_type,
        config.RECOMMENDATIONS_MAP[config.FAILURE_GENERAL_FAILURE]
    )

    return {
        "device_id": device_id,
        "status": config.STATUS_FAILED,
        "event_count": event_count,
        "failure_type": failure_type,
        "retry_count": retry_count,
        "confidence": confidence,
        "recommendation": recommendations,
    }


class LogAnalysisSystem:
    """
    Main orchestrator for log parsing, diagnosis, and JSON report generation.
    """

    def __init__(self, log_file_path: Optional[Path] = None):
        self.log_file_path = log_file_path or config.INPUT_LOG_FILE

    def analyze(self) -> Dict:
        """
        Executes log ingestion, grouping, diagnosis, and generates summary report.
        """
        grouped_events, total_lines, malformed_lines = load_and_group_logs(self.log_file_path)

        # Sort device IDs naturally for predictable output
        sorted_device_ids = sorted(grouped_events.keys())

        device_reports = []
        healthy_count = 0
        failed_count = 0

        for dev_id in sorted_device_ids:
            diagnosis = diagnose_device(dev_id, grouped_events[dev_id])
            device_reports.append(diagnosis)

            if diagnosis["status"] == config.STATUS_HEALTHY:
                healthy_count += 1
            else:
                failed_count += 1

        report = {
            "summary": {
                "total_devices": len(sorted_device_ids),
                "healthy_devices": healthy_count,
                "failed_devices": failed_count,
            },
            "devices": device_reports,
        }

        logger.info(
            f"Analysis complete: Processed {total_lines} lines ({malformed_lines} malformed). "
            f"Total devices: {len(sorted_device_ids)} (Healthy: {healthy_count}, Failed: {failed_count})."
        )
        return report

    def save_report(self, report: Dict, output_path: Optional[Path] = None) -> Path:
        """
        Saves report dict as formatted JSON to output path.
        """
        target_path = output_path or config.get_output_report_file()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report successfully saved to: {target_path}")
        return target_path
