# Demo Mode Architecture Review: Vectra App

## Overview
The demo mode implementation in the Vectra application provides a robust, self-contained way to showcase functionality without relying on live external services (like Alpaca for market data, Ollama for LLMs, and Torch for model predictions). It is built around a centralized mocking strategy that can record real network interactions and replay them accurately on demand.

---

## 1. Backend Implementation

The backend drives the core of the demo system through two environment-configurable settings, which are dynamically controllable and reportable via the API:

*   **`DEMO_MODE`**: When enabled, the backend intercepts service calls and file operations, returning locally cached data instead of interacting with external tools or live file locations.
*   **`SAVE_FOR_DEMO`**: A "record" mode that functions alongside the live application. When enabled, successful operations write their responses/outputs to disk as mock files for later use in demo mode.

### 1.1 `RecordableService` Pattern
External integrations (LLMs, Market Data, Torch Models) inherit from a base `RecordableService` (`apps/backend/services/base.py`). 
The `call()` method dynamically checks the environment state:
- **If `demo_mode` is True**: It bypasses the live execution completely and retrieves stored JSON (and tensor data) via `_load_mock`.
- **If `demo_mode` is False**: It runs the live executor. 
- **If `save_for_demo` is True**: After a live execution succeeds, it serializes the result and saves it to the `mocks_dir` via `_save_mock`.

This applies seamlessly to:
- `LLMService` (Ollama prompts/responses)
- `MarketService` (Alpaca market data)
- `ModelService` (PyTorch model generation)

### 1.2 `DataManager` Mocking
In addition to external API calls, `DataManager` (`apps/backend/data/data_manager.py`) is also "demo-aware". It overrides logic for loading active signals, reading forensic/social data, and identifying available signal/embedding hours. When in demo mode, it points these directory-scanning operations to the `mocks_dir`, ensuring the system only presents data that has been pre-recorded.

### 1.3 Endpoints and Administration
- `/v1/health`: Exposes the current `demo_mode` and `save_for_demo` statuses to clients (like the frontend).
- `/v1/admin/config/save-for-demo`: A POST endpoint allowing external scripts to dynamically toggle `save_for_demo` without needing to restart the backend.

---

## 2. Frontend Implementation

The Streamlit frontend (`apps/frontend/`) modifies its UI dynamically based on the backend's status.

### 2.1 State Management
Upon initialization in `app.py`, the frontend queries the `/v1/health` endpoint. It extracts the `demo_mode` boolean and assigns it to `st.session_state['demo_mode']`.

### 2.2 UI Restrictions
The frontend uses the `demo_mode` session state to gracefully degrade functionality and prevent users from attempting live actions:
*   **Restricted Inputs**: Date inputs are capped or constrained, and disabled. Default date boundaries are calculated based strictly on the mocked data provided rather than current real-world dates.
*   **Disabled Buttons**: "Generate Signals" and feature/embedding update buttons are either disabled or completely hidden (`if not demo_mode`).
*   **Locked Parameters**: Model selection dropdowns and LLM temperature sliders are locked (`disabled=demo_mode`), as the recorded mock data corresponds strictly to the model configurations used during the recording phase.

---

## 3. Workflow Automation: `record_demo_workflow.py`

The `record_demo_workflow.py` script serves as the crucial bridge that populates the mock data. It orchestrates the creation of a realistic subset of application state.

### Execution Flow:
1.  **Toggle Recording**: Sends a request to `/v1/admin/config/save-for-demo` with `{"enabled": True}` to turn on backend recording.
2.  **Date Selection**: Fetches available market hours (`/v1/market/hours`) and groups them, allowing the user to select the past `N` days (default 1) to record.
3.  **Signal Generation**: Calls `/v1/signals/generate` for the targeted hours. The backend generates real signals and transparently saves them to the mocks directory due to `RecordableService`.
4.  **LLM Explanations**: Iterates through every generated signal and triggers `/v1/llm/explain`. The LLM's response for each specific ticker/hour is cached.
5.  **Social Analysis**: Calls `/v1/llm/analyze-social` on a per-hour basis, and then finally generates a global summary for the overall timeframe. 
6.  **Cleanup**: Reverts the backend by disabling `save_for_demo`.

### Accompanying Script (`refresh-demo.sh`)
After `record_demo_workflow.py` populates the `mocks_dir`, `refresh-demo.sh` triggers the building of `vectra-backend-demo:latest` via `Containerfile.demo`. This packages the application specifically with the mocked payload, producing a lightweight, stateless, and fully standalone demo container that requires zero external API keys.

---

## Summary
The demo architecture is exceptionally clean and relies on a well-executed "VCR-style" interception pattern. By centralizing the mocking logic at the `RecordableService` and `DataManager` layers, the core application code remains entirely unaware of whether it is running live or in a demo state. The automated scripts guarantee that the demo artifacts are consistent and representative of actual application behavior.
