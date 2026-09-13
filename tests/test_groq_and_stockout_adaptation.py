"""Unit tests for Groq LLM decision recording, fallbacks, stockout adaptation, and refund verification."""

from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider, LLMDecisionProvider
from backend.config import get_settings, reset_llm_settings, update_llm_settings
from backend.data.database import SimulatedCompanyRepository
from backend.llm.client import LLMClient
from backend.llm.provider import LLMProvider, LLMProviderError, test_llm_provider_connection
from backend.models.agent import AgentDecision, AgentState, CustomerCase
from backend.models.llm import LLMRequest, LLMResponse
from backend.models.tools import ToolCall
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class DummySuccessProvider(LLMProvider):
    """Mock LLM Provider that simulates a successful Groq response."""

    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        return LLMResponse(
            content="Investigating customer order.",
            tool_call=ToolCall(name="get_order", arguments={"order_id": "ORD-9002"}),
        )


class DummyAuthFailProvider(LLMProvider):
    """Mock LLM Provider that simulates an auth error."""

    def complete(self, request: LLMRequest, *, model: str) -> LLMResponse:
        raise LLMProviderError("Authentication failed (HTTP 401). Invalid Groq API key.")


class TestGroqAndStockoutAdaptation(TestCase):
    def setUp(self):
        reset_llm_settings()
        self.repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        self.tool_registry = ToolRegistry(self.repo)
        self.action_registry = ActionRegistry(self.repo, Decimal("50000"))

    def tearDown(self):
        reset_llm_settings()

    def test_1_groq_successful_decision_source(self):
        """Verify that a successful LLM provider sets decision_source = GROQ_LLM."""
        update_llm_settings(provider="groq", api_key="gsk_test123", model="llama-3.3-70b-versatile")
        client = LLMClient(provider=DummySuccessProvider(), model="llama-3.3-70b-versatile")
        llm_provider = LLMDecisionProvider(client)
        controller = AgentController(self.tool_registry, llm_provider, action_registry=self.action_registry, max_steps=1)

        state = controller.run("My laptop stand arrived damaged in ORD-9002.")
        self.assertEqual(state.decision_source, "GROQ_LLM")
        self.assertTrue(state.llm_success)
        self.assertEqual(state.llm_provider, "groq")
        self.assertEqual(state.llm_model, "llama-3.3-70b-versatile")
        self.assertIsNone(state.fallback_reason)

    def test_2_groq_auth_failure_fallback_reason(self):
        """Verify auth failure sets decision_source = RULE_BASED_FALLBACK and safe fallback reason."""
        update_llm_settings(provider="groq", api_key="gsk_invalid_key_9999", model="llama-3.3-70b-versatile")
        client = LLMClient(provider=DummyAuthFailProvider(), model="llama-3.3-70b-versatile")
        llm_provider = LLMDecisionProvider(client)
        controller = AgentController(self.tool_registry, llm_provider, action_registry=self.action_registry, max_steps=3)

        state = controller.run("My laptop stand arrived damaged in ORD-9002.")
        self.assertEqual(state.decision_source, "RULE_BASED_FALLBACK")
        self.assertFalse(state.llm_success)
        self.assertIn("Authentication failed", state.fallback_reason)
        self.assertNotIn("gsk_invalid_key_9999", state.fallback_reason)

    def test_3_groq_connection_verifier(self):
        """Verify connection test behavior."""
        update_llm_settings(provider="groq", api_key="gsk_test", model="llama-3.3-70b-versatile")
        settings = get_settings()
        self.assertTrue(settings.llm_is_configured)
        ok, msg = test_llm_provider_connection(settings)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)

    def test_4_stockout_adaptation_to_refund(self):
        """Verify stockout (replacement inventory = 0) triggers adaptation to refund and reaches RESOLVED."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        tool_registry = ToolRegistry(repo)
        action_registry = ActionRegistry(repo, Decimal("50000"))
        controller = AgentController(tool_registry, EvidenceBasedDecisionProvider(), action_registry=action_registry, max_steps=10)

        state = controller.run("My product arrived damaged in order ORD-9003. I want a replacement.")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any(p.action == "issue_refund" and p.approval_status == "executed" for p in state.action_proposals))
        self.assertTrue(any(e.event_type == "adaptation" for e in state.events))

    def test_5_retry_guard_prevents_infinite_replacement(self):
        """Verify LLMDecisionProvider raises error if create_replacement is proposed when stock is 0."""
        client = MagicMock()
        client.complete.return_value = LLMResponse(
            content="Proposing replacement.",
            tool_call=ToolCall(name="create_replacement", arguments={"order_id": "ORD-9003", "customer_id": "CUST-802", "product_id": "PR-300", "quantity": 1, "reason": "Replacement"}),
        )
        llm_provider = LLMDecisionProvider(client)
        state = AgentState(original_goal="Replacement requested.")
        state.tool_history.append(
            MagicMock(
                tool_call=ToolCall(name="check_customer_resolution_eligibility", arguments={"resolution_type": "replacement"}),
                result=MagicMock(ok=True, data={"blocked_by": "out_of_stock"}),
            )
        )
        with self.assertRaises(ValueError) as ctx:
            llm_provider.decide(state, [])
        self.assertIn("out of stock", str(ctx.exception).lower())

    def test_6_escalate_when_refund_forbidden(self):
        """Verify case escalates safely when cancellation/refund is forbidden by policy."""
        repo = SimulatedCompanyRepository("customer_refund_denied_policy_escalation")
        tool_registry = ToolRegistry(repo)
        action_registry = ActionRegistry(repo, Decimal("50000"))
        controller = AgentController(tool_registry, EvidenceBasedDecisionProvider(), action_registry=action_registry, max_steps=10)

        state = controller.run("I want to cancel order ORD-9004.")
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(any(p.action == "escalate_customer_case" for p in state.action_proposals))

    def test_7_no_false_resolved_without_executed_remediation(self):
        """Verify that a case is never marked RESOLVED if no remediation action was executed."""
        repo = SimulatedCompanyRepository("customer_wrong_product_received")
        tool_reg = ToolRegistry(repo)
        act_reg = ActionRegistry(repo, Decimal("50000"))
        ctrl = AgentController(tool_reg, EvidenceBasedDecisionProvider(), action_registry=act_reg, max_steps=1)
        res_state = ctrl.run("My headphone was broken.")
        self.assertNotEqual(res_state.customer_case.status, "RESOLVED")

    def test_A_wrong_image_no_false_stockout_adaptation(self):
        """TEST A: Biscuit image uploaded for laptop stand complaint -> CONTRADICTED -> ESCALATED with NO false stockout adaptation."""
        import os
        import tempfile
        from backend.models.attachments import EvidenceAttachment
        from backend.services.claim_validator import ClaimValidator

        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        tool_reg = ToolRegistry(repo)
        act_reg = ActionRegistry(repo, Decimal("50000"))
        ctrl = AgentController(tool_reg, EvidenceBasedDecisionProvider(), action_registry=act_reg, max_steps=10)

        # Create temporary file on disk so os.path.exists passes
        tmp_dir = tempfile.gettempdir()
        tmp_path = os.path.join(tmp_dir, "parle_g_biscuit.jpg")
        with open(tmp_path, "wb") as f:
            f.write(b"dummy image content")

        # Attach biscuit food image
        biscuit_attachment = EvidenceAttachment(
            attachment_id="ATT-FOOD-1",
            case_id="CASE-ORD-9002",
            filename="parle_g_biscuit.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=45000,
            storage_path=tmp_path,
            status="processed",
            extracted_text="Parle-G Gold Wheat Biscuits Pack 100g Food Snack Product",
        )

        state = AgentState(
            original_goal="My laptop stand arrived damaged in order ORD-9002. I want a replacement.",
            attachments=[biscuit_attachment],
            customer_case=CustomerCase(
                case_id="CASE-ORD-9002",
                customer_id="CUST-801",
                order_id="ORD-9002",
                original_goal="My laptop stand arrived damaged in order ORD-9002. I want a replacement.",
                issue="My laptop stand arrived damaged in order ORD-9002. I want a replacement.",
                requested_resolution="replacement",
                attachments=[biscuit_attachment],
            )
        )

        from time import monotonic
        res_state = ctrl._run_loop(state, monotonic())

        # Assert claim assessment = CONTRADICTED
        self.assertIsNotNone(res_state.customer_case.claim_assessment)
        self.assertEqual(res_state.customer_case.claim_assessment.claim_status, "CONTRADICTED")
        # Assert action = escalate_customer_case
        self.assertTrue(any(p.action == "escalate_customer_case" for p in res_state.action_proposals))
        # Assert final status = ESCALATED
        self.assertEqual(res_state.customer_case.status, "ESCALATED")
        # Assert original goal was preserved
        self.assertEqual(res_state.original_goal, "My laptop stand arrived damaged in order ORD-9002. I want a replacement.")
        self.assertEqual(res_state.customer_case.original_goal, "My laptop stand arrived damaged in order ORD-9002. I want a replacement.")
        # Assert no false stockout adaptation reason exists
        self.assertTrue(res_state.adaptation_reason is None or "stock" not in res_state.adaptation_reason.lower())

    def test_B_real_stockout_adapts_to_refund(self):
        """TEST B: Inventory = 0 -> stockout adaptation -> issue_refund -> RESOLVED."""
        repo = SimulatedCompanyRepository("customer_replacement_out_of_stock_adapts_refund")
        tool_registry = ToolRegistry(repo)
        action_registry = ActionRegistry(repo, Decimal("50000"))
        controller = AgentController(tool_registry, EvidenceBasedDecisionProvider(), action_registry=action_registry, max_steps=10)

        state = controller.run("My product arrived damaged in order ORD-9003. I want a replacement.")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any(p.action == "issue_refund" and p.approval_status == "executed" for p in state.action_proposals))

    def test_C_inventory_available_no_stockout_adaptation(self):
        """TEST C: Inventory = 48 available -> replacement executed -> RESOLVED with NO stockout adaptation."""
        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        tool_registry = ToolRegistry(repo)
        action_registry = ActionRegistry(repo, Decimal("50000"))
        controller = AgentController(tool_registry, EvidenceBasedDecisionProvider(), action_registry=action_registry, max_steps=10)

        state = controller.run("My package arrived damaged in ORD-9002. Replacement requested.")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertTrue(any(p.action == "create_replacement" for p in state.action_proposals))
        self.assertFalse(state.adaptation_required)

    def test_D_groq_success_decision_source(self):
        """TEST D: Successful Groq decision -> decision_source == GROQ_LLM, llm_success == true."""
        update_llm_settings(provider="groq", api_key="gsk_valid", model="llama-3.3-70b-versatile")
        client = LLMClient(provider=DummySuccessProvider(), model="llama-3.3-70b-versatile")
        llm_provider = LLMDecisionProvider(client)
        controller = AgentController(self.tool_registry, llm_provider, action_registry=self.action_registry, max_steps=1)

        state = controller.run("Check order status for ORD-9002.")
        self.assertEqual(state.decision_source, "GROQ_LLM")
        self.assertTrue(state.llm_success)

    def test_E_groq_failure_fallback_reason(self):
        """TEST E: Groq failure -> decision_source == RULE_BASED_FALLBACK, llm_success == false, fallback_reason populated."""
        update_llm_settings(provider="groq", api_key="gsk_invalid", model="llama-3.3-70b-versatile")
        client = LLMClient(provider=DummyAuthFailProvider(), model="llama-3.3-70b-versatile")
        llm_provider = LLMDecisionProvider(client)
        controller = AgentController(self.tool_registry, llm_provider, action_registry=self.action_registry, max_steps=3)

        state = controller.run("Check order status for ORD-9002.")
        self.assertEqual(state.decision_source, "RULE_BASED_FALLBACK")
        self.assertFalse(state.llm_success)
        self.assertIsNotNone(state.fallback_reason)

    def test_F_connection_success_but_decision_failure_distinction(self):
        """TEST F: Settings show is_configured = true, but decision call fails -> run decision_source == RULE_BASED_FALLBACK."""
        update_llm_settings(provider="groq", api_key="gsk_test_key", model="llama-3.3-70b-versatile")
        settings = get_settings()
        self.assertTrue(settings.llm_is_configured)

        client = LLMClient(provider=DummyAuthFailProvider(), model="llama-3.3-70b-versatile")
        llm_provider = LLMDecisionProvider(client)
        controller = AgentController(self.tool_registry, llm_provider, action_registry=self.action_registry, max_steps=2)

        state = controller.run("Investigate ORD-9002.")
        self.assertEqual(state.decision_source, "RULE_BASED_FALLBACK")
        self.assertIn("Authentication failed", state.fallback_reason)

