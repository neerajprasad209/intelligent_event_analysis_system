"""
Event Intelligent System - Main Entry Point

Reads device event logs from the configured log folder, runs diagnostics,
prints the structured JSON report to standard output, and writes it to disk.
"""

import json
import sys
from pathlib import Path

from loguru import logger

try:
    from src import config
    from src.analyzer import LogAnalysisSystem
except ImportError:
    import config
    from analyzer import LogAnalysisSystem

# Initialize loguru logger sinks
config.setup_logger()


def main():
    app_log = config.get_app_log_file()
    logger.info("=" * 60)
    logger.info("Starting Event Intelligent System - Device Log Analyzer")
    logger.info(f"Input Log File : {config.INPUT_LOG_FILE}")
    logger.info(f"App Log File   : {app_log}")
    logger.info("=" * 60)

    try:
        analyzer = LogAnalysisSystem(log_file_path=config.INPUT_LOG_FILE)
        report = analyzer.analyze()

        # Save to output file (named OUTPUT_<current_date>_<timestamp>.json)
        saved_path = analyzer.save_report(report)
        logger.info(f"Successfully generated diagnosis report for {report['summary']['total_devices']} devices.")

        # Print JSON report cleanly to console
        print("\nGenerated Diagnostics Report:")
        print(json.dumps(report, indent=2))
        print("-" * 60)
        print(f"Report saved to: {saved_path}")
        print(f"Application event logs saved to: {app_log}")

    except Exception as e:
        logger.exception(f"Fatal error during log analysis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
