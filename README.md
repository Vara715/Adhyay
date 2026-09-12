# ADHYAY — Autonomous Customer & Operations Resolution Agent

Adhyay is a lightweight, local-first agentic operations investigator and customer/operations resolution system built for **Track 3 (Smart Automation) — Problem Statement 5 (Autonomous Customer Resolution Agent)**.

Rather than merely classifying issues or generating static text responses, Adhyay dynamically investigates root causes using structured tools, adapts to data quality issues/outages, proposes safe corrective actions, permission-gates high-risk operations via human approval, and verifies post-action state changes before concluding.

---

## Key Features

- **Goal-Driven Execution**: Takes natural-language operational goals and dynamically selects investigation steps.
- **Dynamic Tool Selection**: Discovers and executes 9 read-only inspection tools and 4 state-changing action tools.
- **Agentic Adaptation**: Adapts when data sources fail, data is stale, or evidence contradicts current hypotheses.
- **Safety & Human Approval**: Categorizes actions into `read_only`, `low_risk`, and `high_risk`. High-risk actions (e.g. production rollbacks or high-cost procurement) pause execution and require explicit human approval.
- **Mandatory Post-Action Verification**: Every executed action captures a pre-action baseline and compares post-action state changes. Outcomes are classified as `verified`, `failed`, or `inconclusive`. Failed or inconclusive verification prevents false claims of success.
- **Lightweight Architecture**: Single-controller backend built with FastAPI and SQLite/in-memory deterministic simulation data; modern React + Vite frontend dashboard. No Redis, Kafka, Kubernetes, vector databases, or multi-agent overhead required.

---

## System Architecture

```text
User / Dashboard (React + Vite)
       │
       ▼  HTTP REST Polling (/api)
FastAPI Backend
       │
       ├──► Agent Controller (Single Investigation Loop)
       │         │
       │         ├──► Decision Policy (LLMProvider / EvidenceBasedDecisionProvider)
       │         │
       │         ├──► Tool Registry (9 Read-Only Tools)
       │         │
       │         └──► Action Registry (4 Action Tools & Verification Engine)
       │
       └──► Simulated Company Environment (4 Deterministic Scenarios)
```

---

## Demo Scenarios

Adhyay includes four reproducible, deterministic simulation scenarios:

1. **Inventory & Supplier Failure (`inventory_supplier_failure`)**: Best-selling product is out of stock due to a delayed supplier shipment. Tool outage occurs on initial inventory check; agent recovers, checks system logs and supplier status, and proposes replenishment.
2. **Payment Failure (`payment_failure`)**: Payment gateway timeout surge causes checkout payment drops. Agent analyzes payment metrics and service health to isolate the gateway incident.
3. **Deployment Service Failure (`deployment_service_failure`)**: Checkout deployment `DEP-502` introduces error surge. Agent detects degradation from logs and service metrics, proposes `rollback_deployment` (high-risk), pauses for human approval, executes rollback upon approval, and verifies service health returns to `healthy`.
4. **Misleading Initial Hypothesis (`misleading_initial_hypothesis`)**: Low inventory initially looks suspicious, but support tickets and pricing logs point to a shipping-fee configuration update `DEP-503`. Agent avoids false inventory conclusions.

---

## Setup & Running Locally

### Prerequisites
- Python 3.11+
- Node.js 20+

### 1. Environment Setup

```powershell
# Copy environment configuration
Copy-Item .env.example .env

# Create and activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Run Backend API

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
Confirm backend availability at `http://127.0.0.1:8000/api/health`.

### 3. Run Frontend Dashboard

```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Environment Variables

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | Selected LLM provider adapter (optional; local decision fallback used if unconfigured) | `""` |
| `LLM_API_KEY` | Credential for LLM provider (never exposed in UI or logs) | `""` |
| `LLM_MODEL` | Model identifier | `""` |
| `APP_ENV` | Runtime environment label | `development` |
| `APP_HOST` / `APP_PORT` | Local API bind address and port | `127.0.0.1:8000` |
| `CORS_ORIGINS` | Permitted browser origins | `http://localhost:5173` |

---

## Testing

Run the complete backend unit test suite (68 tests covering tools, LLM abstraction, agent controller, adaptation, actions, verification, REST API, demo scenarios, and robustness):

```powershell
python -m unittest discover tests
```

Build the production frontend bundle:

```powershell
cd frontend
npm run build
```

---

## Single-Command Production Serving

If the frontend is built (`frontend/dist` exists), FastAPI automatically mounts the static dashboard, allowing single-process execution:

```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Access the complete dashboard directly at `http://127.0.0.1:8000`.
