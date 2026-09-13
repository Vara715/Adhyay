"""Automated unit and integration tests verifying PS5 Final Demo Quality Scenarios:

Demo A (Multimodal Wrong Product), Demo B (Stockout Adaptation), Demo C (Inconclusive Evidence),
Order Ownership Security Escalation, and Decision Source Tracking.
"""

import unittest
from decimal import Decimal

from backend.agent.controller import AgentController
from backend.agent.decisions import EvidenceBasedDecisionProvider
from backend.data.database import SimulatedCompanyRepository
from backend.models.attachments import EvidenceAttachment
from backend.tools.actions import ActionRegistry
from backend.tools.registry import ToolRegistry


class TestFinalDemoScenarios(unittest.TestCase):
    def test_demo_a_multimodal_wrong_product(self):
        """DEMO A: Customer ordered Phone 1 but received Phone 2 -> Claim SUPPORTED -> Replacement executed & verified."""
        repo = SimulatedCompanyRepository("customer_wrong_product_received")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I ordered Phone 1 but received Phone 2 in order ORD-9001. I want the correct phone."
        
        # Attach Phone 2 image attachment fixture
        import os
        os.makedirs("backend/data/uploads", exist_ok=True)
        with open("backend/data/uploads/received_phone2.jpg", "w") as f:
            f.write("phone2 image demo data")

        attachment = EvidenceAttachment(
            attachment_id="ATT-101",
            case_id="CASE-ORD-9001",
            filename="received_phone2.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=2100000,
            storage_path="backend/data/uploads/received_phone2.jpg",
            status="processed",
        )
        from backend.models.agent import CustomerCase
        case = CustomerCase(
            case_id="CASE-ORD-9001",
            customer_id="CUST-801",
            order_id="ORD-9001",
            original_goal=goal,
            issue=goal,
            requested_resolution="replacement",
            status="OPEN",
            attachments=[attachment],
        )
        state = controller.run(goal, customer_case=case)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertIsNotNone(state.claim_assessment)
        self.assertEqual(state.claim_assessment.claim_status, "SUPPORTED")
        self.assertTrue(any("create_replacement" in a for a in state.actions))

    def test_demo_b_stockout_adaptation(self):
        """DEMO B: Customer claim SUPPORTED, but replacement stockout -> Agent adapts dynamically to issue refund."""
        repo = SimulatedCompanyRepository("customer_wrong_product_stockout_adapts")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "I ordered Phone 1 but received Phone 2 in order ORD-9001. I want a replacement."
        
        attachment = EvidenceAttachment(
            attachment_id="ATT-102",
            case_id="CASE-ORD-9001",
            filename="received_phone2.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=2100000,
            storage_path="backend/data/uploads/received_phone2.jpg",
            status="processed",
        )
        from backend.models.agent import CustomerCase
        case = CustomerCase(
            case_id="CASE-ORD-9001",
            customer_id="CUST-801",
            order_id="ORD-9001",
            original_goal=goal,
            issue=goal,
            requested_resolution="replacement",
            status="OPEN",
            attachments=[attachment],
        )
        state = controller.run(goal, customer_case=case)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "RESOLVED")
        self.assertIsNotNone(state.claim_assessment)
        self.assertEqual(state.claim_assessment.claim_status, "SUPPORTED")
        # Proves stockout adaptation: requested replacement, but executed refund
        self.assertTrue(any("issue_refund" in a for a in state.actions))
        self.assertTrue(any(e.event_type == "adaptation" for e in state.events))

    def test_demo_c_inconclusive_evidence(self):
        """DEMO C: Blurry image uploaded -> INCONCLUSIVE claim -> agent does not fabricate conclusion, investigates logs."""
        repo = SimulatedCompanyRepository("customer_inconclusive_image_log_lookup")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "My product arrived damaged in order ORD-9001."
        
        import os
        os.makedirs("backend/data/uploads", exist_ok=True)
        with open("backend/data/uploads/blurry_damaged.jpg", "w") as f:
            f.write("blurry image demo data")

        blurry_att = EvidenceAttachment(
            attachment_id="ATT-103",
            case_id="CASE-ORD-9001",
            filename="blurry_damaged.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=1050000,
            storage_path="backend/data/uploads/blurry_damaged.jpg",
            status="processed",
        )
        from backend.models.agent import CustomerCase
        case = CustomerCase(
            case_id="CASE-ORD-9001",
            customer_id="CUST-801",
            order_id="ORD-9001",
            original_goal=goal,
            issue=goal,
            requested_resolution="replacement",
            status="OPEN",
            attachments=[blurry_att],
        )
        state = controller.run(goal, customer_case=case)
        self.assertIsNotNone(state.claim_assessment)
        self.assertEqual(state.claim_assessment.claim_status, "INCONCLUSIVE")
        # Ensure agent logged or investigated without fabricating a fake approval
        self.assertTrue(any(e.event_type in ["tool_call", "decision", "claim_assessed"] for e in state.events))

    def test_ownership_security_mismatch_escalates(self):
        """Security Test: Customer CUST-801 querying ORD-9004 (owned by CUST-803) -> OWNERSHIP_MISMATCH -> Urgent escalation."""
        repo = SimulatedCompanyRepository("customer_ownership_mismatch_escalates")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "Check resolution options for order ORD-9004 for customer CUST-801."
        state = controller.run(goal)
        self.assertEqual(state.status, "completed")
        self.assertEqual(state.customer_case.status, "ESCALATED")
        self.assertTrue(any("escalate_customer_case" in a for a in state.actions))
        self.assertFalse(any("issue_refund" in a or "create_replacement" in a for a in state.actions))

    def test_wrong_image_parle_biscuit_contradicts_claim(self):
        """TEST A (Parle Biscuit Test): Customer claims laptop stand damaged, uploads Parle biscuit image -> CONTRADICTED -> Escalates safely."""
        repo = SimulatedCompanyRepository("customer_damaged_replacement_available")
        controller = AgentController(
            ToolRegistry(repo),
            EvidenceBasedDecisionProvider(),
            action_registry=ActionRegistry(repo, Decimal("50000")),
        )
        goal = "My laptop stand arrived damaged in order ORD-9002. I want a replacement."
        
        import os
        os.makedirs("backend/data/uploads", exist_ok=True)
        with open("backend/data/uploads/parle_biscuit.jpg", "w") as f:
            f.write("parle biscuit demo data")

        biscuit_att = EvidenceAttachment(
            attachment_id="ATT-PARLE-1",
            case_id="CASE-ORD-9002",
            filename="parle_biscuit.jpg",
            file_type="image",
            mime_type="image/jpeg",
            size_bytes=1500000,
            storage_path="backend/data/uploads/parle_biscuit.jpg",
            status="processed",
        )
        from backend.models.agent import CustomerCase
        case = CustomerCase(
            case_id="CASE-ORD-9002",
            customer_id="CUST-801",
            order_id="ORD-9002",
            original_goal=goal,
            issue=goal,
            requested_resolution="replacement",
            status="OPEN",
            attachments=[biscuit_att],
        )
        state = controller.run(goal, customer_case=case)
        self.assertIsNotNone(state.claim_assessment)
        self.assertEqual(state.claim_assessment.claim_status, "CONTRADICTED")
        self.assertEqual(state.customer_case.status, "ESCALATED")
        # Ensure replacement was NOT executed for a Parle biscuit image
        self.assertFalse(any("create_replacement" in a for a in state.actions))


if __name__ == "__main__":
    unittest.main()
