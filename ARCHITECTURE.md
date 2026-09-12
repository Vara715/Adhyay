# Adhyay Architecture Document

Adhyay is a lightweight, local-first agentic operations investigation and customer resolution system built for Track 3 (Smart Automation) — Problem Statement 5 (Autonomous Customer Resolution Agent).

## High-Level Architecture Diagram

```text
User / Dashboard (React + Vite)
       │
       ▼  HTTP REST Polling / API
FastAPI Backend (/api)
       │
       ├──► Agent Controller (Single Investigation Loop)
       │         │
       │         ├──► LLM / Local Decision Policy (LLMProvider / EvidenceBasedProvider)
       │         │
       │         ├──► Tool Registry (9 Read-Only Inspection Tools)
       │         │
       │         └──► Action Registry (4 State-Changing Actions & Verification)
       │                   │
       │                   ├──► Low-Risk Action: Auto-Execute ──► Verify
       │                   └──► High-Risk Action: Pause (Approval Required) ──► Human Review ──► Execute ──► Verify
       │
       └──► Simulated Company Environment (Deterministic SQLite / Memory Store)
```

## Core Components & Responsibilities

1. **Frontend Dashboard (`frontend/src/`)**: Modern React + Vite dashboard displaying mission inputs, scenario selection, real-time structured activity timeline, current objective/hypothesis, evidence cards, human approval panel, and post-action verification outcome.
2. **Backend API (`backend/api/`)**: FastAPI endpoints for `/api/health`, `/api/scenarios`, `/api/runs`, `/api/runs/{run_id}`, `/api/runs/{run_id}/events`, and `/api/runs/{run_id}/approval`.
3. **Agent Controller (`backend/agent/controller.py`)**: Runs the investigation loop (`Goal → Decide → Select Tool/Action → Execute/Approve → Observe → Evaluate → Adapt → Verify → Outcome`). Enforces max steps, timeouts, and permission boundaries.
4. **Decision Layer (`backend/agent/decisions.py`)**: Maps LLM responses into structured `AgentDecision` objects (`tool`, `action`, or `finish`). Provides `EvidenceBasedDecisionProvider` as a deterministic local fallback.
5. **Tool & Action Registries (`backend/tools/`)**:
   - **Read-Only Tools (9)**: `get_revenue_metrics`, `get_order_metrics`, `get_product_sales`, `get_inventory_status`, `get_supplier_status`, `get_payment_status`, `get_service_health`, `get_recent_deployments`, `get_system_logs`.
   - **Action Tools (4)**: `create_purchase_request`, `rollback_deployment`, `create_support_ticket`, `request_human_approval`.
6. **Post-Action Verification (`backend/tools/actions.py`)**:
   - `capture_baseline`: Snapshots system parameters prior to action.
   - `verify`: Compares actual post-action state against baseline.
   - Categorizes outcome into `verified`, `failed`, or `inconclusive`. Non-verified outcomes automatically surface in `final_result.unresolved_issues`.
7. **Simulated Company Repository (`backend/data/database.py`)**: In-memory, resettable environment supporting 4 deterministic scenarios with failure injection and state mutation.

## Permission & Safety Matrix

| Permission Level | Actions | Approval Requirement | Execution Flow |
| :--- | :--- | :--- | :--- |
| **READ-ONLY** | All 9 inspection tools, `request_human_approval` | Allowed automatically | Immediate execution |
| **LOW-RISK** | `create_support_ticket`, low-cost `create_purchase_request` (< threshold) | Allowed automatically | Auto-execute ➔ Baseline Capture ➔ Verification |
| **HIGH-RISK** | `rollback_deployment`, high-cost `create_purchase_request` (≥ threshold) | Human Approval Required | Pause (`awaiting_approval`) ➔ Human Approve/Reject ➔ Execute ➔ Verification |

## Failure Handling & Adaptation

- **Tool Outage**: Agent detects tool errors (e.g. simulated inventory downtime), updates state, and seeks corroborating evidence (e.g. system logs) without hallucinating missing data.
- **Verification Failure**: If an action executes but state verification returns `failed` or `inconclusive`, the agent records verification notes and surfaces the issue in `unresolved_issues` rather than claiming false success.
