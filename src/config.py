"""
Configuration settings and constants for Event Intelligent System.
All configurable parameters, paths, and diagnostic rules are centralized here.
"""

from datetime import datetime
import sys
from pathlib import Path
from loguru import logger

# Base Paths (Project Root is parent of src/)
BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"
INPUT_DATA_DIR = SAMPLE_DATA_DIR  # Alias for backward compatibility
LOGS_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "output"
SRC_DIR = BASE_DIR / "src"

# Ensure both project root and src/ are in sys.path
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def get_app_log_file() -> Path:
    """
    Returns application log path named LOG followed by current date.
    Example: logs/LOG_2026-09-17.log
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    return LOGS_DIR / f"LOG_{date_str}.log"


def get_output_report_file() -> Path:
    """
    Returns output report path named OUTPUT followed by current date and timestamp.
    Example: output/OUTPUT_2026-09-17_20-30-15.json
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    return OUTPUT_DIR / f"OUTPUT_{date_str}_{time_str}.json"


# File Paths
INPUT_LOG_FILE = SAMPLE_DATA_DIR / "events.log"
APP_LOG_FILE = get_app_log_file()
OUTPUT_REPORT_FILE = get_output_report_file()


def setup_logger():
    """
    Configures loguru logger sinks for console and application log file.
    Logs to logs/LOG_<current_date>.log and console.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()  # Remove default handler to avoid duplicate logs

    # Console output sink
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )

    # Application file sink named LOG followed by current date
    current_log_path = get_app_log_file()
    logger.add(
        str(current_log_path),
        rotation="10 MB",
        retention="10 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        encoding="utf-8",
    )
    return logger


# Status Constants
STATUS_HEALTHY = "HEALTHY"
STATUS_FAILED = "FAILED"

# Recognized Log Event Statuses
LOG_STATUS_SUCCESS = "SUCCESS"
LOG_STATUS_FAILED = "FAILED"
LOG_STATUS_STARTED = "STARTED"

# Diagnostic Failure Types
FAILURE_SESSION_ESTABLISHMENT = "SESSION_ESTABLISHMENT"
FAILURE_AUTHENTICATION = "AUTHENTICATION"
FAILURE_DATA_TRANSMISSION = "DATA_TRANSMISSION"
FAILURE_CONNECTION_DROP = "CONNECTION_DROP"
FAILURE_GENERAL_FAILURE = "GENERAL_FAILURE"

# Mapping of Event Type to Failure Classification
EVENT_FAILURE_TYPE_MAP = {
    "SESSION_START": FAILURE_SESSION_ESTABLISHMENT,
    "AUTHENTICATION": FAILURE_AUTHENTICATION,
    "DATA_TRANSFER": FAILURE_DATA_TRANSMISSION,
    "CONNECTION_START": "CONNECTION_ESTABLISHMENT",
    "CONNECTION_DROP": FAILURE_CONNECTION_DROP,
}

# Actionable Human Recommendations based on Root Cause
RECOMMENDATIONS_MAP = {
    FAILURE_SESSION_ESTABLISHMENT: [
        "Review session establishment configuration",
        "Inspect session manager timeout and capacity limits",
        "Verify handshake protocol compatibility",
    ],
    FAILURE_AUTHENTICATION: [
        "Verify device credentials, auth tokens, and certificate validity",
        "Inspect authentication server access control policies and rate limits",
        "Check identity provider sync status",
    ],
    FAILURE_DATA_TRANSMISSION: [
        "Inspect network link stability, latency, and MTU settings",
        "Verify endpoint buffer capacity and receiver availability",
        "Check payload size limits",
    ],
    FAILURE_CONNECTION_DROP: [
        "Investigate physical or wireless connection drops on device interface",
        "Review keepalive ping thresholds and firewall idle timeouts",
    ],
    FAILURE_GENERAL_FAILURE: [
        "Conduct detailed firmware diagnostic dump on device",
        "Inspect system logs for unhandled exceptions",
    ],
}

# Confidence Calculation Parameters
BASE_CONFIDENCE = 0.75
RETRY_CONFIDENCE_BOOST = 0.05
MAX_CONFIDENCE = 0.98

# Date format for parsing log timestamps
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
