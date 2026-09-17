"""
Event Intelligent System - FastAPI REST Service

Endpoints:
- POST /analyze             : Upload log file to run diagnostics, save output file, and return report
- GET  /summary             : Get high-level summary of total, healthy, and failed devices
- GET  /device/{device_id}  : Get detailed diagnostic status for a specific device
"""

import logging
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
import uvicorn
from loguru import logger

try:
    from src import config
    from src.analyzer import LogAnalysisSystem
except ImportError:
    import config
    from analyzer import LogAnalysisSystem

# Initialize loguru logger sinks
config.setup_logger()


# Intercept standard Uvicorn / logging handlers and route them to Loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.getLogger("uvicorn").handlers = [InterceptHandler()]
logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
logging.getLogger("uvicorn.error").handlers = [InterceptHandler()]

app = FastAPI(
    title="Event Intelligent System API",
    description="Real-time Machine Event Ingestion, Out-of-Order Resequencing, Failure Root-Cause Diagnostics & Recommendations.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Global cache for latest analysis report
LATEST_REPORT: Optional[Dict] = None


# Request & Response Logging Middleware using Loguru
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Incoming HTTP Request: {request.method} {request.url.path} from {client_ip}")

    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.info(
            f"HTTP Response: {request.method} {request.url.path} -> Status {response.status_code} ({duration_ms}ms)"
        )
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        logger.exception(f"HTTP Error on {request.method} {request.url.path}: {exc} ({duration_ms}ms)")
        raise exc


@app.get("/", include_in_schema=False)
def root():
    """Redirects base URL automatically to Swagger UI documentation."""
    return RedirectResponse(url="/docs")


def get_or_create_report() -> Dict:
    """Helper to retrieve latest report or run on default events.log if not yet analyzed."""
    global LATEST_REPORT
    if LATEST_REPORT is not None:
        return LATEST_REPORT

    if config.INPUT_LOG_FILE.exists():
        logger.info(f"Running initial analysis on default log file: {config.INPUT_LOG_FILE}")
        analyzer = LogAnalysisSystem(config.INPUT_LOG_FILE)
        report = analyzer.analyze()
        saved_path = analyzer.save_report(report)
        report["output_file"] = str(saved_path)
        LATEST_REPORT = report
        return report

    raise HTTPException(
        status_code=404,
        detail="No analysis report available. Please run POST /analyze with a log file first."
    )


@app.post("/analyze", tags=["Diagnostics"], summary="Upload log file to diagnose and generate output report")
async def analyze_log_file(
    file: Optional[UploadFile] = File(
        None,
        description="Upload log file (.log or .txt). If omitted, analyzes configured sample_data/events.log"
    )
):
    """
    Upload a log file directly via Swagger UI.
    Analyzes all devices, determines root causes for failures,
    saves the output report to disk (output/OUTPUT_<date>_<timestamp>.json),
    and returns the structured JSON diagnosis report.
    """
    global LATEST_REPORT
    try:
        if file is not None and file.filename:
            logger.info(f"API /analyze: Processing uploaded file '{file.filename}'")
            file_bytes = await file.read()
            log_content = file_bytes.decode("utf-8")

            if not log_content.strip():
                logger.warning("Uploaded log file is empty")
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")

            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log", encoding="utf-8") as tmp:
                tmp.write(log_content)
                tmp_path = Path(tmp.name)

            try:
                analyzer = LogAnalysisSystem(tmp_path)
                report = analyzer.analyze()
                saved_path = analyzer.save_report(report)
                report["output_file"] = str(saved_path)
                LATEST_REPORT = report
                logger.info(
                    f"API /analyze: Analyzed {report['summary']['total_devices']} devices. "
                    f"Output generated at: {saved_path}"
                )
                return report
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            # Fallback to configured input file if no file provided
            logger.info(f"API /analyze: No file uploaded, analyzing configured file: {config.INPUT_LOG_FILE}")
            analyzer = LogAnalysisSystem(config.INPUT_LOG_FILE)
            report = analyzer.analyze()
            saved_path = analyzer.save_report(report)
            report["output_file"] = str(saved_path)
            LATEST_REPORT = report
            logger.info(
                f"API /analyze: Analyzed {report['summary']['total_devices']} devices. "
                f"Output generated at: {saved_path}"
            )
            return report

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"API /analyze error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/summary", tags=["Diagnostics"], summary="Get overall device health summary")
def get_summary():
    """
    Returns high-level summary statistics:
    - total_devices
    - healthy_devices
    - failed_devices
    """
    report = get_or_create_report()
    return report.get("summary", {})


@app.get("/device/{device_id}", tags=["Diagnostics"], summary="Get diagnosis for a specific device")
def get_device(device_id: str):
    """
    Returns detailed diagnosis for a specific device ID (e.g. DEVICE-01, DEVICE-02).
    """
    report = get_or_create_report()
    devices = report.get("devices", [])

    # Search for matching device ID (case-insensitive)
    normalized_id = device_id.strip().upper()
    for dev in devices:
        if dev.get("device_id", "").upper() == normalized_id:
            return dev

    logger.warning(f"Device '{device_id}' requested but not found.")
    raise HTTPException(
        status_code=404,
        detail=f"Device '{device_id}' not found in the latest analysis report."
    )


if __name__ == "__main__":
    logger.info("Starting Event Intelligent System FastAPI server on http://127.0.0.1:5000")
    logger.info("Open http://127.0.0.1:5000/docs for Swagger UI")
    app_target = "src.api:app" if (config.BASE_DIR / "src" / "api.py").exists() else "api:app"
    uvicorn.run(app_target, host="0.0.0.0", port=5000, reload=True)
