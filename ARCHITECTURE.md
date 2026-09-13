# ADHYAY — Architecture Specification

Adhyay is a lightweight, local-first autonomous customer resolution and operations investigation system designed for **Track 3 (Smart Automation) — Problem Statement 5 (Autonomous Customer Resolution Agent)**.

This document details the system design, data models, state transitions, tool interfaces, permission framework, post-action verification, failure handling, and frontend architecture.

---

## 1. High-Level System Architecture

```text
                               ┌────────────────────────────────────────┐
                               │     Enterprise Dashboard Console       │
                               │        (React 18 + Vite + CSS)         │
                               └──────────────────┬─────────────────────┘
                                                  │
                                                  │ HTTP REST Polling / REST APIs
                                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       FastAPI Backend App                                       │
│                                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                              Agent Controller & State Machine                              │  │
│  │                    (backend/agent/controller.py & backend/models/agent.py)                 │  │
│  └───────┬───────────────────────────────┬───────────────────────────────┬────────────────────┘  │
│          │                               │                               │                       │
│          ▼                               ▼                               ▼                       │
│  ┌───────────────┐              ┌─────────────────┐             ┌──────────────────┐             │
│  │ Decision Layer│              │ Investigation   │             │ Remediation      │             │
│  │ (LLM / Local) │              │ Tools (16)      │             │ Actions (8)      │             │
│  └───────┬───────┘              └────────┬────────┘             └────────┬─────────┘             │
│          │                               │                               │                       │
│          │                               │                               │  Baseline Capture     │
│          │                               │                               ▼  & Mutation           │
│          │                               │                      ┌──────────────────┐             │
│          │                               │                      │ Verification     │             │
│          │                               │                      │ Engine           │             │
│          │                               │                      └────────┬─────────┘             │
│          │                               │                               │                       │
│          └───────────────────────────────┼───────────────────────────────┘                       │
│                                          │                                                       │
│                                          ▼                                                       │
│                         ┌──────────────────────────────────┐                                     │
│                         │ Simulated Environment Repository │                                     │
│                         │   (Customer, Order, Inventory,   │                                     │
│                         │   Policy & Operations Memory Store│                                     │
│                         └──────────────────────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Customer Case State Machine

The customer resolution lifecycle is tracked explicitly via the `CustomerCase` model ([`agent.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/models/agent.py)) and governed by `AgentController` ([`controller.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/agent/controller.py)):

```text
 ┌──────┐     ┌──────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌───────────┐     ┌──────────┐
 │ OPEN │ ──► │INVESTIGATING │ ──► │AWAITING_APPROVAL │ ──► │ACTION_IN_PROGRESS  │ ──► │ VERIFYING │ ──► │ RESOLVED │
 └──────┘     └──────────────┘     └──────────────────┘     └────────────────────┘     └─────┬─────┘     └──────────┘
                     │                      │                          │                     │                ▲
                     │                      │ (Rejected)               │ (Action Failure)    │ (Unverified)   │
                     ▼                      ▼                          ▼                     ▼                │
              ┌─────────────┐        ┌─────────────┐            ┌─────────────┐       ┌─────────────┐         │
              │  ESCALATED  │        │  ESCALATED  │            │   FAILED    │       │   FAILED    │ ────────┘
              └─────────────┘        └─────────────┘            └─────────────┘       └─────────────┘  (If adapted
                                                                                                        & re-verified)
```

### Case Status Definitions

- **`OPEN`**: Initial state upon case creation. Customer request and initial goal registered.
- **`INVESTIGATING`**: Agent actively running read-only inspection tools (`get_customer`, `get_order`, `get_policy`, `get_customer_inventory`).
- **`AWAITING_APPROVAL`**: Agent requested a high-risk financial action (e.g. refund $\ge \text{₹}5,000$). Execution is paused pending human review.
- **`ACTION_IN_PROGRESS`**: Low-risk action auto-approved or high-risk action approved by human. Baseline state captured; database mutation in progress.
- **`VERIFYING`**: State mutation complete. Baseline capture compared against post-action database query.
- **`RESOLVED`**: Objective completed, expected database mutation verified (`verified`), zero unresolved issues remaining.
- **`ESCALATED`**: Resolution impossible due to policy restrictions (e.g. post-dispatch cancellation) or human approval rejection. Case handed off safely to human support queue.
- **`FAILED`**: Unhandled system error, tool failure with no alternative path, or post-action verification failure.

---

## 3. Data Architecture & Customer/Order Models

### Customer Model (`Customer`)
Maintained in [`customer.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/models/customer.py):
- `customer_id`: Unique identifier (e.g., `CUST-801`).
- `name`: Customer full name.
- `tier`: VIP classification (`Standard`, `Gold`, `VIP`). Influences policy threshold eligibility.
- `email`: Contact email.
- `total_orders`: Cumulative count of orders.
- `total_spent`: Total customer lifetime spend in ₹.
- `relevant_history`: Past return/refund notes and support interaction history.

### Order Model (`CustomerOrder`)
Maintained in [`customer.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/models/customer.py):
- `order_id`: Unique identifier (e.g., `ORD-9001`).
- `customer_id`: Associated customer reference.
- `product_id`: Product purchased.
- `product_name`: Descriptive product title.
- `order_date`: ISO timestamp.
- `price`: Unit price in ₹.
- `order_status`: Order stage (`processing`, `shipped`, `delivered`, `cancelled`).
- `fulfillment_status`: Logistic state (`unfulfilled`, `fulfilled`, `returned`).
- `issue_information`: Reported issue text (e.g., `"Damaged unit received"`).
- `refund_state`: Refund lifecycle state (`none`, `pending`, `refunded`, `rejected`).
- `replacement_state`: Replacement lifecycle state (`none`, `requested`, `dispatched`, `rejected`).
- `cancellation_state`: Cancellation state (`none`, `requested`, `cancelled`, `rejected`).

---

## 4. Agent Controller & Anti-False-Success Verification Engine

The `AgentController` ([`controller.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/agent/controller.py)) drives the autonomous resolution loop:

1. **Goal Registration**: Initializes `CustomerCase` and `AgentRunState`.
2. **Investigation & Tool Selection**: Invokes `DecisionProvider` (LLM or local deterministic provider) to select the next tool.
3. **Execution**: Runs registered tools safely. Catches exceptions and logs tool failure events.
4. **Permission & Risk Evaluation**: Checks action risk level (`READ_ONLY`, `LOW_RISK`, `HIGH_RISK`). If high-risk, sets status to `AWAITING_APPROVAL` and pauses run loop.
5. **Post-Action Baseline & Verification**:
   - Before executing state-changing actions, `capture_baseline` snapshots order and inventory parameters.
   - After action execution, `verify` re-queries simulated storage.
   - **Anti-False-Success Rule**:
     $$\text{Status} = \begin{cases} \text{RESOLVED} & \text{if } \text{Verification} = \text{verified} \land \text{UnresolvedIssues} = \emptyset \\ \text{FAILED} / \text{ESCALATED} & \text{otherwise} \end{cases}$$
     An action attempt without empirical verification can **never** trigger `RESOLVED`.

---

## 5. Tool & Action Registries

### Investigation Tools (16 Tools)
Registered in [`registry.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/tools/registry.py):

| Tool Name | Scope | Category | Description |
| :--- | :--- | :--- | :--- |
| `get_customer` | PS5 | Customer | Fetches customer profile, tier, and history. |
| `get_order` | PS5 | Order | Fetches order fulfillment, pricing, and issue info. |
| `get_customer_orders` | PS5 | Order | Retrieves all past orders for a specific customer. |
| `get_product_details` | PS5 | Catalog | Retrieves product description, specs, and price. |
| `get_policy` | PS5 | Policy | Queries policy rules for refund, replacement, or cancellation. |
| `check_customer_resolution_eligibility` | PS5 | Policy | Evaluates eligibility for customer resolution based on tier and order date. |
| `get_customer_inventory` | PS5 | Inventory | Checks available stock levels (`on_hand`, `reserved`, `available_for_replacement`). |
| `get_revenue_metrics` | Ops | Finance | Analyzes daily revenue trends. |
| `get_order_metrics` | Ops | Operations | Checks overall order processing volume and delays. |
| `get_product_sales` | Ops | Catalog | Retrieves sales volume per SKU. |
| `get_inventory_status` | Ops | Inventory | Scans system-wide warehouse stock. |
| `get_supplier_status` | Ops | Logistics | Checks supplier delivery timelines and stock shortages. |
| `get_payment_status` | Ops | Finance | Inspects payment gateway success rate and error spikes. |
| `get_service_health` | Ops | System | Monitors microservice health metrics. |
| `get_recent_deployments` | Ops | Deployment | Inspects recent code releases and deployments. |
| `get_system_logs` | Ops | Telemetry | Searches system logs for operational errors. |

### Remediation Actions (8 Actions)
Registered in [`actions.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/tools/actions.py):

| Action Name | Risk Level | Mutates State | Description |
| :--- | :--- | :--- | :--- |
| `issue_refund` | Low / High ($\ge \text{₹}5\text{k}$) | Yes | Mutates `refund_state` to `refunded`. High values trigger approval. |
| `create_replacement` | Low-Risk | Yes | Decrements inventory by 1, sets `replacement_state` to `dispatched`. |
| `cancel_order` | Low-Risk | Yes | Sets `order_status` to `cancelled`, restores reserved inventory. |
| `escalate_customer_case` | Low-Risk | Yes | Mutates case status to `ESCALATED`, attaches audit trail for human agents. |
| `create_purchase_request` | Low / High | Yes | Triggers restocking purchase order. |
| `rollback_deployment` | High-Risk | Yes | Reverts recent production release. |
| `create_support_ticket` | Low-Risk | Yes | Creates internal operational issue ticket. |
| `request_human_approval` | Low-Risk | No | Explicitly requests human authorization. |

---

## 6. Permission & Safety Framework

Actions enforce strict risk evaluation:

$$\text{RiskLevel}(\text{action}, \text{params}) = \begin{cases} \text{HIGH\_RISK} & \text{if } \text{action} = \text{\texttt{issue\_refund}} \land \text{amount} \ge 5000 \\ \text{HIGH\_RISK} & \text{if } \text{action} = \text{\texttt{rollback\_deployment}} \\ \text{LOW\_RISK} & \text{otherwise} \end{cases}$$

If an action is `HIGH_RISK`, the controller halts processing, transitions status to `AWAITING_APPROVAL`, and emits an `approval_requested` event to the frontend.

---

## 7. Decision Layer & Provider Fallback

The decision engine ([`decisions.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/agent/decisions.py)) supports dual providers:

1. **`LLMDecisionProvider`**: Formats system prompt with available tools, policy constraints, current customer case state, and tool observation history. Sends structured request to configured LLM endpoint (Ollama, Groq, vLLM, OpenAI format) and parses structured JSON decisions.
2. **`EvidenceBasedDecisionProvider`**: Deterministic rule-based provider that analyzes evidence dynamically without external API calls:
   - Defective product + inventory available $\rightarrow$ `create_replacement`
   - Replacement requested + inventory out of stock $\rightarrow$ `issue_refund`
   - Order shipped + cancellation requested $\rightarrow$ `escalate_customer_case`
   - High value refund $\rightarrow$ `request_human_approval`

---

## 8. Enterprise Frontend Console Architecture

The frontend ([`frontend/src/app.tsx`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/frontend/src/app.tsx)) is built with React 18, TypeScript, and Vite. It connects to the backend REST API (`/api/runs`) via active polling (every 1,000ms while running).

### Layout Sections

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Header: Logo, Active Scenario Selector, Run Controls, LLM Configuration Panel          │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ 8-Stage Workflow Stepper: GOAL ➔ INVESTIGATION ➔ EVIDENCE ➔ DECISION ➔ ACTION ...      │
├──────────────────────────────────────────────────────┬─────────────────────────────────┤
│ Card 1: CUSTOMER CASE DETAILS                        │ Card 6: AGENT ACTIVITY LOG      │
│ Card 2: CUSTOMER PROFILE & HISTORY                   │ Card 7: DECISION ENGINE         │
│ Card 3: ORDER FULFILLMENT & RESOLUTION               │ Card 8: REMEDIATION ACTION &    │
│ Card 4: POLICY & ELIGIBILITY CONSTRAINTS             │         APPROVAL PANEL          │
│ Card 5: INVENTORY AVAILABILITY                       │ Card 9: POST-ACTION VERIFICATION│
│                                                      │ Card 10: FINAL CASE RESOLUTION  │
└──────────────────────────────────────────────────────┴─────────────────────────────────┘
```

---

## 9. Scenarios & Deterministic Simulation Engine

Defined in [`scenarios.py`](file:///c:/Users/Lenovo/Downloads/Adhyay/Adhyay-latest/backend/data/scenarios.py):

- **Scenario 1**: Damaged headphone replacement with full inventory $\rightarrow$ Replacement dispatched $\rightarrow$ `RESOLVED`.
- **Scenario 2**: Replacement requested, but inventory is 0 $\rightarrow$ Agent adapts strategy to refund $\rightarrow$ Refund processed $\rightarrow$ `RESOLVED`.
- **Scenario 3**: Shipped order cancellation requested $\rightarrow$ Policy forbids cancellation post-dispatch $\rightarrow$ Escalates safely $\rightarrow$ `ESCALATED`.
- **Scenario 4**: Inventory investigation tool outage injected $\rightarrow$ Agent detects tool error, adapts tool selection, resolves issue safely.
- **Scenarios 5-8**: Operational scenarios covering inventory supplier delays, payment gateway errors, high-risk deployment rollbacks, and misleading pricing hypotheses.

---

## 10. Robustness & Failure Modes

| Risk / Failure Mode | Handling Mechanism | Outcome |
| :--- | :--- | :--- |
| **Missing Customer/Order** | `GetCustomerTool` / `GetOrderTool` return structured error dict | Agent logs missing entity, avoids crashing, escalates case. |
| **Tool Outage / Error** | Exception caught in `execute_tool`, returns `success=False` | Agent detects failure in observation history, adapts tool choice. |
| **Unconfigured LLM Credentials** | Automatic fallback to `EvidenceBasedDecisionProvider` | Run completes deterministically without error. |
| **High Financial Amount** | Evaluated by permission matrix as `HIGH_RISK` | Pauses run at `AWAITING_APPROVAL` for human review. |
| **Unverified Action** | Post-action verification returns `failed` or `inconclusive` | Status set to `FAILED`, unresolved issues recorded. |
| **Exceeded Max Steps** | Controller enforces step limit budget | Run halts safely with `status=FAILED`, max step limit log. |

---

