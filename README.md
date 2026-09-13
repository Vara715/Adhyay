# ADHYAY — Autonomous Customer & Operations Resolution Agent

Adhyay is a local-first, lightweight, agentic customer resolution and operations investigation platform built for **Track 3 (Smart Automation) — Problem Statement 5 (Autonomous Customer Resolution Agent)**.

Rather than relying on static chat templates, hard-coded decision trees, or superficial text classification, Adhyay operates as a true autonomous agent. It dynamically investigates customer orders, queries policies and inventory, selects permitted remediation actions, permission-gates high-risk operations via human approval, verifies post-action database mutations, adapts when blocked, and escalates safely when constraints prevent automated resolution.

---

## Table of Contents

- [Hackathon Track & Problem Statement](#hackathon-track--problem-statement)
- [Target Users](#target-users)
- [The Solution](#the-solution)
- [Why Adhyay is Agentic](#why-adhyay-is-agentic)
- [Customer Resolution Workflow](#customer-resolution-workflow)
- [System Architecture](#system-architecture)
  - [Agent Controller](#agent-controller)
  - [LLM Layer & Fallback](#llm-layer--fallback)
  - [Customer & Order Data Layer](#customer--order-data-layer)
  - [Investigation Tools](#investigation-tools)
  - [Deterministic Policy Engine](#deterministic-policy-engine)
  - [Real-Time Inventory](#real-time-inventory)
  - [Customer Resolution Actions](#customer-resolution-actions)
  - [Permission Gating & Human Approval](#permission-gating--human-approval)
  - [Post-Action Verification & Anti-False Success](#post-action-verification--anti-false-success)
  - [Dynamic Adaptation & Safe Escalation](#dynamic-adaptation--safe-escalation)
  - [Robust Failure Handling](#robust-failure-handling)
- [Enterprise Frontend Console](#enterprise-frontend-console)
- [Deterministic Simulation Scenarios](#deterministic-simulation-scenarios)
- [Local Setup & Running](#local-setup--running)
- [LLM Configuration](#llm-configuration)
- [Environment Variables](#environment-variables)
- [Testing](#testing)
- [Deployment & Demo Instructions](#deployment--demo-instructions)

---

## Hackathon Track & Problem Statement

- **Track**: Track 3 — Smart Automation
- **Problem Statement**: Problem Statement 5 (PS5) — Autonomous Customer Resolution Agent
- **Core Challenge**: Build an agentic system capable of understanding customer resolution goals, retrieving relevant customer, order, policy, and inventory evidence, dynamically choosing resolution paths without hard-coded sequences, executing permitted simulated actions, verifying state changes, adapting under failure/constraints, and escalating safely when resolution cannot be completed automatically.

---

## Target Users

1. **E-Commerce & Enterprise Support Leads**: Need automated, reliable customer issue resolution for refunds, replacements, and cancellations without manual agent overhead.
2. **Customer Experience (CX) Ops Teams**: Require clear auditability, permission boundaries for high-value financial actions, and zero false-success reporting.
3. **Automated Operations Auditors**: Need structured evidence, baseline-vs-actual state verification, and safe human-in-the-loop escalation queues.

---

## The Solution

Adhyay bridges the gap between AI reasoning and deterministic business execution. It combines:
- A **Single-Controller Investigation Engine** that executes an evidence-driven loop.
- A **16-Tool Read-Only Investigation Suite** for customer profiles, order fulfillment, product catalog, company policies, inventory stock, and system telemetry.
- An **8-Action Remediation Engine** supporting refunds, replacements, cancellations, escalations, purchase requests, and deployment rollbacks.
- A **Permission & Verification Boundary** that halts high-risk financial actions for human review and independently validates database state changes.
- An **Enterprise Dark-Mode React Console** with real-time state binding, a 10-card structured resolution layout, and an 8-stage visual workflow stepper.

---

## Why Adhyay is Agentic

Adhyay satisfies all criteria of an autonomous AI agent:

1. **Goal-Driven Autonomy**: Accepts high-level natural language goals (e.g., *"Customer CUST-801 received defective headphones in order ORD-9001. Resolve the issue."*).
2. **Dynamic Evidence-Based Path Selection**: Never follows a rigid sequence (`customer → order → policy → inventory → action`). Instead, the agent ranks candidates dynamically based on evidence, policy eligibility, inventory levels, and tool outcomes.
3. **Environment Perception**: Observes system state changes, inventory counts, policy rules, and tool failures through structured observations.
4. **State Mutation & Remediation**: Executes actual database mutations (updating order status to `refunded`, `cancelled`, or dispatching replacement units).
5. **Self-Adaptation**: Automatically pivots strategy when blocked (e.g., switching from replacement to refund when stock is 0, or adapting after a tool outage).
6. **Self-Verification**: Never assumes an action worked; queries the system post-action and compares against pre-action baselines.
7. **Permission Boundaries**: Recognizes its own authority limit and pauses execution for human approval when financial thresholds are exceeded.

---

## Customer Resolution Workflow

Adhyay visualizes and executes resolutions through an explicit 8-stage pipeline:

```text
  ┌──────┐    ┌───────────────┐    ┌──────────┐    ┌──────────┐
  │ GOAL │ ──►│ INVESTIGATION │ ──►│ EVIDENCE │ ──►│ DECISION │
  └──────┘    └───────────────┘    └──────────┘    └──────────┘
                                                        │
  ┌────────────┐    ┌──────────────┐    ┌─────────┐     │
  │ RESOLUTION │ ◄──│ VERIFICATION │ ◄──│ ACTION  │ ◄───┘
  │/ESCALATION │    └──────────────┘    └─────────┘
  └────────────┘           │                 
        ▲                  ▼                 
        └────────────┌────────────┐          
                     │ ADAPTATION │          
                     └────────────┘          
```

---

## System Architecture

```text
User / Dashboard (React + Vite)
       │
       ▼  HTTP REST Polling (/api)
FastAPI Backend
       │
       ├──► Agent Controller (Single Investigation Loop & Case State Machine)
       │         │
       │         ├──► LLM / Decision Layer (Ollama/Groq/vLLM or EvidenceBasedProvider)
       │         │
       │         ├──► Tool Registry (16 Read-Only Investigation Tools)
       │         │
       │         └──► Action Registry (8 Remediation Actions & Verification Engine)
       │                   │
       │                   ├──► Low-Risk Action: Auto-Execute ──► Baseline Capture ──► Verify
       │                   └──► High-Risk Action: Pause (AWAITING_APPROVAL) ──► Human Review ──► Execute ──► Verify
       │
       └──► Simulated Company Environment (8 Deterministic Scenarios & SQLite/Memory Repository)
```

### Agent Controller
The `AgentController` (`backend/agent/controller.py`) manages session lifecycle, enforces step budgets (`max_steps`), tracks timeouts, and drives `CustomerCase` state transitions:
`OPEN` $\rightarrow$ `INVESTIGATING` $\rightarrow$ `AWAITING_APPROVAL` $\rightarrow$ `ACTION_IN_PROGRESS` $\rightarrow$ `VERIFYING` $\rightarrow$ `RESOLVED` / `ESCALATED` / `FAILED`.

### LLM Layer & Fallback
The LLM layer (`backend/llm/`) features a provider-neutral interface supporting Ollama, Groq, vLLM, Together, Fireworks, and custom OpenAI-compatible `/v1` endpoints. If credentials are unconfigured or an endpoint is unreachable, Adhyay automatically logs the fallback and runs seamlessly using the local `EvidenceBasedDecisionProvider`.

### Customer & Order Data Layer
Deterministic models (`backend/models/customer.py`) maintain customer profiles (`Customer`) with tiers (`VIP`, `Standard`, `Gold`), order counts, and spend history, alongside individual customer orders (`CustomerOrder`) tracking fulfillment status, refund state, replacement state, and cancellation state.

### Investigation Tools
16 registered read-only tools (`backend/tools/`):
- **Customer Tools**: `get_customer`, `get_order`, `get_customer_orders`, `get_product_details`, `get_policy`, `check_customer_resolution_eligibility`, `get_customer_inventory`.
- **Operational Tools**: `get_revenue_metrics`, `get_order_metrics`, `get_product_sales`, `get_inventory_status`, `get_supplier_status`, `get_payment_status`, `get_service_health`, `get_recent_deployments`, `get_system_logs`.

### Deterministic Policy Engine
`GetPolicyTool` and `CheckResolutionEligibilityTool` enforce local policies:
- **Refund Policy**: Max auto-refund ₹5,000; returns allowed within 14 days; VIP fast-tracking enabled.
- **Replacement Policy**: Requires available inventory (`on_hand - reserved > 0`); 30-day replacement window.
- **Cancellation Policy**: Auto-cancellation allowed for `processing`/`pending` orders; forbidden post-dispatch (`shipped`/`delivered`).

### Real-Time Inventory
`GetCustomerInventoryTool` queries stock levels (`on_hand`, `reserved`, `available_for_replacement`) to verify unit availability prior to dispatching replacements.

### Customer Resolution Actions
8 registered state-changing actions (`backend/tools/actions.py`):
- **Customer Actions**: `issue_refund`, `create_replacement`, `cancel_order`, `escalate_customer_case`.
- **Operational Actions**: `create_purchase_request`, `rollback_deployment`, `create_support_ticket`, `request_human_approval`.

### Permission Gating & Human Approval
Actions are categorized by risk:
- **Low-Risk**: Executed automatically (e.g. refunds < ₹5,000, replacement dispatch, cancellations).
- **High-Risk**: High-value financial refunds ($\ge \text{₹}5,000$) or production rollbacks. The controller pauses execution, sets status to `AWAITING_APPROVAL`, and awaits human approval (`POST /api/runs/{id}/approval`).

### Post-Action Verification & Anti-False Success
Every executed action undergoes mandatory verification:
1. `capture_baseline`: Captures state prior to action execution.
2. `execute`: Mutates simulated database state.
3. `verify`: Re-queries system state and compares against baseline.
- **CRITICAL RULE**: A case is marked `RESOLVED` **ONLY IF** objective is completed, expected state changed, and verification status is `verified`. If verification is `failed` or `inconclusive`, status becomes `FAILED` with `unresolved_issues`.

### Dynamic Adaptation & Safe Escalation
- **Stockout Adaptation**: If replacement stock is 0, the agent automatically pivots to evaluate refund eligibility.
- **Post-Dispatch Policy Restriction**: If cancellation is requested for a shipped order, the agent executes `escalate_customer_case` to safely route the case to a human logistics agent.

### Robust Failure Handling
Adhyay gracefully handles missing customers, missing orders, empty/invalid goals, tool timeouts, tool outages, malformed LLM responses, and unverified actions without crashing, hallucinating, or claiming false success.

---

## Enterprise Frontend Console

The React + Vite dashboard (`frontend/src/app.tsx`) provides an enterprise dark-mode resolution console with 10 main screen section cards:

1. **CUSTOMER CASE**: Case ID, customer name/ID, tier badge, reported issue, requested resolution, status badge.
2. **CUSTOMER PROFILE**: Profile details, contact email, tier, total orders, total spent in ₹, history summary.
3. **ORDER DETAILS**: Order ID, product details, price, order status, fulfillment status, resolution state matrix.
4. **POLICY & ELIGIBILITY**: Resolution policies, eligibility evaluation result, approval rules, constraint blocks.
5. **INVENTORY AVAILABILITY**: Product ID, stock on hand, reserved units, available replacement count, in-stock indicator.
6. **AGENT ACTIVITY LOG**: Chronological tool calls timeline, concise tool outputs, failure events, strategy adaptation logs.
7. **DECISION ENGINE**: Current objective, hypothesis, selected remediation path, decision rationale.
8. **REMEDIATION ACTION & APPROVAL**: Action name, permission level badge, human approval request box with `Approve`/`Reject` buttons when awaiting approval.
9. **POST-ACTION VERIFICATION**: Pre-action baseline vs post-action state diff comparison, verification outcome badge (`VERIFIED`/`FAILED`/`INCONCLUSIVE`), outcome details.
10. **FINAL CASE RESOLUTION**: Terminal status badge (`RESOLVED`/`ESCALATED`/`FAILED`), resolution conclusion summary, unresolved issues list.

---

## Deterministic Simulation Scenarios

Adhyay includes 8 reproducible simulation scenarios (4 PS5 Customer Resolution + 4 Operational):

1. **Damaged Product Replacement Available (`customer_damaged_replacement_available`)**: Replacement requested for defective item; inventory in stock; replacement executed and verified $\rightarrow$ `RESOLVED`.
2. **Replacement Stockout Adapts to Refund (`customer_replacement_out_of_stock_adapts_refund`)**: Replacement requested; stock is 0; agent adapts to refund eligibility; refund executed and verified $\rightarrow$ `RESOLVED`.
3. **Post-Dispatch Cancellation Policy Escalation (`customer_refund_denied_policy_escalation`)**: Shipped order cancellation requested; policy forbids auto-cancellation post-dispatch; agent executes `escalate_customer_case` $\rightarrow$ `ESCALATED`.
4. **Investigation Tool Failure Adaptation (`customer_investigation_tool_failure_adapts`)**: `get_customer_inventory` tool failure injected; agent detects error, adapts path, completes safely.
5. **Inventory & Supplier Failure (`inventory_supplier_failure`)**: Operational supplier delay stockout.
6. **Payment Failure (`payment_failure`)**: Operational payment gateway timeout surge.
7. **Deployment Service Failure (`deployment_service_failure`)**: Operational release error spike requiring high-risk rollback approval.
8. **Misleading Initial Hypothesis (`misleading_initial_hypothesis`)**: Operational shipping-fee pricing configuration anomaly.

---

## Local Setup & Running

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

## LLM Configuration

Adhyay runs completely out-of-the-box in deterministic rule-based mode without requiring any LLM API keys.

To connect an LLM endpoint, set environment variables in `.env` or configure runtime credentials interactively in the web dashboard's **LLM Settings** panel:

- **Ollama (Local)**: `LLM_PROVIDER=ollama`, `LLM_MODEL=llama3.1`, `LLM_BASE_URL=http://localhost:11434/v1`
- **Groq Cloud**: `LLM_PROVIDER=groq`, `LLM_API_KEY=gsk_...`, `LLM_MODEL=llama-3.3-70b-versatile`
- **vLLM / LM Studio / OpenAI-compatible**: `LLM_PROVIDER=vllm`, `LLM_BASE_URL=http://localhost:8000/v1`

---

## Environment Variables

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `ollama`, `vllm`, `lmstudio`, `groq`, `together`, `fireworks`, or blank for deterministic mode | `""` |
| `LLM_API_KEY` | Credential for LLM endpoint (never exposed in UI or logs) | `""` |
| `LLM_MODEL` | Model identifier (e.g. `llama3.1`, `llama-3.3-70b-versatile`) | `""` |
| `LLM_BASE_URL` | Explicit OpenAI-compatible `/v1` base URL | `""` |
| `APP_ENV` | Runtime environment label | `development` |
| `APP_HOST` / `APP_PORT` | Local API bind address and port | `127.0.0.1:8000` |
| `CORS_ORIGINS` | Permitted browser origins | `http://localhost:5173` |

---

## Testing

Run the complete backend unit, integration, and robustness test suite (**140 tests**):

```powershell
python -m unittest discover tests
```

Build the production frontend bundle:

```powershell
cd frontend
npm run build
```

---

## Deployment & Demo Instructions

### Single-Command Production Serving
If `frontend/dist` exists, FastAPI automatically mounts the static dashboard:

```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Access the complete application directly at `http://127.0.0.1:8000`.

### Docker Deployment

```bash
docker build -t adhyay .
docker run -p 8000:8000 --env-file .env adhyay
```

### Known Limitation: Single In-Memory Run Store
Run state is stored in memory (`_RUNS` in `backend/api/runs.py`) to maintain thread safety and avoid database lock contention during fast demo polling. Deploy with a single instance/worker for hackathon presentations.
