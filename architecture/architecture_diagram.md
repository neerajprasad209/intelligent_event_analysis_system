# System Architecture & Workflow Diagram

This document details the architectural design, layered data processing pipeline, and component responsibilities for the **Event Intelligent System**.

---

## High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Ingestion ["1. Ingestion & Sanitization Layer"]
        A1["Raw Log Files<br/>(events.log / Uploaded Files)"] --> B1["Stream Reader & Line Cleaner"]
        B1 --> B2{"parse_log_line()<br/>Validation"}
        B2 -- "Malformed / Bad Timestamp / Noise" --> B3["Loguru Debug & Error Sinks<br/>(logs/LOG_YYYY-MM-DD.log)"]
        B2 -- "Valid Tokenized Record" --> C1["LogEvent Dataclass"]
    end

    subgraph Resequencing ["2. Grouping & Resequencing Layer"]
        C1 --> D1["Device Event Sorter<br/>(Group by device_id)"]
        D1 --> D2["Chronological Ordering<br/>(ISO Timestamps)"]
    end

    subgraph Diagnostics ["3. Diagnostic & RCA Engine"]
        D2 --> E1["diagnose_device()"]
        E1 --> E2{"Has FAILED Events?"}
        E2 -- "No" --> E3["Status: HEALTHY"]
        E2 -- "Yes" --> E4["Status: FAILED"]
        E4 --> E5["Primary Root Cause Identification<br/>(First Failure in Sequence)"]
        E4 --> E6["Retry Counter & Failure Recurrence"]
        E5 --> E7["Rule-Based RCA Mapping<br/>(EVENT_FAILURE_TYPE_MAP)"]
        E6 --> E8["Confidence Calculation Formula"]
        E7 & E8 --> E9["Prescriptive Human Recommendations"]
    end

    subgraph Presentation ["4. Output & Serving Layer"]
        E3 & E9 --> F1["LogAnalysisSystem Orchestrator"]
        F1 --> G1["CLI Runner<br/>(src/main.py / stdout)"]
        F1 --> G2["Timestamped Report Writer<br/>(output/OUTPUT_*.json)"]
        F1 --> G3["FastAPI REST Endpoints<br/>(src/api.py / Swagger UI)"]
    end
```

---

## Detailed Pipeline Stages

### 1. Ingestion & Sanitization Layer
- **Input Sources**: Ingests files via batch CLI (`sample_data/events.log`) or HTTP multipart upload (`POST /analyze`).
- **Resilient Line Parsing**: Strips unwanted trailing commas, dots, and whitespace (`parse_log_line`).
- **Data Validation**: Checks token structure (5 columns: `date`, `time`, `device_id`, `event_type`, `status`) and ensures valid ISO timestamps (`YYYY-MM-DD HH:MM:SS`).
- **Error Isolation**: Broken timestamps (e.g., `2026-99-99`) or missing tokens are logged to Loguru debug sinks and skipped without failing the job.

### 2. Grouping & Resequencing Layer
- **Device Partitioning**: Events are grouped in-memory by `device_id`.
- **Chronological Sorting**: Raw logs often arrive out of sequence due to network delays or multi-threaded logger flushes. The engine sorts each device's timeline strictly by timestamp before analysis to guarantee causal integrity.

### 3. Diagnostic & Root Cause Analysis (RCA) Engine
- **Health Determination**: Devices with no `FAILED` status are marked `HEALTHY`.
- **First-Failure Root Cause Isolation**: Cascading errors are avoided by pinpointing the *first* chronologically failing event in the sequence.
- **Classification Mapping**: Translates raw event types into standardized failure domains (`SESSION_ESTABLISHMENT`, `AUTHENTICATION`, `DATA_TRANSMISSION`, `CONNECTION_DROP`).
- **Confidence Scoring**: Starts at 75% base confidence, adding 5% for every logged retry attempt up to 98%.
- **Actionable Recommendations**: Attaches clear troubleshooting steps for engineering teams based on the identified failure type.

### 4. Output & Serving Layer
- **CLI Output**: Formatted JSON printed to standard output for scripting.
- **Persistent Reports**: Saved as `output/OUTPUT_<Date>_<Time>.json`.
- **FastAPI REST API**: Interactive OpenAPI Swagger documentation (`/docs`), device-level lookups (`/device/{device_id}`), and overall summary stats (`/summary`).

---

## Component Responsibilities

| File | Primary Role |
| :--- | :--- |
| `src/config.py` | Central settings, status definitions, error mapping dictionaries, and Loguru logging sinks. |
| `src/analyzer.py` | Core engine containing `LogEvent` schema, line cleaner, chronological sorter, RCA logic, and report generator. |
| `src/main.py` | CLI execution entry point for offline batch log analysis. |
| `src/api.py` | Asynchronous FastAPI service exposing REST endpoints and Swagger UI documentation. |
