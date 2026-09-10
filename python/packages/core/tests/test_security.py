# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for prompt injection defense system."""

import asyncio
import json
import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from agent_framework import (
    Agent,
    AgentSession,
    ChatResponse,
    ExperimentalFeature,
    FunctionInvocationContext,
    FunctionMiddleware,
    Message,
    SessionContext,
)
from agent_framework._middleware import FunctionMiddlewarePipeline, MiddlewareTermination
from agent_framework._tools import (
    FunctionTool,
    _auto_invoke_function,
    _resolve_approval_responses,
    _store_pending_approval_requests,
    normalize_function_invocation_configuration,
)
from agent_framework._types import Content
from agent_framework.security import (
    ConfidentialityLabel,
    ContentLabel,
    ContentVariableStore,
    InspectVariableInput,
    IntegrityLabel,
    LabeledMessage,
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
    SecureAgentConfig,
    VariableReferenceContent,
    combine_labels,
    get_current_middleware,
    store_untrusted_content,
)


class TestContentLabel:
    """Tests for ContentLabel class."""

    def test_create_label_defaults(self):
        """Test creating a label with default values."""
        label = ContentLabel()
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PUBLIC
        assert label.is_trusted()
        assert label.is_public()

    def test_create_label_custom(self):
        """Test creating a label with custom values."""
        label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE,
            metadata={"user_id": "123"},
        )
        assert label.integrity == IntegrityLabel.UNTRUSTED
        assert label.confidentiality == ConfidentialityLabel.PRIVATE
        assert not label.is_trusted()
        assert not label.is_public()
        assert label.metadata["user_id"] == "123"

    def test_label_serialization(self):
        """Test label serialization to dict."""
        label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.USER_IDENTITY,
            metadata={"source": "external"},
        )

        data = label.to_dict()
        assert data["integrity"] == "untrusted"
        assert data["confidentiality"] == "user_identity"
        assert data["metadata"]["source"] == "external"

    def test_label_deserialization(self):
        """Test label deserialization from dict."""
        data = {"integrity": "trusted", "confidentiality": "private", "metadata": {"key": "value"}}

        label = ContentLabel.from_dict(data)
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PRIVATE
        assert label.metadata["key"] == "value"


class TestSecurityFeatureStage:
    """Tests for security feature-stage annotations."""

    def test_security_classes_are_marked_experimental(self):
        """All security classes share the FIDES experimental feature ID."""
        security_classes = [
            IntegrityLabel,
            ConfidentialityLabel,
            ContentLabel,
            ContentVariableStore,
            VariableReferenceContent,
            LabeledMessage,
            LabelTrackingFunctionMiddleware,
            PolicyEnforcementFunctionMiddleware,
            SecureAgentConfig,
            InspectVariableInput,
        ]

        for security_class in security_classes:
            assert security_class.__feature_stage__ == "experimental"  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            assert security_class.__feature_id__ == ExperimentalFeature.FIDES.value  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]


class TestCombineLabels:
    """Tests for label combination logic."""

    def test_combine_empty(self):
        """Test combining no labels returns default."""
        label = combine_labels()
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PUBLIC

    def test_combine_single(self):
        """Test combining single label."""
        input_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)

        result = combine_labels(input_label)
        assert result.integrity == IntegrityLabel.UNTRUSTED
        assert result.confidentiality == ConfidentialityLabel.PRIVATE

    def test_combine_most_restrictive_integrity(self):
        """Test that UNTRUSTED is selected if any label is UNTRUSTED."""
        label1 = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        label2 = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        label3 = ContentLabel(integrity=IntegrityLabel.TRUSTED)

        result = combine_labels(label1, label2, label3)
        assert result.integrity == IntegrityLabel.UNTRUSTED

    def test_combine_most_restrictive_confidentiality(self):
        """Test most restrictive confidentiality is selected."""
        label1 = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        label2 = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        label3 = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)

        result = combine_labels(label1, label2, label3)
        assert result.confidentiality == ConfidentialityLabel.USER_IDENTITY

    def test_combine_metadata_merged(self):
        """Test that metadata is merged from all labels."""
        label1 = ContentLabel(metadata={"key1": "value1"})
        label2 = ContentLabel(metadata={"key2": "value2"})

        result = combine_labels(label1, label2)
        assert result.metadata["key1"] == "value1"
        assert result.metadata["key2"] == "value2"


class TestContentVariableStore:
    """Tests for ContentVariableStore."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving content."""
        store = ContentVariableStore()
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)

        var_id = store.store("test content", label)
        assert var_id.startswith("var_")

        content, retrieved_label = store.retrieve(var_id)
        assert content == "test content"
        assert retrieved_label.integrity == IntegrityLabel.UNTRUSTED

    def test_exists(self):
        """Test checking if variable exists."""
        store = ContentVariableStore()
        label = ContentLabel()

        var_id = store.store("test", label)
        assert store.exists(var_id)
        assert not store.exists("nonexistent")

    def test_retrieve_nonexistent_raises(self):
        """Test retrieving nonexistent variable raises KeyError."""
        store = ContentVariableStore()

        with pytest.raises(KeyError):
            store.retrieve("nonexistent")

    def test_list_variables(self):
        """Test listing all variable IDs."""
        store = ContentVariableStore()
        label = ContentLabel()

        var_id1 = store.store("content1", label)
        var_id2 = store.store("content2", label)

        variables = store.list_variables()
        assert var_id1 in variables
        assert var_id2 in variables
        assert len(variables) == 2

    def test_clear(self):
        """Test clearing all variables."""
        store = ContentVariableStore()
        label = ContentLabel()

        store.store("content1", label)
        store.store("content2", label)

        store.clear()
        assert len(store.list_variables()) == 0


class TestVariableReferenceContent:
    """Tests for VariableReferenceContent."""

    def test_create_reference(self):
        """Test creating a variable reference."""
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        ref = VariableReferenceContent(variable_id="var_abc123", label=label, description="Test content")

        assert ref.variable_id == "var_abc123"
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.description == "Test content"
        assert ref.type == "variable_reference"

    def test_reference_serialization(self):
        """Test serializing variable reference."""
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        ref = VariableReferenceContent(variable_id="var_abc123", label=label, description="Test")

        data = ref.to_dict()
        assert data["type"] == "variable_reference"
        assert data["variable_id"] == "var_abc123"
        assert data["security_label"]["integrity"] == "untrusted"
        assert data["description"] == "Test"

    def test_reference_deserialization(self):
        """Test deserializing variable reference."""
        data = {
            "type": "variable_reference",
            "variable_id": "var_abc123",
            "security_label": {"integrity": "untrusted", "confidentiality": "public"},
            "description": "Test",
        }

        ref = VariableReferenceContent.from_dict(data)
        assert ref.variable_id == "var_abc123"
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.description == "Test"

    def test_reference_deserialization_legacy_label_key(self):
        """Test deserializing variable reference with legacy 'label' key for backward compatibility."""
        data = {
            "type": "variable_reference",
            "variable_id": "var_abc123",
            "label": {"integrity": "untrusted", "confidentiality": "public"},
            "description": "Test",
        }

        ref = VariableReferenceContent.from_dict(data)
        assert ref.variable_id == "var_abc123"
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.description == "Test"


class TestStoreUntrustedContent:
    """Tests for store_untrusted_content helper."""

    def test_store_with_label(self):
        """Test storing content with explicit label."""
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)

        ref = store_untrusted_content("test content", label=label, description="Test")

        assert ref.variable_id.startswith("var_")
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.label.confidentiality == ConfidentialityLabel.PRIVATE
        assert ref.description == "Test"

    def test_store_default_label(self):
        """Test storing content with default label."""
        ref = store_untrusted_content("test content")

        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.label.confidentiality == ConfidentialityLabel.PUBLIC


class TestLabelTrackingMiddleware:
    """Tests for LabelTrackingFunctionMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return LabelTrackingFunctionMiddleware()

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""

        class MockArgs(BaseModel):
            arg: str

        async def mock_fn(arg: str) -> str:
            return f"result: {arg}"

        return FunctionTool(fn=mock_fn, name="mock_function", description="Mock function", args_schema=MockArgs)

    @pytest.mark.asyncio
    async def test_label_attached_to_context(self, middleware, mock_function):
        """Test that label is attached to context metadata."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("mock result")]

        await middleware.process(context, next_fn)

        assert "result_label" in context.metadata
        label = context.metadata["result_label"]
        assert isinstance(label, ContentLabel)

    @pytest.mark.asyncio
    async def test_tool_with_trusted_source_labeled_trusted(self, middleware, mock_function):
        """Test that tools with source_integrity=trusted and no untrusted inputs are labeled TRUSTED."""

        # Create a function with source_integrity=trusted
        class TrustedArgs(BaseModel):
            arg: str

        async def trusted_fn(arg: str) -> str:
            return f"result: {arg}"

        trusted_function = FunctionTool(
            fn=trusted_fn,
            name="trusted_function",
            description="Trusted function",
            args_schema=TrustedArgs,
            additional_properties={"source_integrity": "trusted"},
        )

        args = trusted_function.args_schema(arg="test")  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=trusted_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("mock result")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        assert label.integrity == IntegrityLabel.TRUSTED

    @pytest.mark.asyncio
    async def test_tool_without_source_integrity_defaults_untrusted(self, middleware, mock_function):
        """Test that tools without source_integrity declaration default to UNTRUSTED."""
        # mock_function has no additional_properties, so no source_integrity
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("mock result")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # Should default to UNTRUSTED (safe default)
        assert label.integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_input_labels_propagate_to_output(self, middleware):
        """Test that source_integrity overrides input labels (tier 2 > tier 3).

        When a tool declares source_integrity="trusted", that declaration is
        authoritative for the trust level of its output, regardless of the
        input argument labels.
        """

        # Create a trusted function
        class TrustedArgs(BaseModel):
            data: dict

        async def process_fn(data: dict) -> str:
            return "processed"

        trusted_function = FunctionTool(
            fn=process_fn,
            name="process_data",
            description="Process data",
            args_schema=TrustedArgs,
            additional_properties={"source_integrity": "trusted"},
        )

        # Create argument that contains untrusted label
        args = trusted_function.args_schema(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            data={"content": "test", "security_label": {"integrity": "untrusted", "confidentiality": "public"}}
        )

        context = FunctionInvocationContext(function=trusted_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("processed result")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # source_integrity="trusted" (tier 2) overrides untrusted input label (tier 3)
        assert label.integrity == IntegrityLabel.TRUSTED

    @pytest.mark.asyncio
    async def test_variable_reference_input_labels_extracted(self, middleware):
        """Test that labels from VariableReferenceContent inputs are extracted."""

        # Create a function that takes a variable reference
        class VarRefArgs(BaseModel):
            var_ref: dict

        async def process_fn(var_ref: dict) -> str:
            return "processed"

        trusted_function = FunctionTool(
            fn=process_fn,
            name="process_var",
            description="Process variable",
            args_schema=VarRefArgs,
            additional_properties={"source_integrity": "trusted"},
        )

        # Create a VariableReferenceContent with UNTRUSTED label
        untrusted_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_ref = VariableReferenceContent(
            variable_id="var_test123", label=untrusted_label, description="Test variable"
        )

        # Pass the VariableReferenceContent as an argument
        context = FunctionInvocationContext(
            function=trusted_function,
            arguments=trusted_function.args_schema(var_ref={"test": "value"}),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # Regular dict
        )
        # But also pass the actual VariableReferenceContent in kwargs
        context.kwargs = {"var_ref_obj": var_ref}

        async def next_fn():
            context.result = [Content.from_text("processed")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # source_integrity="trusted" (tier 2) overrides the VariableReferenceContent
        # label from input (tier 3) — the tool's declaration is authoritative
        assert label.integrity == IntegrityLabel.TRUSTED

    @pytest.mark.asyncio
    async def test_bracketed_variable_reference_expanded_before_call_next(self, middleware):
        """Bracketed variable placeholders should be expanded before tool execution."""

        class MessageArgs(BaseModel):
            summary: str

        async def send_message(summary: str) -> str:
            return summary

        message_tool = FunctionTool(
            fn=send_message,
            name="SendMessagetoSelf",
            description="Send message",
            args_schema=MessageArgs,
        )

        expected_summary = "Expanded quarantined summary"
        variable_id = middleware.get_variable_store().store(
            expected_summary,
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        context = FunctionInvocationContext(
            function=message_tool,
            arguments=MessageArgs(summary=f"[{variable_id}]"),
        )

        async def next_fn() -> None:
            current_args = context.arguments
            if isinstance(current_args, BaseModel):
                summary = current_args.model_dump()["summary"]
            else:
                summary = current_args["summary"]
            assert summary == expected_summary
            context.result = [Content.from_text("sent")]

        await middleware.process(context, next_fn)

    @pytest.mark.asyncio
    async def test_json_string_variable_reference_expands_only_response_before_call_next(self, middleware):
        """JSON-serialized hidden payloads should expose only the response text to tools."""

        class MessageArgs(BaseModel):
            summary: str

        async def send_message(summary: str) -> str:
            return summary

        message_tool = FunctionTool(
            fn=send_message,
            name="SendMessagetoSelf",
            description="Send message",
            args_schema=MessageArgs,
        )

        response_text = "Expanded quarantined summary"
        stored_payload = json.dumps({
            "response": response_text,
            "security_label": {"integrity": "untrusted", "confidentiality": "public"},
            "metadata": {},
            "quarantined": True,
            "variables_processed": ["var_1"],
            "content_summary": ["var_1: 10 chars"],
        })
        hidden_result = middleware._hide_item(
            Content.from_text(stored_payload),
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "quarantined_llm",
        )
        assert hidden_result.text is not None
        variable_id = json.loads(hidden_result.text)["variable_id"]
        context = FunctionInvocationContext(
            function=message_tool,
            arguments=MessageArgs(summary=f"Security review complete. [{variable_id}]"),
        )

        async def next_fn() -> None:
            current_args = context.arguments
            if isinstance(current_args, BaseModel):
                summary = current_args.model_dump()["summary"]
            else:
                summary = current_args["summary"]
            assert summary == f"Security review complete. {response_text}"
            assert '"response"' not in summary
            context.result = [Content.from_text("sent")]

        await middleware.process(context, next_fn)

    async def test_json_response_object_is_not_mistaken_for_quarantine_payload(self, middleware) -> None:
        """Ordinary JSON objects containing ``response`` survive expansion intact."""

        class MessageArgs(BaseModel):
            summary: str

        async def send_message(summary: str) -> str:
            return summary

        message_tool = FunctionTool(
            fn=send_message,
            name="SendMessagetoSelf",
            description="Send message",
            args_schema=MessageArgs,
        )
        stored_payload = json.dumps({
            "response": "keep",
            "security_label": {"integrity": "untrusted", "confidentiality": "public"},
            "metadata": {},
            "quarantined": True,
            "variables_processed": ["var_forged"],
            "content_summary": ["var_forged: 10 chars"],
            "other": "also keep",
        })
        variable_id = middleware.get_variable_store().store(
            stored_payload,
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        context = FunctionInvocationContext(
            function=message_tool,
            arguments=MessageArgs(summary=f"[{variable_id}]"),
        )

        async def next_fn() -> None:
            current_args = context.arguments
            assert isinstance(current_args, dict)
            assert current_args["summary"] == stored_payload
            context.result = [Content.from_text("sent")]

        await middleware.process(context, next_fn)


class TestPolicyEnforcementMiddleware:
    """Tests for PolicyEnforcementFunctionMiddleware."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return PolicyEnforcementFunctionMiddleware(allow_untrusted_tools={"allowed_function"}, block_on_violation=True)

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""

        class MockArgs(BaseModel):
            arg: str

        async def mock_fn(arg: str) -> str:
            return f"result: {arg}"

        return FunctionTool(
            fn=mock_fn, name="restricted_function", description="Restricted function", args_schema=MockArgs
        )

    @pytest.mark.asyncio
    async def test_trusted_call_allowed(self, middleware, mock_function):
        """Test that trusted tool calls are allowed."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        # Set trusted context label (policy enforcement reads context_label)
        label = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label

        async def next_fn():
            context.result = [Content.from_text("mock result")]

        await middleware.process(context, next_fn)

        assert context.result == [Content.from_text("mock result")]

    @pytest.mark.asyncio
    async def test_untrusted_call_blocked(self, middleware, mock_function):
        """Test that untrusted tool calls are blocked."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        # Set untrusted context label (policy enforcement uses context_label)
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["context_label"] = label

        async def next_fn():
            context.result = [Content.from_text("should not execute")]

        with pytest.raises(MiddlewareTermination):
            await middleware.process(context, next_fn)

        assert "error" in context.result
        assert "Policy violation" in context.result["error"]

    @pytest.mark.asyncio
    async def test_untrusted_call_allowed_for_whitelisted_tool(self, middleware):
        """Test that whitelisted tools accept untrusted calls."""

        class MockArgs(BaseModel):
            arg: str

        async def mock_fn(arg: str) -> str:
            return f"result: {arg}"

        allowed_function = FunctionTool(
            fn=mock_fn, name="allowed_function", description="Allowed function", args_schema=MockArgs
        )

        args = allowed_function.args_schema(arg="test")  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=allowed_function, arguments=args)

        # Set untrusted context label (policy enforcement uses context_label)
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["context_label"] = label

        async def next_fn():
            context.result = [Content.from_text("allowed result")]

        await middleware.process(context, next_fn)

        assert context.result == [Content.from_text("allowed result")]

    def test_audit_log_recording(self, middleware, mock_function):
        """Test that violations are recorded in audit log."""
        initial_count = len(middleware.get_audit_log())
        assert initial_count == 0

    async def test_untrusted_call_requests_policy_approval(self, mock_function):
        """Test that policy violations can become approval requests."""
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["call_id"] = "call-untrusted"

        async def next_fn() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(context, next_fn)

        assert isinstance(context.result, Content)
        assert context.result.type == "function_approval_request"
        assert context.result.additional_properties["policy_violation"] is True
        assert context.result.additional_properties["violation_type"] == "untrusted_context"
        assert context.result.function_call.call_id == "call-untrusted"  # type: ignore[union-attr]

    async def test_confidentiality_violation_requests_policy_approval(self, mock_function):
        """Test confidentiality violations reuse the policy approval path."""
        mock_function.additional_properties = {"max_allowed_confidentiality": "public"}
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        context.metadata["context_label"] = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        context.metadata["call_id"] = "call-confidentiality"

        async def next_fn() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(context, next_fn)

        assert isinstance(context.result, Content)
        assert context.result.type == "function_approval_request"
        assert context.result.additional_properties["policy_violation"] is True
        assert context.result.additional_properties["violation_type"] == "max_allowed_confidentiality"
        assert "PRIVATE" in context.result.additional_properties["reason"]

    async def test_policy_approved_replay_executes_tool(self, mock_function):
        """Test that an approved policy violation replays through middleware."""
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "call-approved"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)
        assert approval_request.type == "function_approval_request"

        context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["call_id"] = "call-approved"
        context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        async def next_fn() -> None:
            context.result = [Content.from_text("approved result")]

        await middleware.process(context, next_fn)

        assert context.metadata["user_approved_violation"] is True
        assert context.result == [Content.from_text("approved result")]
        assert "call-approved" not in middleware._pending_policy_approvals

    @pytest.mark.parametrize("invalid_max", [float("nan"), 1.0, True, False, 0, "1"])
    def test_max_pending_approvals_requires_positive_int(self, invalid_max: Any) -> None:
        """Capacity must reject values that could disable the bound."""
        with pytest.raises(ValueError, match="max_pending_approvals must be a positive integer"):
            PolicyEnforcementFunctionMiddleware(max_pending_approvals=invalid_max)  # type: ignore[arg-type]

    def test_max_pending_approvals_accepts_positive_int(self) -> None:
        middleware = PolicyEnforcementFunctionMiddleware(max_pending_approvals=1)
        assert middleware._max_pending_approvals == 1

    async def test_pending_policy_approvals_are_fifo_bounded_by_occurrence(self, mock_function) -> None:
        """The oldest occurrence is evicted and its stale grant fails closed."""
        middleware = PolicyEnforcementFunctionMiddleware(
            approval_on_violation=True,
            max_pending_approvals=2,
            pending_approval_ttl=None,
        )
        session = AgentSession(session_id="fifo-policy-approvals")

        async def request(occurrence_id: str) -> Content:
            context = FunctionInvocationContext(
                function=mock_function,
                arguments=mock_function.args_schema(arg="test"),
                session=session,
                kwargs={"session": session},
            )
            context.metadata.update({
                "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
                "call_id": "reused-provider-call",
                "function_call_occurrence_id": occurrence_id,
            })

            async def should_not_execute() -> None:
                pytest.fail("Policy-violating tools require approval")

            with pytest.raises(MiddlewareTermination):
                await middleware.process(context, should_not_execute)
            assert isinstance(context.result, Content)
            return context.result

        requests = [await request(f"occurrence-{index}") for index in range(3)]
        pending = middleware._scope_for_session(session).pending_approvals
        assert list(pending) == ["occurrence-1", "occurrence-2"]

        stale_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=session,
            kwargs={"session": session},
        )
        stale_context.metadata.update({
            "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "call_id": "reused-provider-call",
            "function_call_occurrence_id": "occurrence-0",
            "approval_response": requests[0].to_function_approval_response(True),
        })

        async def should_not_execute_stale_grant() -> None:
            pytest.fail("An evicted approval must not execute")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(stale_context, should_not_execute_stale_grant)

        assert isinstance(stale_context.result, Content)
        assert stale_context.result.type == "function_approval_request"
        assert stale_context.result.id != "occurrence-0"
        assert stale_context.result.function_call is not None
        assert stale_context.result.function_call.id == "occurrence-0"
        assert list(pending) == ["occurrence-2", "occurrence-0"]

    async def test_pending_policy_approval_ttl_is_deterministic_and_durable(
        self,
        mock_function,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A restored approval expires at the configured boundary and is replaced."""
        now = 1_000.0
        monkeypatch.setattr("agent_framework.security.time.time", lambda: now)
        middleware = PolicyEnforcementFunctionMiddleware(
            approval_on_violation=True,
            pending_approval_ttl=timedelta(seconds=5),
        )
        session = AgentSession(session_id="ttl-policy-approval")
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=session,
            kwargs={"session": session},
        )
        request_context.metadata.update({
            "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "call_id": "ttl-provider-call",
            "function_call_occurrence_id": "ttl-occurrence",
        })

        async def should_not_execute() -> None:
            pytest.fail("Policy-violating tools require approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, should_not_execute)
        assert isinstance(request_context.result, Content)
        approval_request = request_context.result

        restored = AgentSession.from_dict(session.to_dict())
        now = 1_005.0
        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=restored,
            kwargs={"session": restored},
        )
        replay_context.metadata.update({
            "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "call_id": "ttl-provider-call",
            "function_call_occurrence_id": "ttl-occurrence",
            "approval_response": approval_request.to_function_approval_response(True),
        })

        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, should_not_execute)

        assert isinstance(replay_context.result, Content)
        assert replay_context.result.type == "function_approval_request"
        assert replay_context.result.id != "ttl-occurrence"
        assert replay_context.result.function_call is not None
        assert replay_context.result.function_call.id == "ttl-occurrence"
        replacement = replay_context.result
        pending = middleware._scope_for_session(restored).pending_approvals["ttl-occurrence"]
        assert pending["created_at"] == now
        assert pending["request_id"] == replacement.id

        restored_again = AgentSession.from_dict(json.loads(json.dumps(restored.to_dict())))
        stale_generation_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=restored_again,
            kwargs={"session": restored_again},
        )
        stale_generation_context.metadata.update({
            "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "call_id": "ttl-provider-call",
            "function_call_occurrence_id": "ttl-occurrence",
            "approval_response": approval_request.to_function_approval_response(True),
        })
        executions = 0

        async def execute_once() -> None:
            nonlocal executions
            executions += 1

        with pytest.raises(MiddlewareTermination):
            await middleware.process(stale_generation_context, execute_once)

        assert executions == 0
        assert isinstance(stale_generation_context.result, Content)
        latest_replacement = stale_generation_context.result
        assert latest_replacement.id not in {approval_request.id, replacement.id}

        final_restore = AgentSession.from_dict(json.loads(json.dumps(restored_again.to_dict())))
        approved_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=final_restore,
            kwargs={"session": final_restore},
        )
        approved_context.metadata.update({
            "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            "call_id": "ttl-provider-call",
            "function_call_occurrence_id": "ttl-occurrence",
            "approval_response": latest_replacement.to_function_approval_response(True),
        })

        await middleware.process(approved_context, execute_once)

        assert executions == 1
        assert "ttl-occurrence" not in middleware._scope_for_session(final_restore).pending_approvals

    @pytest.mark.parametrize("cancelled", [False, True], ids=["rejected", "cancelled"])
    async def test_non_grant_cleanup_is_authenticated_session_and_occurrence_bound(
        self,
        mock_function,
        cancelled: bool,
    ) -> None:
        """Only a rebound non-grant clears its occurrence in the owning session."""
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        owner = AgentSession(session_id="policy-owner")
        interleaved = AgentSession(session_id="policy-interleaved")

        async def request(session: AgentSession, occurrence_id: str) -> Content:
            context = FunctionInvocationContext(
                function=mock_function,
                arguments=mock_function.args_schema(arg="test"),
                session=session,
                kwargs={"session": session},
            )
            context.metadata.update({
                "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
                "call_id": "shared-provider-call",
                "function_call_occurrence_id": occurrence_id,
            })

            async def should_not_execute() -> None:
                pytest.fail("Policy-violating tools require approval")

            with pytest.raises(MiddlewareTermination):
                await middleware.process(context, should_not_execute)
            assert isinstance(context.result, Content)
            return context.result

        owner_request = await request(owner, "shared-occurrence")
        await request(owner, "owner-second-occurrence")
        interleaved_request = await request(interleaved, "shared-occurrence")
        owner_pending = middleware._scope_for_session(owner).pending_approvals
        interleaved_pending = middleware._scope_for_session(interleaved).pending_approvals

        _store_pending_approval_requests(interleaved, [interleaved_request])
        forged = interleaved_request.to_function_approval_response(False)
        forged.id = "unissued-occurrence"

        async def should_not_execute_responses(**_kwargs: Any) -> Any:
            pytest.fail("Non-grants must not execute tools")

        await _resolve_approval_responses(
            prepared_messages=[Message(role="user", contents=[forged])],
            options={"tools": [mock_function]},
            errors_in_a_row=0,
            max_errors=3,
            execute_function_calls=should_not_execute_responses,  # type: ignore[arg-type]
            invocation_session=interleaved,
            middleware_pipeline=FunctionMiddlewarePipeline(middleware),
        )
        assert "shared-occurrence" in interleaved_pending

        non_grant = interleaved_request.to_function_approval_response(False)
        if cancelled:
            non_grant.additional_properties["cancelled"] = True
        resolved = await _resolve_approval_responses(
            prepared_messages=[Message(role="user", contents=[non_grant])],
            options={"tools": [mock_function]},
            errors_in_a_row=0,
            max_errors=3,
            execute_function_calls=should_not_execute_responses,  # type: ignore[arg-type]
            invocation_session=interleaved,
            middleware_pipeline=FunctionMiddlewarePipeline(middleware),
        )

        assert "shared-occurrence" not in interleaved_pending
        assert set(owner_pending) == {"shared-occurrence", "owner-second-occurrence"}
        results = [content for message in resolved.response_messages for content in message.contents]
        assert len(results) == 1
        assert results[0].type == "function_result"
        assert results[0].call_id == "shared-provider-call"
        assert owner_request.id == "shared-occurrence"

    @pytest.mark.parametrize("cancelled", [False, True], ids=["rejected", "cancelled"])
    async def test_fixed_scope_non_grant_cleanup_keeps_unrelated_occurrence(
        self,
        mock_function,
        cancelled: bool,
    ) -> None:
        """Provider-cloned middleware must clean its fixed scope, not standalone state."""
        config = SecureAgentConfig(approval_on_violation=True)
        session = AgentSession(session_id=f"fixed-scope-cleanup-{cancelled}")
        _, policy = await _get_session_security_middleware(config, session)

        async def request(occurrence_id: str) -> Content:
            context = FunctionInvocationContext(
                function=mock_function,
                arguments=mock_function.args_schema(arg="test"),
                session=session,
                kwargs={"session": session},
            )
            context.metadata.update({
                "context_label": ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
                "call_id": f"call-{occurrence_id}",
                "function_call_occurrence_id": occurrence_id,
            })

            async def should_not_execute() -> None:
                pytest.fail("Policy-violating tools require approval")

            with pytest.raises(MiddlewareTermination):
                await policy.process(context, should_not_execute)
            assert isinstance(context.result, Content)
            return context.result

        target = await request("target-occurrence")
        await request("unrelated-occurrence")
        response = target.to_function_approval_response(False)
        if cancelled:
            response.additional_properties["cancelled"] = True

        FunctionMiddlewarePipeline(policy)._notify_approval_responses([response], session=session)

        pending = config._scope_for_session(session).pending_approvals
        assert set(pending) == {"unrelated-occurrence"}
        assert "pending_policy_approvals" not in session.state.get("__agent_framework_fides_security__", {})

    def test_callable_middleware_cannot_observe_approval_lifecycle(self) -> None:
        """Only class middleware implementing the private capability receives notifications."""
        observed = False

        class CallableMiddleware:
            async def __call__(self, _context: Any, call_next: Any) -> None:
                await call_next()

            def _on_approval_responses(self, _responses: Any, *, session: Any) -> None:
                nonlocal observed
                observed = True

        FunctionMiddlewarePipeline(CallableMiddleware())._notify_approval_responses(
            [],
            session=AgentSession(session_id="callable-observer"),
        )

        assert observed is False
        assert not hasattr(FunctionMiddleware, "on_approval_responses")

    async def test_auto_invoke_passes_approval_response_to_middleware(self, mock_function):
        """Test the main tool loop passes approval response content via metadata."""
        captured_metadata: dict[str, object] = {}

        class CaptureApprovalResponseMiddleware(FunctionMiddleware):
            async def process(self, context: FunctionInvocationContext, call_next) -> None:
                captured_metadata["approval_response"] = context.metadata.get("approval_response")
                captured_metadata["policy_approval_granted"] = context.metadata.get("policy_approval_granted")
                await call_next()

        function_call = Content.from_function_call(
            call_id="call-approved",
            name=mock_function.name,
            arguments='{"arg": "test"}',
        )
        approval_response = Content.from_function_approval_response(
            approved=True,
            id="call-approved",
            function_call=function_call,
        )

        result = await _auto_invoke_function(
            approval_response,
            config=normalize_function_invocation_configuration(None),
            tool_map={mock_function.name: mock_function},
            middleware_pipeline=FunctionMiddlewarePipeline(CaptureApprovalResponseMiddleware()),
        )

        assert result.type == "function_result"
        assert captured_metadata["approval_response"] is approval_response
        assert captured_metadata["policy_approval_granted"] is None

    async def test_policy_violation_approval_preserves_type_through_auto_invoke(self, mock_function):
        """Test that _auto_invoke_function preserves function_approval_request type on MiddlewareTermination.

        When PolicyEnforcementFunctionMiddleware raises MiddlewareTermination with a
        function_approval_request result, the exception handler must pass it through
        directly rather than wrapping it in a function_result.
        """
        label_tracker = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
        # Taint the context label so the policy enforcer sees UNTRUSTED
        label_tracker._context_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        label_tracker._initialized = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        policy = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        pipeline = FunctionMiddlewarePipeline(label_tracker, policy)

        function_call = Content.from_function_call(
            call_id="call-policy-violation",
            name=mock_function.name,
            arguments='{"arg": "test"}',
            id="af-call-policy-violation",
        )

        with pytest.raises(MiddlewareTermination) as exc_info:
            await _auto_invoke_function(
                function_call,
                config=normalize_function_invocation_configuration(None),
                tool_map={mock_function.name: mock_function},
                middleware_pipeline=pipeline,
            )

        # The exception's result must be a function_approval_request, NOT a function_result
        result = exc_info.value.result
        assert isinstance(result, Content)
        assert result.type == "function_approval_request", (
            f"Expected function_approval_request but got {result.type}; "
            "MiddlewareTermination handler must not wrap approval requests in function_result"
        )
        assert result.function_call is not None
        assert result.id == "af-call-policy-violation"
        assert result.function_call.call_id == "call-policy-violation"
        assert result.function_call.id == "af-call-policy-violation"
        assert result.additional_properties["policy_violation"] is True
        assert result.additional_properties["violation_type"] == "untrusted_context"

    async def _approve_once(
        self,
        middleware: PolicyEnforcementFunctionMiddleware,
        function: FunctionTool,
        call_id: str,
    ) -> None:
        """Drive one approval request -> approved replay so the tool executes once."""
        request_context = FunctionInvocationContext(
            function=function,
            arguments=function.args_schema(arg="test"),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = call_id

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)
        assert approval_request.type == "function_approval_request"

        replay_context = FunctionInvocationContext(
            function=function,
            arguments=function.args_schema(arg="test"),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        )
        replay_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        replay_context.metadata["call_id"] = call_id
        replay_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        await middleware.process(replay_context, execute)
        assert executed is True

    async def test_approved_call_id_cannot_be_replayed_for_repeated_call(self, mock_function):
        """A granted approval is consumed once; reusing the same call_id must re-request approval.

        Binds each approval to a single, non-reusable invocation: once a policy violation for a
        call_id has been approved and executed, a later invocation reusing that same call_id (with
        no fresh approval) must not be auto-authorized.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: complete one legitimate approve -> execute cycle for this call_id.
        await self._approve_once(middleware, mock_function, "call-replay")

        # Act: a second invocation reuses the same call_id but presents NO fresh approval.
        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        replay_context.metadata["call_id"] = "call-replay"

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the reused call_id is not auto-authorized; approval is requested again.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)
        assert executed is False
        assert isinstance(replay_context.result, Content)
        assert replay_context.result.type == "function_approval_request"

    async def test_approved_call_id_cannot_authorize_different_function(self, mock_function):
        """A replayed approval bound to one call must not authorize a different function.

        The approval is bound to the specific invocation (function + arguments), so a replayed
        approval response that reuses the approved call_id cannot re-authorize a different tool.
        """

        class MockArgs(BaseModel):
            arg: str

        async def other_fn(arg: str) -> str:
            return f"other: {arg}"

        different_function = FunctionTool(
            fn=other_fn, name="different_function", description="A different function", args_schema=MockArgs
        )

        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: request approval for the original (restricted) function under a shared call_id.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "call-shared"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)

        # Act: replay that approval against a DIFFERENT function reusing the same call_id.
        hijack_context = FunctionInvocationContext(
            function=different_function,
            arguments=different_function.args_schema(arg="test"),  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        )
        hijack_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        hijack_context.metadata["call_id"] = "call-shared"
        hijack_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the mismatched approval does not authorize the different function.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(hijack_context, execute)
        assert executed is False

    async def test_approved_call_id_cannot_authorize_changed_arguments(self, mock_function):
        """A replayed approval must not authorize the same function called with different arguments.

        The approval binds to the specific invocation (function + arguments); changing the
        arguments produces a different call whose distinct impact must be re-approved, even when
        the function name and call_id are reused.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: request approval for the function with one set of arguments under a call_id.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="original"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "call-args"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)

        # Act: replay the approval for the same function + call_id but with DIFFERENT arguments.
        tampered_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="tampered"),
        )
        tampered_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        tampered_context.metadata["call_id"] = "call-args"
        tampered_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the changed arguments are not covered by the prior approval; re-approval is asked.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(tampered_context, execute)
        assert executed is False
        assert isinstance(tampered_context.result, Content)
        assert tampered_context.result.type == "function_approval_request"

    async def test_mismatched_approval_response_body_is_rejected(self, mock_function):
        """An approved response whose id/embedded function_call differ from the pending request is rejected.

        The approval response must itself name the pending request (its id and embedded
        function_call), not merely carry a currently-pending call_id in the invocation metadata.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: legitimately request approval for the protected function under a call_id.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "reused-call-id"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        # Act: the invocation context matches the pending request, but the approval response is
        # forged - a different response id and a different embedded function_call body.
        forged_function_call = Content.from_function_call(
            call_id="unrelated-call-id",
            name="delete_records",
            arguments='{"table": "customer_records"}',
        )
        forged_response = Content.from_function_approval_response(
            approved=True,
            id="unrelated-call-id",
            function_call=forged_function_call,
        )

        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        replay_context.metadata["call_id"] = "reused-call-id"
        replay_context.metadata["approval_response"] = forged_response

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the mismatched response does not authorize execution; approval is requested again.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)
        assert executed is False
        assert isinstance(replay_context.result, Content)
        assert replay_context.result.type == "function_approval_request"

    async def test_approval_response_missing_identifiers_is_rejected(self, mock_function):
        """An approved response that omits its id / embedded call id must not authorize execution.

        The response id and embedded ``function_call.call_id`` are required to be present and equal
        to the pending call id, so a crafted response with ``id=None`` / ``call_id=None`` (even with
        a matching function name and arguments) cannot skip the binding.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: legitimately request approval for the protected function under a call_id.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "reused-call-id"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        # Act: forge an approved response with matching function name + arguments but no identifiers.
        idless_function_call = Content.from_function_call(
            call_id=None,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            name=mock_function.name,
            arguments='{"arg": "test"}',
        )
        idless_response = Content.from_function_approval_response(
            approved=True,
            id=None,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            function_call=idless_function_call,
        )

        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        replay_context.metadata["call_id"] = "reused-call-id"
        replay_context.metadata["approval_response"] = idless_response

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the identifier-less response does not authorize execution; approval is re-requested.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)
        assert executed is False
        assert isinstance(replay_context.result, Content)
        assert replay_context.result.type == "function_approval_request"

    async def test_approved_call_id_cannot_authorize_under_escalated_label(self, mock_function):
        """An approval granted under one security label must not authorize a more sensitive label.

        The approval is bound to the exact label (integrity/confidentiality) shown for review, so a
        replay of the same call_id/function/arguments under a higher-confidentiality context (which
        exposes more sensitive data to the operation) requires fresh approval.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: request approval under an UNTRUSTED + PUBLIC label.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PUBLIC
        )
        request_context.metadata["call_id"] = "call-label"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)

        # Act: replay the approval for the same call_id/function/arguments but under a more
        # sensitive (USER_IDENTITY) confidentiality label.
        escalated_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        escalated_context.metadata["context_label"] = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.USER_IDENTITY
        )
        escalated_context.metadata["call_id"] = "call-label"
        escalated_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the label change is not covered by the prior approval; re-approval is requested.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(escalated_context, execute)
        assert executed is False
        assert isinstance(escalated_context.result, Content)
        assert escalated_context.result.type == "function_approval_request"

    async def test_approved_call_id_is_bound_to_session(self, mock_function):
        """An approval granted in one session must not authorize the same call in another session.

        The approval binds to the session it was requested in (the isolation boundary at this
        layer), so a middleware instance shared across sessions cannot let session B consume an
        approval that session A was shown.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: request approval within session A.
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=AgentSession(session_id="session-a"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "call-session"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)

        # Act: replay the same call_id/function/arguments and approval from a different session B.
        other_session_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
            session=AgentSession(session_id="session-b"),
        )
        other_session_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        other_session_context.metadata["call_id"] = "call-session"
        other_session_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the cross-session replay is not authorized; approval is requested again.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(other_session_context, execute)
        assert executed is False
        assert isinstance(other_session_context.result, Content)
        assert other_session_context.result.type == "function_approval_request"

    async def test_same_call_id_and_function_can_be_reapproved(self, mock_function):
        """After consuming one approval, the same function + call_id works again via a fresh approval.

        Consume-once blocks silent replay, but it must not permanently lock out a legitimate later
        call: re-requesting and re-granting approval for the same (call_id, function, arguments)
        lets the tool execute again.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange + Act: first full approve -> execute cycle consumes the approval.
        await self._approve_once(middleware, mock_function, "call-reused")

        # Act: a fresh approval request for the same call_id + function, then an approved replay.
        second_request = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        second_request.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        second_request.metadata["call_id"] = "call-reused"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(second_request, stop_before_execute)

        second_approval = second_request.result
        assert isinstance(second_approval, Content)
        assert second_approval.type == "function_approval_request"

        second_replay = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        second_replay.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        second_replay.metadata["call_id"] = "call-reused"
        second_replay.metadata["approval_response"] = second_approval.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        # Assert: the freshly re-approved call executes.
        await middleware.process(second_replay, execute)
        assert executed is True

    async def test_multiple_violations_disclosed_in_single_approval(self, mock_function):
        """A call with two violations must disclose both before it can be approved.

        Regression: when both an untrusted-context violation and a confidentiality
        (data-exfiltration) violation apply, the approval request must surface both. A single
        approval computed once must not disclose only the integrity violation and then silently
        wave the undisclosed confidentiality violation on replay.
        """
        # max_allowed_confidentiality="public" makes a PRIVATE context a confidentiality violation.
        mock_function.additional_properties = {"max_allowed_confidentiality": "public"}
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: UNTRUSTED + PRIVATE context triggers BOTH integrity and confidentiality checks.
        both_label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE,
        )
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = both_label
        request_context.metadata["call_id"] = "call-both"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        # Act: the single approval request must disclose every detected violation.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)
        assert approval_request.type == "function_approval_request"
        props = approval_request.additional_properties
        disclosed = {entry["violation_type"] for entry in props.get("violations", [])}
        disclosed.add(props["violation_type"])

        # Assert: both the untrusted-context and the confidentiality violation are disclosed.
        assert "untrusted_context" in disclosed
        assert "max_allowed_confidentiality" in disclosed

        # Act: approving the fully disclosed request executes exactly once and consumes it.
        exec_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        exec_context.metadata["context_label"] = both_label
        exec_context.metadata["call_id"] = "call-both"
        exec_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        executed = False

        async def execute() -> None:
            nonlocal executed
            executed = True

        await middleware.process(exec_context, execute)
        assert executed is True
        assert "call-both" not in middleware._pending_policy_approvals

    async def test_replay_with_new_violation_set_requires_fresh_approval(self, mock_function):
        """An approval bound to one disclosed violation set cannot wave a larger set on replay.

        Regression: the violation set depends on the tool's policy metadata
        (``max_allowed_confidentiality`` / ``accepts_untrusted``), which is not part of the call
        body. If that metadata changes between the approval request and the replay so that a new
        violation now applies, the invocation must re-request approval for the new set rather than
        execute under the old grant that never disclosed it.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: at request time the tool has no confidentiality restriction, so the only
        # violation is untrusted_context.
        both_label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE,
        )
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = both_label
        request_context.metadata["call_id"] = "call-drift"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)
        assert approval_request.additional_properties["violation_type"] == "untrusted_context"
        # Only one violation was disclosed (no confidentiality restriction yet).
        assert "violations" not in approval_request.additional_properties

        # Act: the tool's policy metadata changes so a confidentiality violation now also applies.
        mock_function.additional_properties = {"max_allowed_confidentiality": "public"}

        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = both_label
        replay_context.metadata["call_id"] = "call-drift"
        replay_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        async def execute() -> None:
            pytest.fail("Tool must not execute an undisclosed violation under the old approval")

        # Assert: the replay computes a larger violation set than was disclosed, so instead of
        # executing it re-requests approval disclosing the new (data-exfiltration) risk.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)

        new_request = replay_context.result
        assert isinstance(new_request, Content)
        assert new_request.type == "function_approval_request"
        redisclosed = {entry["violation_type"] for entry in new_request.additional_properties.get("violations", [])}
        redisclosed.add(new_request.additional_properties["violation_type"])
        assert "untrusted_context" in redisclosed
        assert "max_allowed_confidentiality" in redisclosed

    async def test_replay_same_violation_type_worse_risk_requires_fresh_approval(self, mock_function):
        """A same-type violation whose disclosed risk changed must re-request approval.

        The approval binds the disclosed violation *fingerprint* (type + canonical reason), not just
        the type name. If the tool's ``max_allowed_confidentiality`` destination is loosened between
        request and replay, the violation type stays ``max_allowed_confidentiality`` but the risk
        (and its reason) worsens, so the old approval must not wave it.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)

        # Arrange: at request time the destination is PRIVATE; a USER_IDENTITY context violates it.
        mock_function.additional_properties = {"max_allowed_confidentiality": "private"}
        label = ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.USER_IDENTITY,
        )
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = label
        request_context.metadata["call_id"] = "call-worse"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)
        assert approval_request.additional_properties["violation_type"] == "max_allowed_confidentiality"
        assert "PRIVATE" in approval_request.additional_properties["reason"]

        # Act: the destination is loosened to PUBLIC (worse exfiltration risk, same violation type).
        mock_function.additional_properties = {"max_allowed_confidentiality": "public"}

        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = label
        replay_context.metadata["call_id"] = "call-worse"
        replay_context.metadata["approval_response"] = approval_request.to_function_approval_response(True)

        async def execute() -> None:
            pytest.fail("Tool must not execute a worse same-type risk under the old approval")

        # Assert: the fingerprint differs (PRIVATE -> PUBLIC destination), so it re-requests.
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)
        new_request = replay_context.result
        assert isinstance(new_request, Content)
        assert new_request.type == "function_approval_request"
        assert "PUBLIC" in new_request.additional_properties["reason"]

    async def test_non_boolean_approved_flag_is_rejected(self, mock_function):
        """An approval response whose ``approved`` is a truthy non-True value must be rejected.

        The approval gate requires a strict boolean ``True``; a crafted/deserialized response with
        ``approved`` set to a truthy string (e.g. ``"false"``) must not be treated as approval.
        """
        middleware = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        request_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        request_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        request_context.metadata["call_id"] = "call-nonbool"

        async def stop_before_execute() -> None:
            pytest.fail("Tool execution should not continue before approval")

        with pytest.raises(MiddlewareTermination):
            await middleware.process(request_context, stop_before_execute)

        approval_request = request_context.result
        assert isinstance(approval_request, Content)

        # Act: craft a response with a truthy non-True approved flag.
        crafted = approval_request.to_function_approval_response(True)
        crafted.approved = "false"  # type: ignore[assignment]

        replay_context = FunctionInvocationContext(
            function=mock_function,
            arguments=mock_function.args_schema(arg="test"),
        )
        replay_context.metadata["context_label"] = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        replay_context.metadata["call_id"] = "call-nonbool"
        replay_context.metadata["approval_response"] = crafted

        async def execute() -> None:
            pytest.fail("A non-boolean approved flag must not authorize execution")

        # Assert: not treated as approved; execution is gated (re-requests approval).
        with pytest.raises(MiddlewareTermination):
            await middleware.process(replay_context, execute)
        assert isinstance(replay_context.result, Content)
        assert replay_context.result.type == "function_approval_request"


class TestAutomaticHiding:
    """Tests for automatic variable hiding functionality."""

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""

        class MockArgs(BaseModel):
            pass

        async def mock_fn() -> str:
            return "test result"

        return FunctionTool(fn=mock_fn, name="test_function", description="Test function", args_schema=MockArgs)

    @pytest.fixture
    def middleware_auto_hide(self, mock_function):
        """Create middleware with automatic hiding enabled."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=True, hide_threshold=IntegrityLabel.UNTRUSTED)

    @pytest.fixture
    def middleware_no_auto_hide(self, mock_function):
        """Create middleware with automatic hiding disabled."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)

    @pytest.mark.asyncio
    async def test_untrusted_result_auto_hidden(self, middleware_auto_hide, mock_function):
        """Test that UNTRUSTED results are automatically hidden."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)
        # By default, AI-generated calls are UNTRUSTED

        async def next_fn():
            context.result = [Content.from_text("sensitive data")]

        await middleware_auto_hide.process(context, next_fn)

        # Result is now list[Content] with variable reference items
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        item = context.result[0]
        assert isinstance(item, Content)
        assert item.additional_properties.get("_variable_reference") is True
        parsed = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert parsed.get("type") == "variable_reference"
        assert parsed["variable_id"].startswith("var_")

        # Variable store should contain the original content
        store = middleware_auto_hide.get_variable_store()
        content, label = store.retrieve(parsed["variable_id"])
        assert content == "sensitive data"

    @pytest.mark.asyncio
    async def test_trusted_result_not_hidden(self, middleware_auto_hide, mock_function):
        """Test that TRUSTED results are not hidden."""

        # Create a function with source_integrity=trusted
        class TrustedArgs(BaseModel):
            value: str = "default"

        async def trusted_fn(value: str = "default") -> str:
            return f"result: {value}"

        trusted_function = FunctionTool(
            fn=trusted_fn,
            name="trusted_function",
            description="Trusted function",
            args_schema=TrustedArgs,
            additional_properties={"source_integrity": "trusted"},
        )

        args = trusted_function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=trusted_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("trusted data")]

        await middleware_auto_hide.process(context, next_fn)

        # Result should remain as list[Content] (TRUSTED is not hidden)
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        assert context.result[0].text == "trusted data"
        assert not context.result[0].additional_properties.get("_variable_reference", False)

    @pytest.mark.asyncio
    async def test_auto_hide_disabled(self, middleware_no_auto_hide, mock_function):
        """Test that untrusted results are not hidden when auto_hide is disabled."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("sensitive data")]

        await middleware_no_auto_hide.process(context, next_fn)

        # Result should remain as list[Content] even if UNTRUSTED
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        assert context.result[0].text == "sensitive data"
        assert not context.result[0].additional_properties.get("_variable_reference", False)

    @pytest.mark.asyncio
    async def test_variable_metadata_tracking(self, middleware_auto_hide, mock_function):
        """Test that variable metadata is properly tracked."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("private data")]

        await middleware_auto_hide.process(context, next_fn)

        # Check variable metadata
        item = context.result[0]
        parsed = json.loads(item.text)
        var_id = parsed["variable_id"]
        metadata = middleware_auto_hide.get_variable_metadata(var_id)
        assert metadata is not None
        assert "function_name" in metadata

    @pytest.mark.asyncio
    async def test_list_variables(self, middleware_auto_hide, mock_function):
        """Test that list_variables returns all stored variables."""
        args1 = mock_function.args_schema()
        context1 = FunctionInvocationContext(function=mock_function, arguments=args1)

        args2 = mock_function.args_schema()
        context2 = FunctionInvocationContext(function=mock_function, arguments=args2)

        async def next_fn1():
            context1.result = [Content.from_text("data1")]

        async def next_fn2():
            context2.result = [Content.from_text("data2")]

        await middleware_auto_hide.process(context1, next_fn1)
        await middleware_auto_hide.process(context2, next_fn2)

        variables = middleware_auto_hide.list_variables()
        assert len(variables) == 2
        parsed1 = json.loads(context1.result[0].text)
        parsed2 = json.loads(context2.result[0].text)
        assert parsed1["variable_id"] in variables
        assert parsed2["variable_id"] in variables

    @pytest.mark.asyncio
    async def test_thread_local_middleware_access(self, middleware_auto_hide, mock_function):
        """Test that middleware can be accessed via thread-local storage."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            from agent_framework.security import get_current_middleware

            # Should be able to access middleware from thread-local
            current = get_current_middleware()
            assert current is middleware_auto_hide

            context.result = [Content.from_text("test")]

        await middleware_auto_hide.process(context, next_fn)

    @pytest.mark.asyncio
    async def test_inspect_variable_uses_middleware_store(self, middleware_auto_hide, mock_function):
        """Test that inspect_variable uses the middleware's variable store."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("hidden content")]

        await middleware_auto_hide.process(context, next_fn)

        item = context.result[0]
        parsed = json.loads(item.text)
        var_id = parsed["variable_id"]

        # Verify we can retrieve the content from the store
        store = middleware_auto_hide.get_variable_store()
        content, label = store.retrieve(var_id)
        assert content == "hidden content"
        assert label.integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_inspect_variable_bypasses_auto_hide_and_taints_context(self, middleware_auto_hide):
        """inspect_variable should expose content and taint context even when auto-hide is enabled."""
        from agent_framework.security import get_security_tools

        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")

        # Seed variable store with untrusted data to inspect.
        var_id = middleware_auto_hide.get_variable_store().store(
            "raw untrusted payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE),
        )

        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": var_id, "reason": "validate exposure behavior"},
        )

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({
                        "inspected": True,
                        "variable_id": var_id,
                        "content": "raw untrusted payload",
                    })
                )
            ]

        assert middleware_auto_hide.get_context_label().integrity == IntegrityLabel.TRUSTED

        await middleware_auto_hide.process(context, next_fn)

        # Result should stay visible (no variable-reference replacement).
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        item = context.result[0]
        assert item.additional_properties.get("_variable_reference") is not True

        payload = json.loads(item.text)
        assert payload["inspected"] is True
        assert payload["variable_id"] == var_id
        assert payload["content"] == "raw untrusted payload"

        # Since content entered context, integrity should taint to UNTRUSTED.
        assert middleware_auto_hide.get_context_label().integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_inspect_variable_id_not_expanded(self, middleware_no_auto_hide):
        """inspect_variable's variable_id must not be expanded to stored content.

        The middleware expands ``var_xxx`` references in tool arguments by default
        (an anti-leak measure). For ``inspect_variable`` this would replace the ID
        with the content and break the lookup, so the tool is exempt.
        """
        from agent_framework.security import get_security_tools

        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")

        var_id = middleware_no_auto_hide.get_variable_store().store(
            "raw untrusted payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE),
        )

        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": var_id, "reason": "no expansion"},
        )

        async def next_fn():
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware_no_auto_hide.process(context, next_fn)

        # The literal ID must survive (not expanded to "raw untrusted payload").
        assert isinstance(context.arguments, dict)
        assert context.arguments["variable_id"] == var_id

        payload = json.loads(context.result[0].text)
        assert payload["inspected"] is True
        assert payload["content"] == "raw untrusted payload"

    @pytest.mark.asyncio
    async def test_inspect_variable_propagates_user_identity(self, middleware_no_auto_hide):
        """inspect_variable must propagate a USER_IDENTITY label, not downgrade it.

        The tool returns a dict whose ``security_label`` carries the inspected
        content's confidentiality. A custom result parser stamps that label onto
        the produced Content so the middleware propagates it faithfully.
        """
        from agent_framework.security import get_security_tools

        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")

        var_id = middleware_no_auto_hide.get_variable_store().store(
            "secret",
            ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.USER_IDENTITY,
                metadata={"user_id": "user-123"},
            ),
        )

        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": var_id, "reason": "propagate user identity"},
        )

        async def next_fn():
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware_no_auto_hide.process(context, next_fn)

        result_label = context.metadata["result_label"]
        assert result_label.integrity == IntegrityLabel.UNTRUSTED
        assert result_label.confidentiality == ConfidentialityLabel.USER_IDENTITY
        assert middleware_no_auto_hide.get_context_label().integrity == IntegrityLabel.UNTRUSTED
        assert middleware_no_auto_hide.get_context_label().confidentiality == ConfidentialityLabel.USER_IDENTITY

    @pytest.mark.asyncio
    async def test_inspect_variable_propagates_private(self, middleware_no_auto_hide):
        """Regression: inspect_variable preserves a PRIVATE label."""
        from agent_framework.security import get_security_tools

        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")

        var_id = middleware_no_auto_hide.get_variable_store().store(
            "secret",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE),
        )

        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": var_id, "reason": "propagate private"},
        )

        async def next_fn():
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware_no_auto_hide.process(context, next_fn)

        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert middleware_no_auto_hide.get_context_label().confidentiality == ConfidentialityLabel.PRIVATE

    @pytest.mark.asyncio
    async def test_inspect_variable_missing_var_does_not_crash(self, middleware_no_auto_hide):
        """A missing variable id returns a trusted tool-generated error."""
        from agent_framework.security import get_security_tools

        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")

        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": "var_doesnotexist1", "reason": "missing"},
        )

        async def next_fn():
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware_no_auto_hide.process(context, next_fn)

        payload = json.loads(context.result[0].text)
        assert payload["security_label"] is None
        assert "error" in payload
        assert context.metadata["result_label"].integrity == IntegrityLabel.TRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert middleware_no_auto_hide.get_context_label().integrity == IntegrityLabel.TRUSTED

    async def test_inspect_variable_foreign_var_does_not_taint_integrity(self) -> None:
        """An id owned by another store returns a trusted tool-generated error."""
        from agent_framework.security import get_security_tools

        owner = LabelTrackingFunctionMiddleware()
        foreign_id = owner.get_variable_store().store(
            "foreign secret",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.USER_IDENTITY),
        )
        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")
        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": foreign_id, "reason": "foreign id"},
        )

        async def next_fn() -> None:
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        payload = json.loads(context.result[0].text)
        assert payload["security_label"] is None
        assert "error" in payload
        assert context.metadata["result_label"].integrity == IntegrityLabel.TRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED

    async def test_inspect_variable_error_inherits_untrusted_invocation_integrity(self) -> None:
        """Attacker-labeled missing IDs cannot produce trusted visible errors."""
        from agent_framework.security import get_security_tools

        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
        inspect_tool = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")
        context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={
                "variable_id": "var_doesnotexist2",
                "reason": "untrusted missing id",
                "security_label": {
                    "integrity": "untrusted",
                    "confidentiality": "public",
                },
            },
        )

        async def next_fn() -> None:
            context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        payload = json.loads(context.result[0].text)
        assert payload["security_label"] is None
        assert "error" in payload
        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_variables(self, middleware_auto_hide, mock_function):
        """Test that multiple tool calls accumulate variables in the store."""
        for i in range(5):
            args = mock_function.args_schema()
            context = FunctionInvocationContext(function=mock_function, arguments=args)

            async def next_fn(current_context=context, data=f"data_{i}"):
                current_context.result = [Content.from_text(data)]

            await middleware_auto_hide.process(context, next_fn)

        # Should have 5 variables
        variables = middleware_auto_hide.list_variables()
        assert len(variables) == 5


class TestSecureAgentConfig:
    """Tests for SecureAgentConfig helper class."""

    def test_create_config_defaults(self):
        """Test creating config with default values."""
        from agent_framework.security import SecureAgentConfig

        config = SecureAgentConfig()

        # Should have middleware
        middleware = config.get_middleware()
        assert len(middleware) == 2
        assert isinstance(middleware[0], LabelTrackingFunctionMiddleware)
        assert isinstance(middleware[1], PolicyEnforcementFunctionMiddleware)

    def test_create_config_with_options(self):
        """Test creating config with custom options."""
        from agent_framework.security import SecureAgentConfig

        config = SecureAgentConfig(
            auto_hide_untrusted=True,
            allow_untrusted_tools={"fetch_data", "search"},
            block_on_violation=True,
        )

        middleware = config.get_middleware()
        assert len(middleware) == 2

        label_tracker = middleware[0]
        policy_enforcer = middleware[1]

        assert label_tracker.auto_hide_untrusted is True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        assert "fetch_data" in policy_enforcer.allow_untrusted_tools  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        assert "search" in policy_enforcer.allow_untrusted_tools  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    @pytest.mark.parametrize("invalid_max", [float("nan"), 1.0, True, False, 0, "1"])
    def test_max_pending_approvals_requires_positive_int(self, invalid_max: Any) -> None:
        """SecureAgentConfig must reject values that can disable policy capacity."""
        with pytest.raises(ValueError, match="max_pending_approvals must be a positive integer"):
            SecureAgentConfig(max_pending_approvals=invalid_max)  # type: ignore[arg-type]

    def test_max_pending_approvals_accepts_positive_int(self) -> None:
        config = SecureAgentConfig(max_pending_approvals=1)
        assert config._max_pending_approvals == 1

    def test_get_tools_returns_security_tools(self):
        """Test that get_tools returns quarantined_llm and inspect_variable."""
        from agent_framework.security import SecureAgentConfig

        config = SecureAgentConfig()
        tools = config.get_tools()

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "quarantined_llm" in tool_names
        assert "inspect_variable" in tool_names

    def test_get_instructions_returns_string(self):
        """Test that get_instructions returns instruction text."""
        from agent_framework.security import SECURITY_TOOL_INSTRUCTIONS, SecureAgentConfig

        config = SecureAgentConfig()
        instructions = config.get_instructions()

        assert isinstance(instructions, str)
        assert len(instructions) > 100
        assert instructions == SECURITY_TOOL_INSTRUCTIONS
        assert "quarantined_llm" in instructions
        assert "inspect_variable" in instructions

    def test_inspect_variable_uses_generic_approval_mode(self):
        """Test that inspect_variable does not require approval (context tainting handles security)."""
        from agent_framework.security import get_security_tools

        inspect_variable = next(tool for tool in get_security_tools() if tool.name == "inspect_variable")
        assert inspect_variable.approval_mode == "never_require"
        assert "requires_approval" not in inspect_variable.additional_properties  # type: ignore[operator]  # pyrefly: ignore[not-iterable]  # ty: ignore[unsupported-operator]


async def _get_session_security_middleware(
    config: SecureAgentConfig,
    session: AgentSession,
) -> tuple[LabelTrackingFunctionMiddleware, PolicyEnforcementFunctionMiddleware]:
    """Run the provider and return the middleware bound to one session."""
    context = SessionContext(session_id=session.session_id, input_messages=[])
    await config.before_run(
        agent=SimpleNamespace(),
        session=session,
        context=context,
        state=session.state.setdefault(config.source_id, {}),
    )
    middleware = context.get_middleware()
    assert isinstance(middleware[0], LabelTrackingFunctionMiddleware)
    assert isinstance(middleware[1], PolicyEnforcementFunctionMiddleware)
    return middleware[0], middleware[1]


class TestSecureAgentSessionIsolation:
    """Regression tests for session-scoped FIDES state."""

    async def test_routine_logs_redact_hidden_content_handles_and_quarantine_prompt(self, caplog) -> None:
        """INFO and WARNING logs must not disclose hidden data or its handles."""

        class SinkArgs(BaseModel):
            value: str

        async def sink(value: str) -> str:
            return value

        caplog.set_level(logging.INFO, logger="agent_framework.security")
        tracker = LabelTrackingFunctionMiddleware()
        secret = "EXPANDED-CONTENT-SECRET"
        variable_id = tracker.get_variable_store().store(
            secret,
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink_tool = FunctionTool(
            fn=sink,
            name="sink",
            description="Accept a value",
            args_schema=SinkArgs,
            additional_properties={"source_integrity": "trusted"},
        )
        sink_context = FunctionInvocationContext(
            function=sink_tool,
            arguments=SinkArgs(value=f"[{variable_id}]"),
        )

        async def execute_sink() -> None:
            sink_context.result = [Content.from_text("sent")]

        await tracker.process(sink_context, execute_sink)

        quarantine_prompt = "QUARANTINE-PROMPT-SECRET"
        quarantine_tool = next(tool for tool in tracker.get_security_tools() if tool.name == "quarantined_llm")
        quarantine_context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={"prompt": quarantine_prompt, "variable_ids": [variable_id]},
        )

        async def execute_quarantine() -> None:
            quarantine_context.result = await quarantine_tool.invoke(
                arguments=quarantine_context.arguments,
                context=quarantine_context,
            )

        await tracker.process(quarantine_context, execute_quarantine)

        inspect_tool = next(tool for tool in tracker.get_security_tools() if tool.name == "inspect_variable")
        inspect_context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={
                "variable_id": variable_id,
                "reason": f"Review hidden handle {variable_id}",
            },
        )

        async def execute_inspection() -> None:
            inspect_context.result = await inspect_tool.invoke(
                arguments=inspect_context.arguments, context=inspect_context
            )

        await tracker.process(inspect_context, execute_inspection)

        routine_logs = "\n".join(record.getMessage() for record in caplog.records if record.levelno >= logging.INFO)
        assert variable_id not in routine_logs
        assert secret not in routine_logs
        assert quarantine_prompt not in routine_logs

    async def test_provider_scoping_preserves_middleware_customization(self) -> None:
        """Provider runs clone the current overridable middleware stack into the session scope."""

        class CustomConfig(SecureAgentConfig):
            def get_middleware(self) -> list[FunctionMiddleware]:
                assert self.policy_enforcer is not None
                return [self.policy_enforcer, self.label_tracker]

        config = CustomConfig()
        configured_tracker = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
        config.label_tracker = configured_tracker
        assert config.policy_enforcer is not None
        config.policy_enforcer.allow_untrusted_tools.add("post_init_tool")

        session = AgentSession(session_id="customized-provider")
        context = SessionContext(session_id=session.session_id, input_messages=[])
        await config.before_run(
            agent=SimpleNamespace(),
            session=session,
            context=context,
            state=session.state.setdefault(config.source_id, {}),
        )

        scoped_policy, scoped_tracker = context.get_middleware()
        assert isinstance(scoped_tracker, LabelTrackingFunctionMiddleware)
        assert scoped_tracker is not configured_tracker
        assert scoped_tracker.auto_hide_untrusted is False
        assert isinstance(scoped_policy, PolicyEnforcementFunctionMiddleware)
        assert scoped_policy is not config.policy_enforcer
        assert "post_init_tool" in scoped_policy.allow_untrusted_tools

    async def test_provider_use_requires_session_for_state_accessors(self) -> None:
        """No-session access remains standalone-only and becomes explicit after provider use."""
        config = SecureAgentConfig()
        standalone_id = config.get_variable_store().store("standalone", ContentLabel())
        assert config.list_variables() == [standalone_id]

        session = AgentSession(session_id="provider-accessor")
        await _get_session_security_middleware(config, session)

        with pytest.raises(ValueError, match="session is required"):
            config.get_audit_log()
        with pytest.raises(ValueError, match="session is required"):
            config.get_variable_store()
        with pytest.raises(ValueError, match="session is required"):
            config.list_variables()

        assert config.get_audit_log(session) == []
        assert config.list_variables(session) == []

    async def test_explicit_sessions_isolate_and_restore_state_across_a_b_a(self) -> None:
        """A shared config persists each explicit session without reset-on-switch."""
        config = SecureAgentConfig()
        alice = AgentSession(session_id="alice")
        bob = AgentSession(session_id="bob")

        alice_tracker, _ = await _get_session_security_middleware(config, alice)
        alice_tracker._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))
        alice_variable = alice_tracker.get_variable_store().store(
            {"secret": ["alice"]},
            ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.PRIVATE,
            ),
        )

        bob_tracker, _ = await _get_session_security_middleware(config, bob)
        assert bob_tracker.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert not bob_tracker.get_variable_store().exists(alice_variable)

        alice_tracker_again, _ = await _get_session_security_middleware(config, alice)
        assert alice_tracker_again.get_context_label().integrity == IntegrityLabel.UNTRUSTED
        assert alice_tracker_again.get_variable_store().retrieve(alice_variable)[0] == {"secret": ["alice"]}
        assert config.list_variables(alice) == [alice_variable]
        assert config.list_variables(bob) == []

        restored = AgentSession.from_dict(json.loads(json.dumps(alice.to_dict())))
        restored_tracker, _ = await _get_session_security_middleware(config, restored)
        assert restored_tracker.get_context_label().integrity == IntegrityLabel.UNTRUSTED
        assert restored_tracker.get_variable_store().retrieve(alice_variable)[0] == {"secret": ["alice"]}

    async def test_omitted_sessions_receive_distinct_generated_security_state(self) -> None:
        """Each session-less Agent.run receives a fresh provider session."""

        class RecordingConfig(SecureAgentConfig):
            def __init__(self) -> None:
                super().__init__()
                self.run_trackers: list[LabelTrackingFunctionMiddleware] = []
                self.session_ids: list[str] = []

            async def before_run(self, **kwargs: Any) -> None:
                await super().before_run(**kwargs)
                tracker = kwargs["context"].get_middleware()[0]
                assert isinstance(tracker, LabelTrackingFunctionMiddleware)
                self.run_trackers.append(tracker)
                self.session_ids.append(kwargs["session"].session_id)
                if len(self.run_trackers) == 1:
                    tracker._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))

        class StaticClient:
            async def get_response(self, messages: Any, **kwargs: Any) -> ChatResponse:
                return ChatResponse(messages=[Message(role="assistant", contents=["done"])])

        config = RecordingConfig()
        agent = Agent(client=StaticClient(), context_providers=[config])  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

        await agent.run("first")
        await agent.run("second")

        assert config.session_ids[0] != config.session_ids[1]
        assert config.run_trackers[0] is not config.run_trackers[1]
        assert config.run_trackers[0].get_context_label().integrity == IntegrityLabel.UNTRUSTED
        assert config.run_trackers[1].get_context_label().integrity == IntegrityLabel.TRUSTED

    async def test_overlapping_sessions_keep_task_local_middleware(self) -> None:
        """Overlapping invocations inspect variables through their own middleware."""
        config = SecureAgentConfig()
        alice_tracker, _ = await _get_session_security_middleware(config, AgentSession(session_id="alice-overlap"))
        bob_tracker, _ = await _get_session_security_middleware(config, AgentSession(session_id="bob-overlap"))
        alice_id = alice_tracker.get_variable_store().store(
            "alice secret", ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        bob_id = bob_tracker.get_variable_store().store("bob secret", ContentLabel(integrity=IntegrityLabel.UNTRUSTED))
        inspect_tool = next(tool for tool in config.get_tools() if tool.name == "inspect_variable")
        both_started = asyncio.Event()
        started = 0

        async def inspect(
            tracker: LabelTrackingFunctionMiddleware,
            variable_id: str,
        ) -> str:
            nonlocal started
            context = FunctionInvocationContext(
                function=inspect_tool,
                arguments={"variable_id": variable_id, "reason": "overlap isolation"},
            )

            async def execute() -> None:
                nonlocal started
                started += 1
                if started == 2:
                    both_started.set()
                await both_started.wait()
                await asyncio.sleep(0)
                assert get_current_middleware() is tracker
                context.result = await inspect_tool.invoke(arguments=context.arguments, context=context)

            await tracker.process(context, execute)
            return cast(str, json.loads(context.result[0].text)["content"])

        assert await asyncio.gather(inspect(alice_tracker, alice_id), inspect(bob_tracker, bob_id)) == [
            "alice secret",
            "bob secret",
        ]
        assert get_current_middleware() is None

    async def test_foreign_owned_variable_and_metadata_are_denied_without_logging_id(self, caplog) -> None:
        """Copied foreign state remains inaccessible and its handle stays out of routine logs."""
        caplog.set_level(logging.WARNING, logger="agent_framework.security")
        config = SecureAgentConfig()
        alice = AgentSession(session_id="alice-owner")
        bob = AgentSession(session_id="bob-owner")
        alice_tracker, _ = await _get_session_security_middleware(config, alice)
        bob_tracker, bob_policy = await _get_session_security_middleware(config, bob)
        alice_variable = alice_tracker.get_variable_store().store(
            "alice secret", ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        alice_entry = alice.state[config.source_id]["variables"][alice_variable]
        alice_metadata = {"details": ["alice metadata"]}
        alice.state[config.source_id].setdefault("variable_metadata", {})[alice_variable] = alice_metadata
        detached_metadata = alice_tracker.get_variable_metadata(alice_variable)
        assert detached_metadata == alice_metadata
        assert detached_metadata is not None
        detached_metadata["details"].append("mutation")
        assert alice_tracker.get_variable_metadata(alice_variable) == alice_metadata

        bob.state[config.source_id].setdefault("variables", {})[alice_variable] = json.loads(json.dumps(alice_entry))
        bob.state[config.source_id].setdefault("variable_metadata", {})[alice_variable] = json.loads(
            json.dumps(alice_metadata)
        )
        assert not bob_tracker.get_variable_store().exists(alice_variable)
        assert bob_tracker.get_variable_metadata(alice_variable) is None

        inspect_tool = next(tool for tool in config.get_tools() if tool.name == "inspect_variable")
        inspect_context = FunctionInvocationContext(
            function=inspect_tool,
            arguments={"variable_id": alice_variable, "reason": "cross-session probe"},
            session=bob,
        )

        async def inspect() -> list[Content]:
            return await inspect_tool.invoke(arguments=inspect_context.arguments, context=inspect_context)

        await FunctionMiddlewarePipeline(bob_tracker, bob_policy).execute(inspect_context, lambda _: inspect())
        inspected = json.loads(inspect_context.result[0].text)
        routine_logs = "\n".join(record.getMessage() for record in caplog.records)
        assert alice_variable not in routine_logs
        assert inspected["security_label"] is None
        assert "error" in inspected

        received: list[str] = []

        class SinkArgs(BaseModel):
            value: str

        async def sink(value: str) -> str:
            received.append(value)
            return "sent"

        sink_tool = FunctionTool(
            fn=sink,
            name="sink",
            description="Accept a value",
            args_schema=SinkArgs,
            additional_properties={"source_integrity": "trusted", "accepts_untrusted": True},
        )
        sink_context = FunctionInvocationContext(
            function=sink_tool,
            arguments={"value": f"[{alice_variable}]"},
            session=bob,
        )

        async def execute_sink(_: FunctionInvocationContext) -> list[Content]:
            received.append(cast(dict[str, Any], sink_context.arguments)["value"])
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(bob_tracker, bob_policy).execute(sink_context, execute_sink)
        assert received == [f"[{alice_variable}]"]

    async def test_session_state_is_detached_json_and_rejects_unsupported_values(self) -> None:
        """Durable hidden state is detached and strictly JSON-compatible."""
        config = SecureAgentConfig()
        session = AgentSession(session_id="durable-state")
        store = config.get_variable_store(session)
        type_shaped_data = {
            "type": "message",
            "role": "user",
            "contents": ["plain data"],
        }
        payload: dict[str, Any] = {
            "values": [None, True, 1, 1.5, "text"],
            "coordinates": ("x", 2),
            "content": Content.from_text("hello"),
            "type_shaped_data": type_shaped_data,
        }
        variable_id = store.store(payload, ContentLabel(metadata={"type_shaped_data": type_shaped_data}))
        payload["values"].append("mutated")

        restored = AgentSession.from_dict(json.loads(json.dumps(session.to_dict())))
        restored_content, restored_label = config.get_variable_store(restored).retrieve(variable_id)
        assert restored_content["values"] == [None, True, 1, 1.5, "text"]
        assert restored_content["coordinates"] == ["x", 2]
        assert restored_content["content"]["type"] == "text"
        assert restored_content["type_shaped_data"] == type_shaped_data
        assert isinstance(restored_content["type_shaped_data"], dict)
        assert restored_label.metadata == {"type_shaped_data": type_shaped_data}

        restored_content["values"].append("retrieval mutation")
        assert config.get_variable_store(restored).retrieve(variable_id)[0]["values"] == [None, True, 1, 1.5, "text"]

        with pytest.raises(TypeError, match="variable content.*object"):
            store.store(object(), ContentLabel())
        with pytest.raises(TypeError, match="label.*metadata.*bad.*object"):
            store.store("safe", ContentLabel(metadata={"bad": object()}))

        tracker, _ = await _get_session_security_middleware(config, session)
        with pytest.raises(TypeError, match="context label.*metadata.*bad.*object"):
            tracker._update_context_label(ContentLabel(metadata={"bad": object()}))

        malformed = AgentSession(session_id="malformed-context-label")
        malformed.state[config.source_id] = {
            "scope_id": malformed.session_id,
            "context_label": json.dumps({}),
        }
        malformed_tracker, _ = await _get_session_security_middleware(config, malformed)
        with pytest.raises(ValueError, match="integrity and confidentiality"):
            malformed_tracker.get_context_label()

    async def test_audit_and_pending_approval_are_session_scoped_and_resume_after_restore(self) -> None:
        """Audit and approval state persists only in the owning session."""
        config = SecureAgentConfig(approval_on_violation=True)
        alice = AgentSession(session_id="approval-session")
        bob = AgentSession(session_id="other-session")
        alice_tracker, alice_policy = await _get_session_security_middleware(config, alice)
        _, bob_policy = await _get_session_security_middleware(config, bob)
        type_shaped_metadata = {
            "type": "message",
            "role": "user",
            "contents": ["audit metadata"],
        }
        alice_tracker._update_context_label(
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, metadata={"type_shaped_data": type_shaped_metadata})
        )

        class ToolArgs(BaseModel):
            value: str

        async def restricted(value: str) -> str:
            return value

        restricted_tool = FunctionTool(
            fn=restricted,
            name="restricted",
            description="Restricted operation",
            args_schema=ToolArgs,
        )
        request = FunctionInvocationContext(
            function=restricted_tool,
            arguments=ToolArgs(value="payload"),
            session=alice,
        )
        request.metadata.update({"call_id": "provider-call", "function_call_occurrence_id": "occurrence-1"})

        async def should_not_execute(_: FunctionInvocationContext) -> None:
            pytest.fail("Tool execution should stop for approval")

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(alice_tracker, alice_policy).execute(request, should_not_execute)

        approval_request = request.result
        assert isinstance(approval_request, Content)
        assert approval_request.type == "function_approval_request"
        assert approval_request.id == "occurrence-1"
        assert approval_request.function_call.call_id == "provider-call"  # type: ignore[union-attr]
        assert config.get_audit_log(alice)[-1]["function"] == "restricted"
        assert config.get_audit_log(bob) == []
        assert bob_policy._pending_policy_approvals == {}

        restored = AgentSession.from_dict(json.loads(json.dumps(alice.to_dict())))
        restored_audit = config.get_audit_log(restored)
        restored_metadata = restored_audit[-1]["context_label"]["metadata"]["type_shaped_data"]
        assert restored_metadata == type_shaped_metadata
        assert isinstance(restored_metadata, dict)
        restored_tracker, restored_policy = await _get_session_security_middleware(config, restored)
        replay = FunctionInvocationContext(
            function=restricted_tool,
            arguments=ToolArgs(value="payload"),
            session=restored,
        )
        replay.metadata.update({
            "call_id": "provider-call",
            "function_call_occurrence_id": "occurrence-1",
            "approval_response": approval_request.to_function_approval_response(True),
        })
        executions = 0

        async def execute(_: FunctionInvocationContext) -> list[Content]:
            nonlocal executions
            executions += 1
            return [Content.from_text("executed")]

        await FunctionMiddlewarePipeline(restored_tracker, restored_policy).execute(replay, execute)
        assert executions == 1
        assert replay.metadata["user_approved_violation"] is True
        assert "occurrence-1" not in restored_policy._pending_policy_approvals

        repeated = FunctionInvocationContext(
            function=restricted_tool,
            arguments=ToolArgs(value="payload"),
            session=restored,
        )
        repeated.metadata.update({
            "call_id": "provider-call",
            "function_call_occurrence_id": "occurrence-1",
            "approval_response": approval_request.to_function_approval_response(True),
        })
        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(restored_tracker, restored_policy).execute(repeated, execute)
        assert executions == 1
        assert isinstance(repeated.result, Content)
        assert repeated.result.type == "function_approval_request"


class TestGetSecurityTools:
    """Tests for get_security_tools function."""

    def test_get_security_tools_from_module(self):
        """Test importing get_security_tools from agent_framework."""
        from agent_framework.security import get_security_tools

        tools = get_security_tools()
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "quarantined_llm" in tool_names
        assert "inspect_variable" in tool_names

    def test_get_security_tools_from_middleware(self):
        """Test getting security tools from middleware instance."""
        middleware = LabelTrackingFunctionMiddleware()
        tools = middleware.get_security_tools()

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "quarantined_llm" in tool_names
        assert "inspect_variable" in tool_names


class TestQuarantinedLLMWithVariableIds:
    """Tests for quarantined_llm with variable_ids parameter."""

    @pytest.fixture
    def middleware_with_store(self):
        """Create middleware with variables pre-populated."""
        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=True)
        middleware._set_as_current()
        yield middleware
        middleware._clear_current()

    @pytest.mark.asyncio
    async def test_quarantined_llm_with_single_variable_id(self, middleware_with_store):
        """Test quarantined_llm retrieves content from variable store."""
        from agent_framework.security import quarantined_llm

        # Store a variable
        store = middleware_with_store.get_variable_store()
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_id = store.store("Test content for processing", label)

        # Call quarantined_llm with variable_id
        result = await quarantined_llm(prompt="Process this content", variable_ids=[var_id])

        assert result["quarantined"] is True
        assert var_id in result["variables_processed"]
        assert len(result["content_summary"]) == 1
        assert "27 chars" in result["content_summary"][0]  # len("Test content for processing")

    @pytest.mark.asyncio
    async def test_quarantined_llm_with_multiple_variable_ids(self, middleware_with_store):
        """Test quarantined_llm retrieves multiple variables."""
        from agent_framework.security import quarantined_llm

        # Store multiple variables
        store = middleware_with_store.get_variable_store()
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_id1 = store.store("First content", label)
        var_id2 = store.store("Second content", label)

        # Call quarantined_llm with multiple variable_ids
        result = await quarantined_llm(prompt="Compare these", variable_ids=[var_id1, var_id2])

        assert result["quarantined"] is True
        assert len(result["variables_processed"]) == 2
        assert var_id1 in result["variables_processed"]
        assert var_id2 in result["variables_processed"]
        assert len(result["content_summary"]) == 2

    @pytest.mark.asyncio
    async def test_quarantined_llm_with_unknown_variable_id(self, middleware_with_store):
        """Test quarantined_llm handles unknown variable IDs gracefully."""
        from agent_framework.security import quarantined_llm

        # Call with non-existent variable ID
        result = await quarantined_llm(prompt="Process this", variable_ids=["var_nonexistent"])

        # Should still return a result, just with UNTRUSTED label
        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"
        assert "var_nonexistent" in result["variables_processed"]

    @pytest.mark.asyncio
    async def test_quarantined_llm_without_variable_ids(self, middleware_with_store):
        """Test quarantined_llm works with labelled_data instead of variable_ids."""
        from agent_framework.security import quarantined_llm

        result = await quarantined_llm(
            prompt="Process this data",
            labelled_data={
                "data": {
                    "content": "Some external data",
                    "security_label": {"integrity": "untrusted", "confidentiality": "public"},
                }
            },
        )

        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"

    @pytest.mark.asyncio
    async def test_quarantined_llm_with_legacy_label_key(self, middleware_with_store):
        """Test quarantined_llm accepts legacy 'label' key for backward compatibility."""
        from agent_framework.security import quarantined_llm

        result = await quarantined_llm(
            prompt="Process this data",
            labelled_data={
                "data": {
                    "content": "Some external data",
                    "label": {"integrity": "untrusted", "confidentiality": "public"},  # Legacy key
                }
            },
        )

        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"


class TestMiddlewareSetCurrent:
    """Tests for middleware _set_as_current and _clear_current methods."""

    def test_set_and_clear_current(self):
        """Test setting and clearing thread-local middleware reference."""
        from agent_framework.security import get_current_middleware

        # Initially no middleware
        assert get_current_middleware() is None

        middleware = LabelTrackingFunctionMiddleware()
        middleware._set_as_current()

        # Now middleware is set
        assert get_current_middleware() is middleware

        middleware._clear_current()

        # Back to None
        assert get_current_middleware() is None

    def test_set_current_overwrites_previous(self):
        """Test that setting current overwrites previous middleware."""
        from agent_framework.security import get_current_middleware

        middleware1 = LabelTrackingFunctionMiddleware()
        middleware2 = LabelTrackingFunctionMiddleware()

        middleware1._set_as_current()
        assert get_current_middleware() is middleware1

        middleware2._set_as_current()
        assert get_current_middleware() is middleware2

        middleware2._clear_current()
        assert get_current_middleware() is None


class TestContextLabelTracking:
    """Tests for context-level label tracking."""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""

        class MockArgs(BaseModel):
            arg: str = "default"

        async def mock_fn(arg: str = "default") -> str:
            return f"result: {arg}"

        return FunctionTool(fn=mock_fn, name="test_function", description="Test function", args_schema=MockArgs)

    def test_initial_context_label(self, middleware):
        """Test that context label starts as TRUSTED + PUBLIC."""
        context_label = middleware.get_context_label()
        assert context_label.integrity == IntegrityLabel.TRUSTED
        assert context_label.confidentiality == ConfidentialityLabel.PUBLIC

    def test_reset_context_label(self, middleware, mock_function):
        """Test that context label can be reset."""
        # Taint the context first
        middleware._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED

        # Reset
        middleware.reset_context_label()
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.PUBLIC

    @pytest.mark.asyncio
    async def test_context_label_updated_after_untrusted_result(self, middleware, mock_function):
        """Test that context label becomes UNTRUSTED after untrusted result enters context."""
        # Disable auto-hide so result enters context
        middleware.auto_hide_untrusted = False

        # The mock_function has no source_integrity, so it defaults to UNTRUSTED
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("untrusted result")]

        # Initial context should be TRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED

        await middleware.process(context, next_fn)

        # Context should now be UNTRUSTED (default source_integrity = UNTRUSTED)
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_context_label_unchanged_when_result_hidden(self, mock_function):
        """Test that context label stays TRUSTED when untrusted result is hidden."""
        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=True)

        # The mock_function has no source_integrity, so it defaults to UNTRUSTED
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("untrusted result")]

        # Initial context should be TRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED

        await middleware.process(context, next_fn)

        # Context should STILL be TRUSTED because result was hidden
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        # Result should be list[Content] with variable reference
        assert isinstance(context.result, list)
        item = context.result[0]
        parsed = json.loads(item.text)
        assert parsed.get("type") == "variable_reference"

    @pytest.mark.asyncio
    async def test_context_label_passed_to_policy_enforcement(self, middleware, mock_function):
        """Test that context label is passed in metadata for policy enforcement."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("result")]

        await middleware.process(context, next_fn)

        # Both result label and context label should be in metadata
        assert "result_label" in context.metadata
        assert "context_label" in context.metadata
        assert isinstance(context.metadata["context_label"], ContentLabel)

    @pytest.mark.asyncio
    async def test_context_label_accumulates_across_calls(self, middleware, mock_function):
        """Test that context label accumulates restrictions across multiple tool calls."""
        middleware.auto_hide_untrusted = False

        # Create a trusted function (source_integrity=trusted)
        class TrustedArgs(BaseModel):
            value: str = "default"

        async def trusted_fn(value: str = "default") -> str:
            return f"result: {value}"

        trusted_function = FunctionTool(
            fn=trusted_fn,
            name="trusted_function",
            description="Trusted function",
            args_schema=TrustedArgs,
            additional_properties={"source_integrity": "trusted"},
        )

        # Create an untrusted function (no source_integrity = default UNTRUSTED)
        class UntrustedArgs(BaseModel):
            value: str = "default"

        async def untrusted_fn(value: str = "default") -> str:
            return f"external: {value}"

        untrusted_function = FunctionTool(
            fn=untrusted_fn,
            name="external_function",
            description="Fetches external data (untrusted)",
            args_schema=UntrustedArgs,
            # No source_integrity = defaults to UNTRUSTED
        )

        current_context = None

        async def next_fn():
            current_context.result = [Content.from_text("result")]  # type: ignore[attr-defined, union-attr]  # ty: ignore[invalid-assignment]

        # First call: trusted function (TRUSTED)
        context1 = FunctionInvocationContext(function=trusted_function, arguments=trusted_function.args_schema())  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        current_context = context1

        await middleware.process(context1, next_fn)

        # Context should still be TRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED

        # Second call: untrusted function (UNTRUSTED)
        context2 = FunctionInvocationContext(function=untrusted_function, arguments=untrusted_function.args_schema())  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        current_context = context2

        await middleware.process(context2, next_fn)

        # Context should now be UNTRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED

        # Third call: trusted function again
        context3 = FunctionInvocationContext(function=trusted_function, arguments=trusted_function.args_schema())  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        current_context = context3

        await middleware.process(context3, next_fn)

        # Context should STILL be UNTRUSTED (once tainted, stays tainted)
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED


class TestPolicyEnforcementWithContextLabel:
    """Tests for policy enforcement using context labels."""

    @pytest.fixture
    def label_middleware(self):
        """Create label tracking middleware."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)

    @pytest.fixture
    def policy_middleware(self):
        """Create policy enforcement middleware."""
        return PolicyEnforcementFunctionMiddleware(allow_untrusted_tools={"allowed_function"}, block_on_violation=True)

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""

        class MockArgs(BaseModel):
            arg: str = "default"

        async def mock_fn(arg: str = "default") -> str:
            return f"result: {arg}"

        return FunctionTool(
            fn=mock_fn, name="restricted_function", description="Restricted function", args_schema=MockArgs
        )

    @pytest.mark.asyncio
    async def test_policy_blocks_in_untrusted_context(self, label_middleware, policy_middleware, mock_function):
        """Test that policy blocks tool calls when context is UNTRUSTED."""
        # First, taint the context
        label_middleware._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))

        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        # Set up context_label as if label_middleware ran
        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "should not reach"

        with pytest.raises(MiddlewareTermination):
            await policy_middleware.process(context, next_fn)

        # Should be blocked due to untrusted context
        assert "error" in context.result
        assert "untrusted context" in context.result["error"]

    @pytest.mark.asyncio
    async def test_policy_allows_whitelisted_tool_in_untrusted_context(self, label_middleware, policy_middleware):
        """Test that whitelisted tools are allowed even in UNTRUSTED context."""
        # Taint the context
        label_middleware._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))

        class MockArgs(BaseModel):
            arg: str = "default"

        async def mock_fn(arg: str = "default") -> str:
            return f"result: {arg}"

        allowed_function = FunctionTool(
            fn=mock_fn,
            name="allowed_function",  # In allow_untrusted_tools
            description="Allowed function",
            args_schema=MockArgs,
        )

        args = allowed_function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=allowed_function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "allowed"

        await policy_middleware.process(context, next_fn)

        # Should be allowed
        assert context.result == "allowed"


# ========== Phase 1: Message-Level Label Tracking Tests ==========


class TestLabeledMessage:
    """Tests for LabeledMessage class."""

    def test_create_user_message_defaults_to_trusted(self):
        """Test that user messages are TRUSTED by default."""
        from agent_framework.security import LabeledMessage

        msg = LabeledMessage(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED
        assert msg.is_trusted()

    def test_create_system_message_defaults_to_trusted(self):
        """Test that system messages are TRUSTED by default."""
        from agent_framework.security import LabeledMessage

        msg = LabeledMessage(role="system", content="You are an assistant.")
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED

    def test_create_tool_message_defaults_to_untrusted(self):
        """Test that tool messages are UNTRUSTED by default."""
        from agent_framework.security import LabeledMessage

        msg = LabeledMessage(role="tool", content="External API result")
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert not msg.is_trusted()

    def test_create_assistant_message_no_sources(self):
        """Test assistant message without sources defaults to TRUSTED."""
        from agent_framework.security import LabeledMessage

        msg = LabeledMessage(role="assistant", content="I'll help you.")
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED

    def test_create_assistant_message_with_untrusted_source(self):
        """Test assistant message inherits UNTRUSTED from sources."""
        from agent_framework.security import LabeledMessage

        untrusted_source = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        msg = LabeledMessage(role="assistant", content="Based on the data...", source_labels=[untrusted_source])
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED

    def test_explicit_label_overrides_inference(self):
        """Test that explicit label overrides role-based inference."""
        from agent_framework.security import LabeledMessage

        explicit_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)
        msg = LabeledMessage(
            role="user",  # Would normally be TRUSTED
            content="Hello",
            security_label=explicit_label,
        )
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert msg.security_label.confidentiality == ConfidentialityLabel.PRIVATE

    def test_message_serialization(self):
        """Test LabeledMessage serialization to dict."""
        from agent_framework.security import LabeledMessage

        msg = LabeledMessage(role="user", content="Hello", message_index=5, metadata={"key": "value"})

        data = msg.to_dict()
        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert data["message_index"] == 5
        assert data["security_label"]["integrity"] == "trusted"

    def test_message_deserialization(self):
        """Test LabeledMessage deserialization from dict."""
        from agent_framework.security import LabeledMessage

        data = {
            "role": "tool",
            "content": "API result",
            "security_label": {"integrity": "untrusted", "confidentiality": "public"},
            "message_index": 3,
        }

        msg = LabeledMessage.from_dict(data)
        assert msg.role == "tool"
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert msg.message_index == 3

    def test_from_message_convenience_method(self):
        """Test creating LabeledMessage from a standard message dict."""
        from agent_framework.security import LabeledMessage

        standard_msg = {"role": "user", "content": "What's the weather?"}
        labeled = LabeledMessage.from_message(standard_msg, index=0)

        assert labeled.role == "user"
        assert labeled.content == "What's the weather?"
        assert labeled.message_index == 0
        assert labeled.is_trusted()


# ========== Quarantined LLM Tests ==========


class TestQuarantinedLLM:
    """Tests for quarantined_llm tool behavior.

    Note: Auto-hiding of UNTRUSTED results is handled by the middleware
    via source_integrity="untrusted", not by quarantined_llm itself.
    """

    async def test_quarantined_llm_publishes_combined_confidentiality(self) -> None:
        """Quarantine output is UNTRUSTED at the highest input confidentiality."""
        middleware = LabelTrackingFunctionMiddleware()
        variable_id = middleware.get_variable_store().store(
            "identity secret",
            ContentLabel(
                integrity=IntegrityLabel.TRUSTED,
                confidentiality=ConfidentialityLabel.USER_IDENTITY,
            ),
        )
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={"prompt": "Summarize", "variable_ids": [variable_id]},
        )

        async def next_fn() -> None:
            context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.USER_IDENTITY
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.USER_IDENTITY
        hidden_reference = json.loads(context.result[0].text)
        _, hidden_label = middleware.get_variable_store().retrieve(hidden_reference["variable_id"])
        assert hidden_label.integrity == IntegrityLabel.UNTRUSTED
        assert hidden_label.confidentiality == ConfidentialityLabel.USER_IDENTITY

    async def test_quarantined_llm_public_input_remains_public(self) -> None:
        """A valid quarantine label overrides the fail-closed PRIVATE fallback."""
        from agent_framework.security import set_quarantine_client

        set_quarantine_client(None)
        middleware = LabelTrackingFunctionMiddleware()
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={
                "prompt": "Summarize",
                "labelled_data": {
                    "data": {
                        "content": "public information",
                        "security_label": {
                            "integrity": "trusted",
                            "confidentiality": "public",
                            "metadata": ["malformed"],
                        },
                    }
                },
            },
        )

        async def next_fn() -> None:
            context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PUBLIC
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.PUBLIC

    async def test_quarantined_llm_invalid_label_falls_back_to_private(self) -> None:
        """A partial parser label cannot override the PRIVATE tool fallback."""
        from agent_framework.security import _quarantined_llm_result_parser

        middleware = LabelTrackingFunctionMiddleware()
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={"prompt": "Summarize"},
        )

        async def next_fn() -> None:
            context.result = _quarantined_llm_result_parser({
                "response": "partial label",
                "security_label": {"integrity": "untrusted"},
            })

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        hidden_reference = json.loads(context.result[0].text)
        _, hidden_label = middleware.get_variable_store().retrieve(hidden_reference["variable_id"])
        assert hidden_label.integrity == IntegrityLabel.UNTRUSTED
        assert hidden_label.confidentiality == ConfidentialityLabel.PRIVATE

    async def test_quarantined_llm_partial_input_label_is_private(self) -> None:
        """An incomplete quarantine input label fails closed to PRIVATE."""
        from agent_framework.security import set_quarantine_client

        set_quarantine_client(None)
        middleware = LabelTrackingFunctionMiddleware()
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={
                "prompt": "Summarize",
                "labelled_data": {
                    "data": {
                        "content": "unknown information",
                        "security_label": {"integrity": "trusted"},
                    }
                },
            },
        )

        async def next_fn() -> None:
            context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE

    async def test_quarantined_llm_malformed_input_is_private(self) -> None:
        """A malformed item makes mixed quarantine input PRIVATE."""
        from agent_framework.security import set_quarantine_client

        set_quarantine_client(None)
        middleware = LabelTrackingFunctionMiddleware()
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={
                "prompt": "Summarize",
                "labelled_data": {
                    "public": {
                        "content": "public information",
                        "security_label": {
                            "integrity": "trusted",
                            "confidentiality": "public",
                        },
                    },
                    "malformed": "unlabeled information",
                },
            },
        )

        async def next_fn() -> None:
            context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.UNTRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE

    async def test_quarantined_llm_empty_input_placeholder_is_private(self) -> None:
        """An unlabeled placeholder response remains PRIVATE."""
        from agent_framework.security import set_quarantine_client

        set_quarantine_client(None)
        middleware = LabelTrackingFunctionMiddleware()
        quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
        context = FunctionInvocationContext(
            function=quarantine_tool,
            arguments={
                "prompt": "Summarize sensitive instructions",
                "variable_ids": [],
                "labelled_data": {},
            },
        )

        async def next_fn() -> None:
            context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

        await middleware.process(context, next_fn)

        result_label = context.metadata["result_label"]
        assert result_label.integrity == IntegrityLabel.UNTRUSTED
        assert result_label.confidentiality == ConfidentialityLabel.PRIVATE
        hidden_reference = json.loads(context.result[0].text)
        hidden_content, hidden_label = middleware.get_variable_store().retrieve(hidden_reference["variable_id"])
        assert hidden_label.integrity == IntegrityLabel.UNTRUSTED
        assert hidden_label.confidentiality == ConfidentialityLabel.PRIVATE
        assert "[Quarantined LLM Response]" in json.loads(hidden_content)["response"]

    async def test_quarantined_llm_empty_input_client_response_is_private(self) -> None:
        """An unlabeled client response remains PRIVATE."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework.security import set_quarantine_client

        mock_response = MagicMock()
        mock_response.text = "client-produced sensitive response"
        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(return_value=mock_response)
        set_quarantine_client(mock_client)

        try:
            middleware = LabelTrackingFunctionMiddleware()
            quarantine_tool = next(tool for tool in middleware.get_security_tools() if tool.name == "quarantined_llm")
            context = FunctionInvocationContext(
                function=quarantine_tool,
                arguments={
                    "prompt": "Summarize sensitive instructions",
                    "variable_ids": [],
                    "labelled_data": {},
                },
            )

            async def next_fn() -> None:
                context.result = await quarantine_tool.invoke(arguments=context.arguments, context=context)

            await middleware.process(context, next_fn)

            result_label = context.metadata["result_label"]
            assert result_label.integrity == IntegrityLabel.UNTRUSTED
            assert result_label.confidentiality == ConfidentialityLabel.PRIVATE
            hidden_reference = json.loads(context.result[0].text)
            hidden_content, hidden_label = middleware.get_variable_store().retrieve(hidden_reference["variable_id"])
            assert hidden_label.integrity == IntegrityLabel.UNTRUSTED
            assert hidden_label.confidentiality == ConfidentialityLabel.PRIVATE
            assert json.loads(hidden_content)["response"] == "client-produced sensitive response"
            mock_client.get_response.assert_awaited_once()
        finally:
            set_quarantine_client(None)

    @pytest.mark.asyncio
    async def test_quarantined_llm_returns_response(self):
        """Test that quarantined_llm returns a plain response dict."""
        from agent_framework.security import LabelTrackingFunctionMiddleware, quarantined_llm

        middleware = LabelTrackingFunctionMiddleware()

        # Store some untrusted content
        var_id = middleware.get_variable_store().store(
            "untrusted external data", ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )

        # Set middleware context
        middleware._set_as_current()

        try:
            result = await quarantined_llm(prompt="Summarize this data", variable_ids=[var_id])

            # Result should be a plain response dict (middleware handles hiding)
            assert "response" in result
            assert result["quarantined"] is True
            assert "auto_hidden" not in result
        finally:
            middleware._clear_current()

    @pytest.mark.asyncio
    async def test_quarantined_llm_trusted_input(self):
        """Test quarantined_llm with TRUSTED input returns response directly."""
        from agent_framework.security import LabelTrackingFunctionMiddleware, quarantined_llm

        middleware = LabelTrackingFunctionMiddleware()

        # Store TRUSTED content
        var_id = middleware.get_variable_store().store(
            "trusted system data", ContentLabel(integrity=IntegrityLabel.TRUSTED)
        )

        middleware._set_as_current()

        try:
            result = await quarantined_llm(
                prompt="Process this",
                variable_ids=[var_id],
            )

            # Result should be a plain response dict
            assert "response" in result
            assert result["quarantined"] is True
        finally:
            middleware._clear_current()

    @pytest.mark.asyncio
    async def test_quarantined_llm_multiple_variables(self):
        """Test that quarantined_llm handles multiple variables correctly."""
        from agent_framework.security import LabelTrackingFunctionMiddleware, quarantined_llm

        middleware = LabelTrackingFunctionMiddleware()

        var1 = middleware.get_variable_store().store("data1", ContentLabel(integrity=IntegrityLabel.UNTRUSTED))
        var2 = middleware.get_variable_store().store("data2", ContentLabel(integrity=IntegrityLabel.UNTRUSTED))

        middleware._set_as_current()

        try:
            result = await quarantined_llm(prompt="Compare these", variable_ids=[var1, var2])

            # Check result has expected fields
            assert result["quarantined"] is True
            assert result["variables_processed"] == [var1, var2]
        finally:
            middleware._clear_current()

    def test_quarantined_llm_declares_source_integrity(self):
        """Test that quarantined_llm declares source_integrity='untrusted'."""
        from agent_framework.security import get_security_tools

        q_llm = next(tool for tool in get_security_tools() if tool.name == "quarantined_llm")
        assert q_llm.additional_properties.get("source_integrity") == "untrusted"  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert q_llm.additional_properties.get("accepts_untrusted") is True  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]


class TestQuarantineClient:
    """Tests for quarantine chat client functionality."""

    def test_set_and_get_quarantine_client(self):
        """Test setting and getting the quarantine client."""
        from agent_framework.security import get_quarantine_client, set_quarantine_client

        # Initially should be None (or whatever state it's in)
        # Clear it first
        set_quarantine_client(None)
        assert get_quarantine_client() is None

        # Create a mock client
        class MockClient:
            async def get_response(self, messages, **kwargs):
                pass

        mock_client = MockClient()
        set_quarantine_client(mock_client)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

        assert get_quarantine_client() is mock_client

        # Clean up
        set_quarantine_client(None)
        assert get_quarantine_client() is None

    def test_secure_agent_config_sets_quarantine_client(self):
        """Test that SecureAgentConfig sets the quarantine client."""
        from agent_framework.security import SecureAgentConfig, get_quarantine_client, set_quarantine_client

        # Clear any existing client
        set_quarantine_client(None)

        # Create a mock client
        class MockClient:
            async def get_response(self, messages, **kwargs):
                pass

        mock_client = MockClient()

        # Create config with quarantine client
        config = SecureAgentConfig(quarantine_chat_client=mock_client)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]  # ty: ignore[invalid-argument-type]

        # Should have set the global client
        assert get_quarantine_client() is mock_client

        # Config should also return the client
        assert config.get_quarantine_client() is mock_client

        # Clean up
        set_quarantine_client(None)

    def test_secure_agent_config_without_quarantine_client(self):
        """Test SecureAgentConfig without quarantine client doesn't set one."""
        from agent_framework.security import SecureAgentConfig, get_quarantine_client, set_quarantine_client

        # Clear any existing client
        set_quarantine_client(None)

        # Create config without quarantine client
        config = SecureAgentConfig()

        # Global client should still be None
        assert get_quarantine_client() is None

        # Config should return None
        assert config.get_quarantine_client() is None

    @pytest.mark.asyncio
    async def test_quarantined_llm_uses_real_client_when_set(self):
        """Test that quarantined_llm uses real client when available."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework.security import (
            ContentLabel,
            IntegrityLabel,
            LabelTrackingFunctionMiddleware,
            quarantined_llm,
            set_quarantine_client,
        )

        # Clear any existing client
        set_quarantine_client(None)

        # Create a mock client that returns a response
        mock_response = MagicMock()
        mock_response.text = "This is a safe summary of the content."

        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(return_value=mock_response)

        set_quarantine_client(mock_client)

        # Set up middleware with untrusted content
        middleware = LabelTrackingFunctionMiddleware()
        var_id = middleware.get_variable_store().store(
            "Some email content with [INJECTION ATTEMPT]", ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )

        middleware._set_as_current()

        try:
            result = await quarantined_llm(prompt="Summarize this email", variable_ids=[var_id])

            # Verify the mock client was called
            mock_client.get_response.assert_called_once()

            # Check the call arguments
            call_args = mock_client.get_response.call_args
            messages = call_args.kwargs.get("messages") or call_args.args[0]
            assert len(messages) == 2  # system + user
            assert messages[0].role == "system"
            assert "quarantined" in messages[0].text.lower()
            assert messages[1].role == "user"
            assert "Summarize this email" in messages[1].text

            # Check tools=None was passed (critical for isolation)
            assert call_args.kwargs.get("tools") is None
            assert call_args.kwargs.get("client_kwargs", {}).get("tool_choice") == "none"

            # Result should be a plain response dict (middleware handles hiding)
            assert "response" in result
            assert result["response"] == "This is a safe summary of the content."

        finally:
            middleware._clear_current()
            set_quarantine_client(None)

    @pytest.mark.asyncio
    async def test_quarantined_llm_fallback_without_client(self):
        """Test that quarantined_llm falls back to placeholder without client."""
        from agent_framework.security import (
            ContentLabel,
            IntegrityLabel,
            LabelTrackingFunctionMiddleware,
            quarantined_llm,
            set_quarantine_client,
        )

        # Clear the client
        set_quarantine_client(None)

        middleware = LabelTrackingFunctionMiddleware()
        var_id = middleware.get_variable_store().store(
            "Some content",
            ContentLabel(integrity=IntegrityLabel.TRUSTED),  # Use trusted to see response directly
        )

        middleware._set_as_current()

        try:
            result = await quarantined_llm(
                prompt="Process this content",
                variable_ids=[var_id],
            )

            # Should use placeholder response
            assert "response" in result
            assert "[Quarantined LLM Response] Processed:" in result["response"]

        finally:
            middleware._clear_current()

    @pytest.mark.asyncio
    async def test_quarantined_llm_handles_client_error(self):
        """Test that quarantined_llm handles client errors gracefully."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework.security import (
            ContentLabel,
            IntegrityLabel,
            LabelTrackingFunctionMiddleware,
            quarantined_llm,
            set_quarantine_client,
        )

        # Create a mock client that raises an error
        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(side_effect=Exception("API Error"))

        set_quarantine_client(mock_client)

        middleware = LabelTrackingFunctionMiddleware()
        var_id = middleware.get_variable_store().store("Some content", ContentLabel(integrity=IntegrityLabel.TRUSTED))

        middleware._set_as_current()

        try:
            result = await quarantined_llm(prompt="Process this", variable_ids=[var_id])

            # Should fall back to error message
            assert "response" in result
            assert "[Quarantined LLM Error]" in result["response"]
            assert "API Error" in result["response"]

        finally:
            middleware._clear_current()
            set_quarantine_client(None)

    @pytest.mark.asyncio
    async def test_quarantined_llm_builds_correct_messages(self):
        """Test that quarantined_llm builds messages correctly with content."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework.security import (
            ContentLabel,
            IntegrityLabel,
            LabelTrackingFunctionMiddleware,
            quarantined_llm,
            set_quarantine_client,
        )

        mock_response = MagicMock()
        mock_response.text = "Summary"

        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(return_value=mock_response)

        set_quarantine_client(mock_client)

        middleware = LabelTrackingFunctionMiddleware()

        # Store multiple pieces of content
        var1 = middleware.get_variable_store().store(
            "Email 1: Hello world", ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        var2 = middleware.get_variable_store().store(
            {"subject": "Test", "body": "Content"},  # Dict content
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )

        middleware._set_as_current()

        try:
            await quarantined_llm(prompt="Summarize both emails", variable_ids=[var1, var2])

            # Check the user message includes both pieces of content
            call_args = mock_client.get_response.call_args
            messages = call_args.kwargs.get("messages") or call_args.args[0]
            user_message = messages[1].text

            assert "Summarize both emails" in user_message
            assert "Retrieved Content" in user_message
            assert "Email 1: Hello world" in user_message
            assert '"subject": "Test"' in user_message  # Dict should be JSON serialized

        finally:
            middleware._clear_current()
            set_quarantine_client(None)


# ========== Per-Item Embedded Label Tests ==========


class TestPerItemEmbeddedLabels:
    """Tests for per-item security labels in additional_properties."""

    @pytest.fixture
    def middleware(self):
        """Create middleware with auto-hide enabled."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=True)

    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool that returns a list."""

        class MockArgs(BaseModel):
            pass

        async def mock_fn() -> list:
            return []

        return FunctionTool(fn=mock_fn, name="fetch_items", description="Fetch items", args_schema=MockArgs)

    @pytest.mark.asyncio
    async def test_mixed_trust_items_in_list(self, middleware, mock_function):
        """Test that untrusted items are hidden while trusted items remain visible."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            # Return list[Content] with mixed trust items via additional_properties
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "content": "trusted content"}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 2, "content": "untrusted content with [INJECTION]"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 3, "content": "another trusted item"}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        assert isinstance(context.result, list)
        assert len(context.result) == 3

        # First item should be visible (trusted)
        item0 = context.result[0]
        assert isinstance(item0, Content)
        data0 = json.loads(item0.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert data0["id"] == 1
        assert data0["content"] == "trusted content"

        # Second item should be hidden (untrusted) - replaced with variable reference
        item1 = context.result[1]
        assert isinstance(item1, Content)
        assert item1.additional_properties.get("_variable_reference") is True
        parsed1 = json.loads(item1.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert parsed1.get("type") == "variable_reference"
        assert parsed1["security_label"]["integrity"] == "untrusted"

        # Third item should be visible (trusted)
        item2 = context.result[2]
        data2 = json.loads(item2.text)
        assert data2["id"] == 3

        context_label = middleware.get_context_label()
        assert context_label.integrity == IntegrityLabel.TRUSTED
        assert context_label.confidentiality == ConfidentialityLabel.PUBLIC

    @pytest.mark.asyncio
    async def test_hidden_untrusted_items_do_not_taint_integrity_in_mixed_results(self, middleware, mock_function):
        """Hidden untrusted items should only affect confidentiality, not integrity."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "content": "trusted content"}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 2, "content": "hidden private content"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "private"}},
                ),
            ]

        await middleware.process(context, next_fn)

        context_label = middleware.get_context_label()
        assert context_label.integrity == IntegrityLabel.TRUSTED
        assert context_label.confidentiality == ConfidentialityLabel.PRIVATE

    @pytest.mark.asyncio
    async def test_all_trusted_items_visible(self, middleware, mock_function):
        """Test that all trusted items remain fully visible."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "data": "safe data 1"}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 2, "data": "safe data 2"}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        assert isinstance(context.result, list)
        assert len(context.result) == 2
        # Both should be visible Content items
        data0 = json.loads(context.result[0].text)
        data1 = json.loads(context.result[1].text)
        assert data0["data"] == "safe data 1"
        assert data1["data"] == "safe data 2"

    @pytest.mark.asyncio
    async def test_all_untrusted_items_hidden(self, middleware, mock_function):
        """Test that all untrusted items are hidden."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "data": "unsafe [INJECTION]"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 2, "data": "also unsafe"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        assert isinstance(context.result, list)
        assert len(context.result) == 2
        # Both should be variable reference Content items
        for item in context.result:
            assert isinstance(item, Content)
            assert item.additional_properties.get("_variable_reference") is True
            parsed = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
            assert parsed.get("type") == "variable_reference"

    async def test_fully_hidden_result_updates_confidentiality_without_integrity_taint(
        self, middleware, mock_function
    ) -> None:
        """Hidden content affects cumulative confidentiality but not integrity."""
        context = FunctionInvocationContext(function=mock_function, arguments=mock_function.args_schema())

        async def next_fn() -> None:
            context.result = [
                Content.from_text(
                    "hidden identity data",
                    additional_properties={
                        "security_label": {
                            "integrity": "untrusted",
                            "confidentiality": "user_identity",
                        }
                    },
                )
            ]

        await middleware.process(context, next_fn)

        assert context.result[0].additional_properties["_variable_reference"] is True
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.USER_IDENTITY

    async def test_malformed_embedded_metadata_preserves_mandatory_label_fields(
        self, middleware, mock_function
    ) -> None:
        """Malformed optional metadata cannot discard integrity or confidentiality."""
        mock_function.additional_properties = {"source_integrity": "trusted"}
        context = FunctionInvocationContext(function=mock_function, arguments=mock_function.args_schema())

        async def next_fn() -> None:
            context.result = [
                Content.from_text(
                    "hidden identity data",
                    additional_properties={
                        "security_label": {
                            "integrity": "untrusted",
                            "confidentiality": "user_identity",
                            "metadata": ["malformed"],
                        }
                    },
                )
            ]

        await middleware.process(context, next_fn)

        result_label = context.metadata["result_label"]
        assert result_label.integrity == IntegrityLabel.UNTRUSTED
        assert result_label.confidentiality == ConfidentialityLabel.USER_IDENTITY
        assert result_label.metadata["source"] == "source_integrity"
        assert context.result[0].additional_properties["_variable_reference"] is True
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.USER_IDENTITY

    async def test_partial_embedded_label_uses_untrusted_fallback(self, middleware, mock_function) -> None:
        """A partial embedded label cannot promote an untrusted fallback."""
        context = FunctionInvocationContext(function=mock_function, arguments=mock_function.args_schema())

        async def next_fn() -> None:
            context.result = [
                Content.from_text(
                    "untrusted result",
                    additional_properties={
                        "security_label": {
                            "metadata": {"note": "missing mandatory fields"},
                        }
                    },
                )
            ]

        await middleware.process(context, next_fn)

        result_label = context.metadata["result_label"]
        assert result_label.integrity == IntegrityLabel.UNTRUSTED
        assert result_label.confidentiality == ConfidentialityLabel.PUBLIC
        assert context.result[0].additional_properties["_variable_reference"] is True
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED

    @pytest.mark.asyncio
    async def test_items_without_labels_use_fallback(self, middleware, mock_function):
        """Test that items without embedded labels use the fallback (call) label."""

        # Create function with source_integrity=untrusted (fallback)
        class UntrustedArgs(BaseModel):
            pass

        async def untrusted_fn() -> list:
            return []

        untrusted_function = FunctionTool(
            fn=untrusted_fn,
            name="fetch_external",
            description="Fetch external data",
            args_schema=UntrustedArgs,
            # No source_integrity = defaults to UNTRUSTED
        )

        args = untrusted_function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=untrusted_function, arguments=args)

        async def next_fn():
            # Content items without security_label in additional_properties
            context.result = [
                Content.from_text(json.dumps({"id": 1, "data": "no label here"})),
                Content.from_text(json.dumps({"id": 2, "data": "also no label"})),
            ]

        await middleware.process(context, next_fn)

        # Without embedded labels, each item is hidden individually because
        # the fallback label is UNTRUSTED (from tool's default source_integrity)
        assert isinstance(context.result, list)
        assert len(context.result) == 2
        for item in context.result:
            assert isinstance(item, Content)
            assert item.additional_properties.get("_variable_reference") is True
            parsed = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
            assert parsed.get("type") == "variable_reference"
            assert parsed["security_label"]["integrity"] == "untrusted"

        # The call/result label should be UNTRUSTED
        label = context.metadata.get("result_label")
        assert label.integrity == IntegrityLabel.UNTRUSTED  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]

    @pytest.mark.asyncio
    async def test_nested_json_in_content_item(self, middleware, mock_function):
        """Test that a Content item containing nested JSON is treated as a single unit."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            # A single Content item with nested structure and untrusted label
            nested_data = {
                "emails": [
                    {"id": 1, "body": "safe"},
                    {"id": 2, "body": "unsafe [INJECTION]"},
                ],
                "count": 2,
            }
            context.result = [
                Content.from_text(
                    json.dumps(nested_data),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        # The entire Content item is hidden as a single variable reference
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        item = context.result[0]
        assert isinstance(item, Content)
        assert item.additional_properties.get("_variable_reference") is True
        parsed = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert parsed.get("type") == "variable_reference"

    @pytest.mark.asyncio
    async def test_combined_label_reflects_all_items(self, middleware, mock_function):
        """Test that combined label is most restrictive across all items."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1}),
                    additional_properties={"security_label": {"integrity": "trusted", "confidentiality": "public"}},
                ),
                Content.from_text(
                    json.dumps({"id": 2}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "private"}},
                ),
            ]

        await middleware.process(context, next_fn)

        # Combined label should be UNTRUSTED (most restrictive integrity)
        # and PRIVATE (most restrictive confidentiality)
        label = context.metadata.get("result_label")
        assert label.integrity == IntegrityLabel.UNTRUSTED  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]
        assert label.confidentiality == ConfidentialityLabel.PRIVATE  # type: ignore[union-attr]  # ty: ignore[unresolved-attribute]

    @pytest.mark.asyncio
    async def test_hidden_items_stored_in_variable_store(self, middleware, mock_function):
        """Test that hidden items can be retrieved from the variable store."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "secret": "hidden data"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        # Get the variable reference
        assert isinstance(context.result, list)
        item = context.result[0]
        assert isinstance(item, Content)
        assert item.additional_properties.get("_variable_reference") is True
        var_ref = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert var_ref.get("type") == "variable_reference"

        # Retrieve from store
        store = middleware.get_variable_store()
        content, label = store.retrieve(var_ref["variable_id"])

        # Should have the original text content (JSON string)
        original = json.loads(content)
        assert original["id"] == 1
        assert original["secret"] == "hidden data"
        assert label.integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_auto_hide_disabled_shows_all_items(self, mock_function):
        """Test that with auto_hide_untrusted=False, all items are visible."""
        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)

        args = mock_function.args_schema()
        context = FunctionInvocationContext(function=mock_function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "data": "untrusted but visible"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        # Item should NOT be hidden even though untrusted
        assert isinstance(context.result, list)
        assert len(context.result) == 1
        item = context.result[0]
        assert isinstance(item, Content)
        data = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert data["data"] == "untrusted but visible"


# ========== Tests for Tiered Label Propagation Priority ==========


class TestTieredLabelPropagation:
    """Tests for the 3-tier label propagation priority.

    Tier 1 (Highest): Per-item embedded labels in tool result
    Tier 2: Tool's source_integrity declaration
    Tier 3 (Lowest): Join of input argument labels
    """

    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return LabelTrackingFunctionMiddleware()

    @pytest.mark.asyncio
    async def test_source_integrity_overrides_input_labels(self, middleware):
        """Test that source_integrity (tier 2) overrides input labels (tier 3).

        When a tool declares source_integrity="trusted", that declaration is
        authoritative even when input arguments carry untrusted labels.
        """

        class Args(BaseModel):
            data: dict

        async def fn(data: dict) -> str:
            return "result"

        function = FunctionTool(
            fn=fn,
            name="trusted_processor",
            description="Trusted processor",
            args_schema=Args,
            additional_properties={"source_integrity": "trusted"},
        )

        # Input has an untrusted label embedded in the argument
        args = function.args_schema(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            data={"content": "test", "security_label": {"integrity": "untrusted", "confidentiality": "public"}}
        )
        context = FunctionInvocationContext(function=function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("plain result with no embedded labels")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # Tier 2 (source_integrity=trusted) wins over tier 3 (untrusted input)
        assert label.integrity == IntegrityLabel.TRUSTED

    @pytest.mark.parametrize(
        "confidentiality",
        [ConfidentialityLabel.PRIVATE, ConfidentialityLabel.USER_IDENTITY],
    )
    async def test_hidden_input_confidentiality_propagates_to_transform_result(
        self,
        middleware: LabelTrackingFunctionMiddleware,
        confidentiality: ConfidentialityLabel,
    ) -> None:
        """A trusted transformer cannot implicitly declassify hidden input."""

        class Args(BaseModel):
            value: str

        async def transform(value: str) -> str:
            return value.upper()

        function = FunctionTool(
            fn=transform,
            name="trusted_transformer",
            description="Transform hidden input",
            args_schema=Args,
            additional_properties={"source_integrity": "trusted"},
        )
        variable_id = middleware.get_variable_store().store(
            "secret",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=confidentiality),
        )
        context = FunctionInvocationContext(
            function=function,
            arguments=Args(value=f"[{variable_id}]"),
        )

        async def next_fn() -> None:
            current_args = context.arguments
            assert isinstance(current_args, dict)
            context.result = [Content.from_text(current_args["value"].upper())]

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.TRUSTED
        assert context.metadata["result_label"].confidentiality == confidentiality
        assert middleware.get_context_label().confidentiality == confidentiality

    async def test_embedded_public_label_cannot_declassify_hidden_input(self, middleware) -> None:
        """Embedded labels choose integrity without lowering input confidentiality."""

        class Args(BaseModel):
            value: str

        async def transform(value: str) -> str:
            return value

        function = FunctionTool(
            fn=transform,
            name="embedded_label_transformer",
            description="Transform hidden input",
            args_schema=Args,
            additional_properties={"source_integrity": "untrusted"},
        )
        variable_id = middleware.get_variable_store().store(
            "private payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE),
        )
        context = FunctionInvocationContext(function=function, arguments=Args(value=f"[{variable_id}]"))

        async def next_fn() -> None:
            context.result = [
                Content.from_text(
                    "transformed",
                    additional_properties={
                        "security_label": {"integrity": "trusted", "confidentiality": "public"},
                        "_security_label_authoritative_confidentiality": True,
                    },
                )
            ]

        await middleware.process(context, next_fn)

        assert context.metadata["result_label"].integrity == IntegrityLabel.TRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert middleware.get_context_label().confidentiality == ConfidentialityLabel.PRIVATE

    @pytest.mark.asyncio
    async def test_embedded_labels_override_source_integrity(self, middleware):
        """Test that embedded labels (tier 1) override source_integrity (tier 2).

        Even when a tool declares source_integrity="trusted", per-item embedded
        labels in the result take precedence.
        """

        class Args(BaseModel):
            pass

        async def fn() -> list:
            return []

        function = FunctionTool(
            fn=fn,
            name="trusted_fetcher",
            description="Trusted fetcher",
            args_schema=Args,
            additional_properties={"source_integrity": "trusted"},
        )

        args = function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=function, arguments=args)

        async def next_fn():
            context.result = [
                Content.from_text(
                    json.dumps({"id": 1, "data": "untrusted external data"}),
                    additional_properties={"security_label": {"integrity": "untrusted", "confidentiality": "public"}},
                ),
            ]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # Tier 1 (embedded label: untrusted) wins over tier 2 (source_integrity: trusted)
        assert label.integrity == IntegrityLabel.UNTRUSTED

    @pytest.mark.asyncio
    async def test_no_source_integrity_falls_back_to_input_labels(self, middleware):
        """Test that without source_integrity, input labels (tier 3) determine the result.

        When a tool has no source_integrity declaration and the result has no
        embedded labels, the join of input argument labels is used.
        """

        class Args(BaseModel):
            data: dict

        async def fn(data: dict) -> str:
            return "result"

        # No source_integrity declared
        function = FunctionTool(
            fn=fn,
            name="generic_processor",
            description="Generic processor",
            args_schema=Args,
        )

        # Input has an untrusted label
        args = function.args_schema(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
            data={"content": "test", "security_label": {"integrity": "untrusted", "confidentiality": "public"}}
        )
        context = FunctionInvocationContext(function=function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("plain result")]

        await middleware.process(context, next_fn)

        # No source_integrity (tier 2 absent), so tier 3: join of input labels
        # Input has untrusted label → result is untrusted
        # Result should be hidden since it's untrusted
        assert isinstance(context.result, list)
        item = context.result[0]
        assert isinstance(item, Content)
        assert item.additional_properties.get("_variable_reference") is True
        parsed = json.loads(item.text)  # type: ignore[arg-type]  # pyrefly: ignore[bad-argument-type]
        assert parsed.get("type") == "variable_reference"

    @pytest.mark.asyncio
    async def test_no_labels_anywhere_defaults_untrusted(self, middleware):
        """Test that with no labels anywhere, the result defaults to UNTRUSTED.

        No source_integrity, no input labels, no embedded labels → safe default.
        """

        class Args(BaseModel):
            arg: str = "default"

        async def fn(arg: str = "default") -> str:
            return "result"

        # No source_integrity, no additional_properties
        function = FunctionTool(
            fn=fn,
            name="plain_function",
            description="Plain function",
            args_schema=Args,
        )

        args = function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=function, arguments=args)

        async def next_fn():
            context.result = [Content.from_text("plain result")]

        await middleware.process(context, next_fn)

        label = context.metadata["result_label"]
        # No source_integrity + no input labels + no embedded labels → UNTRUSTED default
        assert label.integrity == IntegrityLabel.UNTRUSTED


# ========== Tests for max_allowed_confidentiality (Data Exfiltration Prevention) ==========


class TestMaxAllowedConfidentiality:
    """Tests for max_allowed_confidentiality policy enforcement."""

    @pytest.fixture
    def label_middleware(self):
        """Create label tracking middleware."""
        return LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)

    @pytest.fixture
    def policy_middleware(self):
        """Create policy enforcement middleware."""
        return PolicyEnforcementFunctionMiddleware(block_on_violation=True)

    @pytest.fixture
    def create_function_with_max_confidentiality(self):
        """Factory to create mock function with max_allowed_confidentiality."""

        def _create(name: str, max_conf: str):
            class MockArgs(BaseModel):
                arg: str = "default"

            async def mock_fn(arg: str = "default") -> str:
                return f"result: {arg}"

            return FunctionTool(
                fn=mock_fn,
                name=name,
                description=f"Function with max_allowed_confidentiality={max_conf}",
                args_schema=MockArgs,
                additional_properties={"max_allowed_confidentiality": max_conf},
            )

        return _create

    @pytest.mark.asyncio
    async def test_public_data_allowed_to_public_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PUBLIC data can be written to PUBLIC destination."""
        # Context is PUBLIC
        label_middleware._update_context_label(
            ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.PUBLIC)
        )

        function = create_function_with_max_confidentiality("send_public", "public")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "sent"

        await policy_middleware.process(context, next_fn)

        # Should be allowed
        assert context.result == "sent"

    @pytest.mark.asyncio
    async def test_private_data_blocked_from_public_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PRIVATE data cannot be written to PUBLIC destination (data exfiltration blocked)."""
        # Context contains PRIVATE data
        label_middleware._update_context_label(
            ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)
        )

        function = create_function_with_max_confidentiality("send_to_public", "public")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "should not reach"

        with pytest.raises(MiddlewareTermination):
            await policy_middleware.process(context, next_fn)

        # Should be blocked
        assert "error" in context.result
        assert "exfiltration" in context.result["error"].lower()

    @pytest.mark.asyncio
    async def test_user_identity_data_blocked_from_private_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test USER_IDENTITY data cannot be written to PRIVATE destination."""
        # Context contains USER_IDENTITY data
        label_middleware._update_context_label(
            ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.USER_IDENTITY)
        )

        function = create_function_with_max_confidentiality("send_to_private", "private")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "should not reach"

        with pytest.raises(MiddlewareTermination):
            await policy_middleware.process(context, next_fn)

        # Should be blocked
        assert "error" in context.result

    @pytest.mark.asyncio
    async def test_private_data_allowed_to_private_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PRIVATE data can be written to PRIVATE destination."""
        # Context contains PRIVATE data
        label_middleware._update_context_label(
            ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)
        )

        function = create_function_with_max_confidentiality("send_to_private", "private")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "sent to private"

        await policy_middleware.process(context, next_fn)

        # Should be allowed
        assert context.result == "sent to private"

    @pytest.mark.asyncio
    async def test_combined_integrity_and_confidentiality_violation(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test that both integrity AND confidentiality violations are detected."""
        # Context is UNTRUSTED + PRIVATE
        label_middleware._update_context_label(
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PRIVATE)
        )

        # Tool requires trusted context AND is a public destination
        class MockArgs(BaseModel):
            arg: str = "default"

        async def mock_fn(arg: str = "default") -> str:
            return f"result: {arg}"

        function = FunctionTool(
            fn=mock_fn,
            name="restricted_public_tool",
            description="Requires trusted, public-only destination",
            args_schema=MockArgs,
            additional_properties={
                "accepts_untrusted": False,  # Rejects untrusted context
                "max_allowed_confidentiality": "public",  # Rejects private data
            },
        )

        args = function.args_schema()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        context = FunctionInvocationContext(function=function, arguments=args)

        context.metadata["context_label"] = label_middleware.get_context_label()

        async def next_fn():
            context.result = "should not reach"

        with pytest.raises(MiddlewareTermination):
            await policy_middleware.process(context, next_fn)

        # Should be blocked (either violation should block)
        assert "error" in context.result


class TestCheckConfidentialityAllowed:
    """Tests for check_confidentiality_allowed helper function."""

    def test_public_to_public_allowed(self):
        """Test PUBLIC data can be written to PUBLIC destination."""
        from agent_framework.security import check_confidentiality_allowed

        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PUBLIC) is True

    def test_public_to_private_allowed(self):
        """Test PUBLIC data can be written to PRIVATE destination."""
        from agent_framework.security import check_confidentiality_allowed

        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PRIVATE) is True

    def test_public_to_user_identity_allowed(self):
        """Test PUBLIC data can be written to USER_IDENTITY destination."""
        from agent_framework.security import check_confidentiality_allowed

        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.USER_IDENTITY) is True

    def test_private_to_public_blocked(self):
        """Test PRIVATE data cannot be written to PUBLIC destination."""
        from agent_framework.security import check_confidentiality_allowed

        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PUBLIC) is False

    def test_private_to_private_allowed(self):
        """Test PRIVATE data can be written to PRIVATE destination."""
        from agent_framework.security import check_confidentiality_allowed

        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PRIVATE) is True

    def test_private_to_user_identity_allowed(self):
        """Test PRIVATE data can be written to USER_IDENTITY destination."""
        from agent_framework.security import check_confidentiality_allowed

        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.USER_IDENTITY) is True

    def test_user_identity_to_public_blocked(self):
        """Test USER_IDENTITY data cannot be written to PUBLIC destination."""
        from agent_framework.security import check_confidentiality_allowed

        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.PUBLIC) is False

    def test_user_identity_to_private_blocked(self):
        """Test USER_IDENTITY data cannot be written to PRIVATE destination."""
        from agent_framework.security import check_confidentiality_allowed

        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.PRIVATE) is False

    def test_user_identity_to_user_identity_allowed(self):
        """Test USER_IDENTITY data can be written to USER_IDENTITY destination."""
        from agent_framework.security import check_confidentiality_allowed

        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.USER_IDENTITY) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# MCP annotation mapping
# ---------------------------------------------------------------------------


class TestMCPAnnotationMapping:
    """Tests for hint-based mapping from MCP annotations to FIDES labels."""

    @pytest.mark.parametrize(
        ("read_only", "open_world", "default_integrity", "expected_integrity", "expected_max_conf", "expected_accepts"),
        [
            (
                True,
                None,
                IntegrityLabel.UNTRUSTED,
                IntegrityLabel.UNTRUSTED,
                ConfidentialityLabel.PUBLIC,
                False,
            ),
            (True, True, IntegrityLabel.TRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (True, False, IntegrityLabel.UNTRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (False, None, IntegrityLabel.UNTRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (False, True, IntegrityLabel.TRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (False, False, IntegrityLabel.UNTRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (None, None, IntegrityLabel.UNTRUSTED, IntegrityLabel.UNTRUSTED, ConfidentialityLabel.PUBLIC, False),
            (None, None, IntegrityLabel.TRUSTED, IntegrityLabel.TRUSTED, ConfidentialityLabel.PUBLIC, False),
        ],
    )
    def test_map_mcp_annotations_to_labels(
        self,
        read_only,
        open_world,
        default_integrity,
        expected_integrity,
        expected_max_conf,
        expected_accepts,
    ):
        from agent_framework.security import _map_mcp_annotations_to_labels

        annotations = None
        if read_only is not None or open_world is not None:
            annotations = SimpleNamespace(readOnlyHint=read_only, openWorldHint=open_world)

        integrity, max_conf, accepts_untrusted = _map_mcp_annotations_to_labels(
            annotations,
            default_integrity=default_integrity,
        )

        assert integrity == expected_integrity
        assert max_conf == expected_max_conf
        assert accepts_untrusted is expected_accepts

    def test_map_missing_annotations_defaults_to_sink(self):
        from agent_framework.security import _map_mcp_annotations_to_labels

        integrity, max_conf, accepts_untrusted = _map_mcp_annotations_to_labels(None)
        assert integrity == IntegrityLabel.UNTRUSTED
        assert max_conf == ConfidentialityLabel.PUBLIC
        assert accepts_untrusted is False


def _make_connected_mcp_tool_for_ifc(
    *,
    annotations: Any,
    server_meta: dict[str, Any],
    confidentiality: ConfidentialityLabel = ConfidentialityLabel.PRIVATE,
) -> tuple[Any, FunctionTool]:
    from agent_framework._mcp import MCPTool

    async def fake_call(**kwargs: Any) -> list[Content]:
        return [Content.from_text("payload", additional_properties={"_meta": server_meta})]

    function = FunctionTool(
        func=fake_call,
        name="remote_tool",
        description="",
        additional_properties={
            "_mcp_remote_name": "remote_tool",
            "confidentiality": confidentiality.value,
        },
    )
    mcp_tool = MCPTool(name="helper")  # type: ignore[abstract]
    mcp_tool.is_connected = True
    mcp_tool.session = AsyncMock()
    mcp_tool.session.list_tools = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(
            tools=[SimpleNamespace(name="remote_tool", annotations=annotations)],
            nextCursor=None,
        )
    )
    mcp_tool.functions.append(function)
    return mcp_tool, function


# ---------------------------------------------------------------------------
# IFC labels from MCP _meta payload
# ---------------------------------------------------------------------------


class TestMCPIFCMetaLabels:
    """Tests for parsing per-call IFC labels from MCP ``_meta`` payloads.

    Covers:
      * ``_label_from_mcp_meta`` parsing (well-formed, missing, malformed).
      * ``MCPTool._parse_tool_result_from_mcp`` propagating ``_meta`` onto
                every Content via the ``_meta`` key.
      * ``_stamp_mcp_content_labels`` combining server labels with local policy
        and falling back when the server omits/misformats ``_meta.ifc``.
      * ``SecureMCPToolProxy`` wrapping each ``FunctionTool`` so an MCP tool
        result carries a per-item ``security_label`` that remote metadata can
        restrict but cannot relax.
    """

    def test_label_from_meta_well_formed(self):
        from agent_framework.security import _label_from_mcp_meta

        label = _label_from_mcp_meta({"ifc": {"integrity": "untrusted", "confidentiality": "private"}})
        assert label is not None
        assert label.integrity == IntegrityLabel.UNTRUSTED
        assert label.confidentiality == ConfidentialityLabel.PRIVATE

    def test_label_from_meta_trusted_public(self):
        from agent_framework.security import _label_from_mcp_meta

        label = _label_from_mcp_meta({"ifc": {"integrity": "trusted", "confidentiality": "public"}})
        assert label is not None
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PUBLIC

    @pytest.mark.parametrize(
        "meta",
        [
            None,
            {},
            {"ifc": None},
            {"ifc": "trusted"},
            {"ifc": {}},
            {"ifc": {"integrity": "trusted"}},  # missing confidentiality
            {"ifc": {"integrity": "garbage", "confidentiality": "public"}},
            {"ifc": {"integrity": "trusted", "confidentiality": "garbage"}},
            {"other_key": {"integrity": "trusted", "confidentiality": "public"}},  # non-ifc key
        ],
    )
    def test_label_from_meta_invalid_returns_none(self, meta):
        from agent_framework.security import _label_from_mcp_meta

        assert _label_from_mcp_meta(meta) is None

    def test_parse_tool_result_propagates_meta(self):
        """``_parse_tool_result_from_mcp`` stamps ``_meta`` on each Content."""
        from mcp import types as mcp_types

        from agent_framework._mcp import MCPTool

        class _ConcreteMCPTool(MCPTool):
            def get_mcp_client(self):
                raise NotImplementedError

        helper = _ConcreteMCPTool(name="helper")
        mcp_result = mcp_types.CallToolResult(
            content=[
                mcp_types.TextContent(type="text", text="first"),
                mcp_types.TextContent(type="text", text="second"),
            ],
            _meta={"ifc": {"integrity": "untrusted", "confidentiality": "public"}, "tracing": {"span": "abc"}},
        )
        contents = helper._parse_tool_result_from_mcp(mcp_result)
        assert len(contents) == 2
        for c in contents:
            meta = c.additional_properties.get("_meta")
            assert meta == {
                "ifc": {"integrity": "untrusted", "confidentiality": "public"},
                "tracing": {"span": "abc"},
            }

    def test_parse_tool_result_without_meta_has_no_sentinel(self):
        from mcp import types as mcp_types

        from agent_framework._mcp import MCPTool

        class _ConcreteMCPTool(MCPTool):
            def get_mcp_client(self):
                raise NotImplementedError

        helper = _ConcreteMCPTool(name="helper")
        mcp_result = mcp_types.CallToolResult(content=[mcp_types.TextContent(type="text", text="hi")])
        contents = helper._parse_tool_result_from_mcp(mcp_result)
        assert "_meta" not in contents[0].additional_properties

    @pytest.mark.parametrize("trust_server_ifc", [False, True], ids=["restricted", "authoritative"])
    def test_stamp_contents_complete_local_and_remote_label_matrix(self, trust_server_ifc: bool):
        from agent_framework.security import _stamp_mcp_content_labels

        integrity_labels = (
            IntegrityLabel.TRUSTED,
            IntegrityLabel.UNTRUSTED,
        )
        confidentiality_labels = (
            ConfidentialityLabel.PUBLIC,
            ConfidentialityLabel.PRIVATE,
            ConfidentialityLabel.USER_IDENTITY,
        )
        confidentiality_rank = {
            ConfidentialityLabel.PUBLIC: 0,
            ConfidentialityLabel.PRIVATE: 1,
            ConfidentialityLabel.USER_IDENTITY: 2,
        }
        for local_integrity in integrity_labels:
            for local_confidentiality in confidentiality_labels:
                for remote_integrity in integrity_labels:
                    for remote_confidentiality in confidentiality_labels:
                        static = ContentLabel(
                            integrity=local_integrity,
                            confidentiality=local_confidentiality,
                            metadata={"source": "local_mcp_policy"},
                        )
                        contents = [
                            Content.from_text(
                                "x",
                                additional_properties={
                                    "_meta": {
                                        "ifc": {
                                            "integrity": remote_integrity.value,
                                            "confidentiality": remote_confidentiality.value,
                                            "metadata": {"source": "forged_remote_policy"},
                                        }
                                    }
                                },
                            )
                        ]

                        _stamp_mcp_content_labels(contents, static, trust_server_ifc=trust_server_ifc)

                        if trust_server_ifc:
                            expected_integrity = remote_integrity
                            expected_confidentiality = remote_confidentiality
                            expected_metadata: dict[str, Any] | None = None
                        else:
                            expected_integrity = (
                                IntegrityLabel.UNTRUSTED
                                if IntegrityLabel.UNTRUSTED in (local_integrity, remote_integrity)
                                else IntegrityLabel.TRUSTED
                            )
                            expected_confidentiality = max(
                                (local_confidentiality, remote_confidentiality), key=confidentiality_rank.__getitem__
                            )
                            expected_metadata = {"source": "local_mcp_policy"}
                        assert contents[0].additional_properties["security_label"] == {
                            "integrity": expected_integrity.value,
                            "confidentiality": expected_confidentiality.value,
                            **({"metadata": expected_metadata} if expected_metadata is not None else {}),
                        }
                        assert "_meta" not in contents[0].additional_properties

    @pytest.mark.parametrize(
        "confidentiality",
        [ConfidentialityLabel.PRIVATE, ConfidentialityLabel.USER_IDENTITY],
    )
    @pytest.mark.parametrize("trust_server_ifc", [False, True])
    def test_stamp_contents_missing_meta_falls_back_to_local_policy(
        self, confidentiality: ConfidentialityLabel, trust_server_ifc: bool
    ):
        from agent_framework.security import _stamp_mcp_content_labels

        static = ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=confidentiality)
        contents = [Content.from_text("x")]
        _stamp_mcp_content_labels(contents, static, trust_server_ifc=trust_server_ifc)
        assert contents[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": confidentiality.value,
        }

    @pytest.mark.parametrize(
        "server_meta",
        [
            {"ifc": {"integrity": "bogus", "confidentiality": "public"}},
            {"ifc": {"integrity": "trusted"}},
        ],
        ids=["malformed", "partial"],
    )
    @pytest.mark.parametrize("trust_server_ifc", [False, True])
    def test_stamp_contents_invalid_meta_falls_back_to_local_policy(
        self, server_meta: dict[str, Any], trust_server_ifc: bool
    ):
        from agent_framework.security import _stamp_mcp_content_labels

        static = ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.PUBLIC)
        contents = [
            Content.from_text(
                "x",
                additional_properties={"_meta": server_meta},
            )
        ]
        _stamp_mcp_content_labels(contents, static, trust_server_ifc=trust_server_ifc)
        assert contents[0].additional_properties["security_label"] == {
            "integrity": "trusted",
            "confidentiality": "public",
        }
        assert "_meta" not in contents[0].additional_properties

    def test_stamp_contents_non_ifc_meta_falls_back_to_static(self):
        """Generic ``_meta`` keys unrelated to IFC don't accidentally produce a label."""
        from agent_framework.security import _stamp_mcp_content_labels

        static = ContentLabel(integrity=IntegrityLabel.UNTRUSTED, confidentiality=ConfidentialityLabel.PUBLIC)
        contents = [
            Content.from_text(
                "x",
                additional_properties={"_meta": {"tracing": {"span": "abc"}}},
            )
        ]
        _stamp_mcp_content_labels(contents, static)
        assert contents[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": "public",
        }

    def test_stamp_contents_multi_item_all_stamped(self):
        from agent_framework.security import _stamp_mcp_content_labels

        static = ContentLabel(integrity=IntegrityLabel.TRUSTED, confidentiality=ConfidentialityLabel.PUBLIC)
        meta = {"_meta": {"ifc": {"integrity": "untrusted", "confidentiality": "public"}}}
        contents = [Content.from_text(str(i), additional_properties=dict(meta)) for i in range(3)]
        _stamp_mcp_content_labels(contents, static)
        for c in contents:
            assert c.additional_properties["security_label"] == {
                "integrity": "untrusted",
                "confidentiality": "public",
            }

    async def test_wrap_mcp_function_remote_label_can_restrict_local_policy(self):
        """End-to-end: remote metadata can make the locally derived label stricter."""
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs):
            return [
                Content.from_text(
                    "payload",
                    additional_properties={"_meta": {"ifc": {"integrity": "untrusted", "confidentiality": "private"}}},
                )
            ]

        func_tool = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={
                "source_integrity": "trusted",
                "max_allowed_confidentiality": "public",
                "_mcp_remote_name": "remote_tool",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is not None
        result = await func_tool.func()
        assert isinstance(result, list)
        assert result[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": "private",
        }
        # Static policy was trusted+public; remote metadata restricted both dimensions.

    async def test_wrap_mcp_function_static_fallback(self):
        """When the server omits ``_meta``, the static label is used."""
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs):
            return [Content.from_text("payload")]

        func_tool = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={
                "source_integrity": "untrusted",
                "max_allowed_confidentiality": "public",
                "_mcp_remote_name": "remote_tool",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is not None
        result = await func_tool.func()
        assert result[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": "public",
        }

    @pytest.mark.parametrize("confidentiality", [ConfidentialityLabel.PRIVATE, ConfidentialityLabel.USER_IDENTITY])
    async def test_wrap_mcp_function_remote_label_cannot_relax_local_policy(
        self, confidentiality: ConfidentialityLabel
    ):
        """Remote MCP metadata cannot raise integrity or lower confidentiality."""
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs):
            return [
                Content.from_text(
                    "wrote item",
                    additional_properties={"_meta": {"ifc": {"integrity": "trusted", "confidentiality": "public"}}},
                )
            ]

        func_tool = FunctionTool(
            func=fake_call,
            name="create_issue",
            description="",
            additional_properties={
                "source_integrity": "untrusted",
                "confidentiality": confidentiality.value,
                "max_allowed_confidentiality": "public",
                "accepts_untrusted": False,
                "_mcp_remote_name": "create_issue",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is not None
        result = await func_tool.func()
        assert result[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": confidentiality.value,
        }

    async def test_wrap_mcp_function_ignores_sink_confidentiality_for_public_output(self):
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs: Any) -> list[Content]:
            return [
                Content.from_text(
                    "payload",
                    additional_properties={"_meta": {"ifc": {"integrity": "trusted", "confidentiality": "public"}}},
                )
            ]

        func_tool = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={
                "source_integrity": "trusted",
                "max_allowed_confidentiality": "private",
                "_mcp_remote_name": "remote_tool",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is not None

        result = await func_tool.func()

        assert result[0].additional_properties["security_label"] == {
            "integrity": "trusted",
            "confidentiality": "public",
        }

    async def test_wrap_mcp_function_reads_refreshed_local_policy_at_invocation(self):
        from agent_framework.security import SecureMCPToolProxy

        trusted_annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        untrusted_annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=True)
        server_meta = {"ifc": {"integrity": "trusted", "confidentiality": "public"}}
        mcp_tool, function = _make_connected_mcp_tool_for_ifc(
            annotations=trusted_annotations,
            server_meta=server_meta,
            confidentiality=ConfidentialityLabel.PUBLIC,
        )
        mcp_tool.session.list_tools.side_effect = [
            SimpleNamespace(
                tools=[SimpleNamespace(name="remote_tool", annotations=trusted_annotations)], nextCursor=None
            ),
            SimpleNamespace(
                tools=[SimpleNamespace(name="remote_tool", annotations=untrusted_annotations)], nextCursor=None
            ),
        ]
        proxy = SecureMCPToolProxy(mcp_tool, default_integrity=IntegrityLabel.TRUSTED)

        await proxy.refresh_labels()
        props = function.additional_properties
        assert props is not None
        assert props["source_integrity"] == "trusted"
        await proxy.refresh_labels()
        assert props["source_integrity"] == "untrusted"
        assert function.func is not None
        result = await function.func()

        assert result[0].additional_properties["security_label"] == {
            "integrity": "untrusted",
            "confidentiality": "public",
        }

    @pytest.mark.parametrize(
        ("start_properties", "refreshed_properties", "first_label", "second_label"),
        [
            (
                {
                    "source_integrity": "trusted",
                    "confidentiality": "public",
                    "_mcp_trust_server_ifc": False,
                },
                {
                    "source_integrity": "untrusted",
                    "confidentiality": "private",
                    "_mcp_trust_server_ifc": False,
                },
                {"integrity": "trusted", "confidentiality": "public"},
                {"integrity": "untrusted", "confidentiality": "private"},
            ),
            (
                {
                    "source_integrity": "untrusted",
                    "confidentiality": "private",
                    "_mcp_trust_server_ifc": True,
                },
                {
                    "source_integrity": "untrusted",
                    "confidentiality": "private",
                    "_mcp_trust_server_ifc": False,
                },
                {"integrity": "trusted", "confidentiality": "public"},
                {"integrity": "untrusted", "confidentiality": "private"},
            ),
        ],
        ids=["stricter-local-policy", "revoke-server-authority"],
    )
    async def test_wrap_mcp_function_snapshots_policy_for_in_flight_call(
        self,
        start_properties: dict[str, Any],
        refreshed_properties: dict[str, Any],
        first_label: dict[str, str],
        second_label: dict[str, str],
    ):
        from agent_framework.security import _wrap_mcp_function_for_ifc

        call_started = asyncio.Event()
        release_call = asyncio.Event()

        async def fake_call(**kwargs: Any) -> list[Content]:
            call_started.set()
            await release_call.wait()
            return [
                Content.from_text(
                    "payload",
                    additional_properties={"_meta": {"ifc": {"integrity": "trusted", "confidentiality": "public"}}},
                )
            ]

        function = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={"_mcp_remote_name": "remote_tool", **start_properties},
        )
        _wrap_mcp_function_for_ifc(function, IntegrityLabel.UNTRUSTED)
        assert function.func is not None

        first_call = asyncio.create_task(function.func())
        await call_started.wait()
        assert function.additional_properties is not None
        function.additional_properties.update(refreshed_properties)
        release_call.set()

        first_result = await first_call
        second_result = await function.func()

        assert first_result[0].additional_properties["security_label"] == first_label
        assert second_result[0].additional_properties["security_label"] == second_label

    @pytest.mark.parametrize("trust_server_ifc", [False, True], ids=["default", "trusted"])
    async def test_apply_mcp_security_labels_configures_result_authority(self, trust_server_ifc: bool):
        from agent_framework.security import apply_mcp_security_labels

        annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        server_meta = {
            "ifc": {"integrity": "trusted", "confidentiality": "public"},
            "_mcp_trust_server_ifc": True,
        }
        mcp_tool, function = _make_connected_mcp_tool_for_ifc(annotations=annotations, server_meta=server_meta)

        if trust_server_ifc:
            await apply_mcp_security_labels(mcp_tool, trust_server_ifc=True)
        else:
            await apply_mcp_security_labels(mcp_tool)

        props = function.additional_properties
        assert props is not None
        assert props["source_integrity"] == "untrusted"
        assert props["max_allowed_confidentiality"] == "public"
        assert props["accepts_untrusted"] is False
        assert props["_mcp_trust_server_ifc"] is trust_server_ifc
        assert function.func is not None
        result = await function.func()
        expected_label = (
            {"integrity": "trusted", "confidentiality": "public"}
            if trust_server_ifc
            else {"integrity": "untrusted", "confidentiality": "private"}
        )
        assert result[0].additional_properties["security_label"] == expected_label

    async def test_apply_mcp_security_labels_reconfigures_existing_wrapper_authority(self):
        from agent_framework.security import apply_mcp_security_labels

        annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        server_meta = {"ifc": {"integrity": "trusted", "confidentiality": "public"}}
        mcp_tool, function = _make_connected_mcp_tool_for_ifc(annotations=annotations, server_meta=server_meta)
        await apply_mcp_security_labels(mcp_tool)
        wrapped = function.func
        props = function.additional_properties
        assert props is not None
        assert props["max_allowed_confidentiality"] == "public"

        await apply_mcp_security_labels(mcp_tool, mark_write_tools_as_sinks=False, trust_server_ifc=True)

        assert function.func is wrapped
        assert "max_allowed_confidentiality" not in props
        assert function.func is not None
        result = await function.func()
        assert result[0].additional_properties["security_label"] == {
            "integrity": "trusted",
            "confidentiality": "public",
        }

    @pytest.mark.parametrize("trust_server_ifc", [False, True], ids=["default", "trusted"])
    async def test_secure_mcp_proxy_configures_result_authority(self, trust_server_ifc: bool):
        from agent_framework.security import SecureMCPToolProxy

        annotations = SimpleNamespace(readOnlyHint=True, openWorldHint=False)
        server_meta = {"ifc": {"integrity": "trusted", "confidentiality": "public"}}
        mcp_tool, function = _make_connected_mcp_tool_for_ifc(annotations=annotations, server_meta=server_meta)
        proxy = (
            SecureMCPToolProxy(mcp_tool, trust_server_ifc=True) if trust_server_ifc else SecureMCPToolProxy(mcp_tool)
        )

        await proxy.refresh_labels()

        props = function.additional_properties
        assert props is not None
        assert props["source_integrity"] == "untrusted"
        assert props["max_allowed_confidentiality"] == "public"
        assert props["accepts_untrusted"] is False
        assert props["_mcp_trust_server_ifc"] is trust_server_ifc
        assert function.func is not None
        result = await function.func()
        expected_label = (
            {"integrity": "trusted", "confidentiality": "public"}
            if trust_server_ifc
            else {"integrity": "untrusted", "confidentiality": "private"}
        )
        assert result[0].additional_properties["security_label"] == expected_label

    async def test_wrap_mcp_function_str_result_passes_through(self):
        """``str`` results (no per-item containers) are not modified by the wrapper."""
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs):
            return "plain string result"

        func_tool = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={
                "source_integrity": "trusted",
                "max_allowed_confidentiality": "public",
                "_mcp_remote_name": "remote_tool",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is not None
        result = await func_tool.func()
        assert result == "plain string result"

    async def test_wrap_mcp_function_is_idempotent(self):
        """Re-running ``_wrap_mcp_function_for_ifc`` (e.g. reconnect) does not double-wrap."""
        from agent_framework.security import _wrap_mcp_function_for_ifc

        async def fake_call(**kwargs):
            return [Content.from_text("x")]

        func_tool = FunctionTool(
            func=fake_call,
            name="remote_tool",
            description="",
            additional_properties={
                "source_integrity": "untrusted",
                "max_allowed_confidentiality": "public",
                "_mcp_remote_name": "remote_tool",
            },
        )
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        wrapped_once = func_tool.func
        _wrap_mcp_function_for_ifc(func_tool, IntegrityLabel.UNTRUSTED)
        assert func_tool.func is wrapped_once


async def _hide_session_value(
    tracker: LabelTrackingFunctionMiddleware,
    policy: PolicyEnforcementFunctionMiddleware,
    session: AgentSession,
    value: str,
) -> str:
    """Hide one untrusted result through the public middleware pipeline."""

    class SourceArgs(BaseModel):
        value: str

    async def source(value: str) -> str:
        return value

    source_tool = FunctionTool(
        func=source,
        name="source",
        description="Return untrusted data",
        input_model=SourceArgs,
        additional_properties={"source_integrity": "untrusted"},
    )
    context = FunctionInvocationContext(function=source_tool, arguments={"value": value}, session=session)

    async def execute(_context: FunctionInvocationContext) -> list[Content]:
        return [Content.from_text(value)]

    await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)
    result = cast(list[Content], context.result)
    assert result[0].text is not None
    return cast(str, json.loads(result[0].text)["variable_id"])


class TestManualSecuritySessionSelection:
    """Manual middleware wiring must select explicit session state safely."""

    @staticmethod
    def _sink() -> FunctionTool:
        class SinkArgs(BaseModel):
            value: str

        async def sink(value: str) -> str:
            return value

        return FunctionTool(
            func=sink,
            name="sink",
            description="Forward hidden data",
            input_model=SinkArgs,
            additional_properties={"accepts_untrusted": True, "source_integrity": "trusted"},
        )

    async def test_shared_middleware_selects_explicit_sessions_a_b_a(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        alice = AgentSession(session_id="alice")
        bob = AgentSession(session_id="bob")
        alice_variable = await _hide_session_value(tracker, policy, alice, "alice secret")
        bob_variable = await _hide_session_value(tracker, policy, bob, "bob secret")
        sink = self._sink()
        received: list[tuple[str, str]] = []

        async def forward(session: AgentSession, variable_id: str) -> None:
            context = FunctionInvocationContext(
                function=sink,
                arguments={"value": f"[{variable_id}]"},
                session=session,
            )

            async def execute(current: FunctionInvocationContext) -> list[Content]:
                value = cast(dict[str, Any], current.arguments)["value"]
                received.append((session.session_id, cast(str, value)))
                return [Content.from_text("sent")]

            await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)

        await forward(bob, alice_variable)
        await forward(alice, alice_variable)
        await forward(alice, bob_variable)
        await forward(bob, bob_variable)
        await forward(alice, alice_variable)

        assert received == [
            ("bob", f"[{alice_variable}]"),
            ("alice", "alice secret"),
            ("alice", f"[{bob_variable}]"),
            ("bob", "bob secret"),
            ("alice", "alice secret"),
        ]

    async def test_overlapping_sessions_keep_task_local_variable_scope(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        alice = AgentSession(session_id="alice-overlap")
        bob = AgentSession(session_id="bob-overlap")
        alice_variable = await _hide_session_value(tracker, policy, alice, "alice secret")
        bob_variable = await _hide_session_value(tracker, policy, bob, "bob secret")
        inspect_tool = next(tool for tool in tracker.get_security_tools() if tool.name == "inspect_variable")
        both_started = asyncio.Event()
        started = 0

        async def inspect(session: AgentSession, variable_id: str) -> str:
            nonlocal started
            context = FunctionInvocationContext(
                function=inspect_tool,
                arguments={"variable_id": variable_id, "reason": "overlap isolation"},
                session=session,
            )

            async def execute(current: FunctionInvocationContext) -> list[Content]:
                nonlocal started
                started += 1
                if started == 2:
                    both_started.set()
                await both_started.wait()
                await asyncio.sleep(0)
                assert get_current_middleware() is tracker
                return await inspect_tool.invoke(arguments=current.arguments, context=current)

            await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)
            result = cast(list[Content], context.result)
            assert result[0].text is not None
            return cast(str, json.loads(result[0].text)["content"])

        assert await asyncio.gather(
            inspect(alice, alice_variable),
            inspect(bob, bob_variable),
        ) == ["alice secret", "bob secret"]
        assert get_current_middleware() is None

    async def test_direct_standalone_invocation_keeps_private_scope(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        variable_id = tracker.get_variable_store().store(
            "standalone secret",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink = self._sink()
        received: list[str] = []
        context = FunctionInvocationContext(function=sink, arguments={"value": f"[{variable_id}]"})

        async def execute(current: FunctionInvocationContext) -> list[Content]:
            received.append(cast(str, cast(dict[str, Any], current.arguments)["value"]))
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)

        assert received == ["standalone secret"]
        assert tracker.get_variable_store().retrieve(variable_id)[0] == "standalone secret"


class TestVariableArgumentPolicy:
    """Expanded hidden values retain their labels for policy enforcement."""

    @staticmethod
    def _sink(
        *,
        accepts_untrusted: bool,
        max_confidentiality: str = "private",
    ) -> FunctionTool:
        class SinkArgs(BaseModel):
            value: Any

        async def sink(value: Any) -> str:
            return str(value)

        return FunctionTool(
            func=sink,
            name="sink",
            description="Forward hidden data",
            input_model=SinkArgs,
            additional_properties={
                "accepts_untrusted": accepts_untrusted,
                "max_allowed_confidentiality": max_confidentiality,
                "source_integrity": "trusted",
            },
        )

    @pytest.mark.parametrize(
        ("make_value", "expected"),
        [
            pytest.param(lambda variable_id: f"[{variable_id}]", "payload", id="bracketed"),
            pytest.param(lambda variable_id: f"  [ {variable_id} ]  ", "payload", id="whitespace"),
            pytest.param(lambda variable_id: variable_id, "payload", id="bare"),
            pytest.param(lambda variable_id: f"prefix [{variable_id}] suffix", "prefix payload suffix", id="embedded"),
            pytest.param(lambda variable_id: f"[{variable_id}]/[{variable_id}]", "payload/payload", id="duplicate"),
            pytest.param(lambda variable_id: [f"[{variable_id}]", variable_id], ["payload", "payload"], id="list"),
            pytest.param(lambda variable_id: {"item": f"[{variable_id}]"}, {"item": "payload"}, id="mapping"),
            pytest.param(
                lambda variable_id: {"outer": [{"inner": f"value=[{variable_id}]"}]},
                {"outer": [{"inner": "value=payload"}]},
                id="deep",
            ),
        ],
    )
    async def test_all_reference_forms_resolve_and_block_untrusted_arguments(
        self,
        make_value: Any,
        expected: Any,
    ) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        variable_id = tracker.get_variable_store().store(
            "payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        value = make_value(variable_id)
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=False),
            arguments={"value": value},
        )

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                context,
                lambda _context: pytest.fail("Blocked tool must not execute"),
            )

        assert cast(dict[str, Any], context.arguments)["value"] == expected
        assert cast(dict[str, Any], context.metadata["original_arguments_for_messages"])["value"] == value
        assert context.metadata["argument_label"].integrity == IntegrityLabel.UNTRUSTED
        assert policy.get_audit_log()[-1]["type"] == "untrusted_arguments"

    @pytest.mark.parametrize("value", ["[var_0123456789abcdef]", "var_0123456789abcdef"])
    async def test_unknown_references_remain_literal(self, value: str) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        received: list[str] = []
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=False),
            arguments={"value": value},
        )

        async def execute(current: FunctionInvocationContext) -> list[Content]:
            received.append(cast(str, cast(dict[str, Any], current.arguments)["value"]))
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)

        assert received == [value]
        argument_label = cast(ContentLabel, context.metadata["argument_label"])
        assert argument_label.integrity == IntegrityLabel.TRUSTED
        assert argument_label.confidentiality == ConfidentialityLabel.PUBLIC

    async def test_accepts_untrusted_blind_forwards_without_model_context_taint(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        variable_id = tracker.get_variable_store().store(
            "payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        received: list[str] = []
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=True),
            arguments={"value": f"[{variable_id}]"},
        )

        async def execute(current: FunctionInvocationContext) -> list[Content]:
            received.append(cast(str, cast(dict[str, Any], current.arguments)["value"]))
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)

        assert received == ["payload"]
        assert context.metadata["argument_label"].integrity == IntegrityLabel.UNTRUSTED
        assert tracker.get_context_label().integrity == IntegrityLabel.TRUSTED

    async def test_private_hidden_argument_is_blocked_from_public_sink(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        variable_id = tracker.get_variable_store().store(
            "private payload",
            ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.PRIVATE,
            ),
        )
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=True, max_confidentiality="public"),
            arguments={"value": f"[{variable_id}]"},
        )

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                context,
                lambda _context: pytest.fail("Confidential value must not reach a public sink"),
            )

        assert context.metadata["effective_invocation_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert policy.get_audit_log()[-1]["subtype"] == "max_allowed_confidentiality"

    async def test_argument_labels_preserve_result_confidentiality(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware()
        variable_id = tracker.get_variable_store().store(
            "private payload",
            ContentLabel(
                integrity=IntegrityLabel.UNTRUSTED,
                confidentiality=ConfidentialityLabel.PRIVATE,
            ),
        )
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=True),
            arguments={"value": f"[{variable_id}]"},
        )

        async def execute(_context: FunctionInvocationContext) -> list[Content]:
            return [Content.from_text("public result")]

        await FunctionMiddlewarePipeline(tracker, policy).execute(context, execute)

        assert context.metadata["result_label"].integrity == IntegrityLabel.TRUSTED
        assert context.metadata["result_label"].confidentiality == ConfidentialityLabel.PRIVATE
        assert tracker.get_context_label().confidentiality == ConfidentialityLabel.PRIVATE

    async def test_policy_approval_allows_exact_resolved_invocation(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        variable_id = tracker.get_variable_store().store(
            "payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink = self._sink(accepts_untrusted=False)
        request = FunctionInvocationContext(function=sink, arguments={"value": f"[{variable_id}]"})
        request.metadata.update({"call_id": "call-approved", "function_call_occurrence_id": "occurrence-approved"})

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                request,
                lambda _context: pytest.fail("Tool must wait for approval"),
            )

        approval_request = request.result
        assert isinstance(approval_request, Content)
        assert approval_request.id == "occurrence-approved"
        assert approval_request.function_call is not None
        assert approval_request.function_call.call_id == "call-approved"
        assert approval_request.function_call.parse_arguments() == {"value": f"[{variable_id}]"}

        replay = FunctionInvocationContext(function=sink, arguments={"value": f"[{variable_id}]"})
        replay.metadata.update({
            "call_id": "call-approved",
            "function_call_occurrence_id": "occurrence-approved",
            "approval_response": approval_request.to_function_approval_response(True),
        })
        received: list[str] = []

        async def execute(current: FunctionInvocationContext) -> list[Content]:
            received.append(cast(str, cast(dict[str, Any], current.arguments)["value"]))
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(tracker, policy).execute(replay, execute)

        assert received == ["payload"]
        assert replay.metadata["user_approved_violation"] is True

    async def test_changed_resolved_arguments_do_not_match_approval(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        session = AgentSession(session_id="resolved-mismatch")
        variable_id = tracker.get_variable_store(session).store(
            "original",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink = self._sink(accepts_untrusted=False)
        request = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            session=session,
        )
        request.metadata.update({"call_id": "call-resolved", "function_call_occurrence_id": "occurrence-resolved"})

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                request,
                lambda _context: pytest.fail("Tool must wait for approval"),
            )
        approval_request = cast(Content, request.result)
        security_state = cast(dict[str, Any], session.state["__agent_framework_fides_security__"])
        variable_state = cast(dict[str, Any], security_state["variables"])
        cast(dict[str, Any], variable_state[variable_id])["content"] = json.dumps("changed")

        replay = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            session=session,
        )
        replay.metadata.update({
            "call_id": "call-resolved",
            "function_call_occurrence_id": "occurrence-resolved",
            "approval_response": approval_request.to_function_approval_response(True),
        })

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                replay,
                lambda _context: pytest.fail("Changed resolved arguments need fresh approval"),
            )
        assert isinstance(replay.result, Content)
        assert replay.result.type == "function_approval_request"

    async def test_changed_runtime_kwargs_do_not_match_approval(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        variable_id = tracker.get_variable_store().store(
            "payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink = self._sink(accepts_untrusted=False)
        request = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            kwargs={"tenant": "one"},
        )
        request.metadata["call_id"] = "call-runtime"

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                request,
                lambda _context: pytest.fail("Tool must wait for approval"),
            )
        approval_request = cast(Content, request.result)
        replay = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            kwargs={"tenant": "two"},
        )
        replay.metadata.update({
            "call_id": "call-runtime",
            "approval_response": approval_request.to_function_approval_response(True),
        })

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                replay,
                lambda _context: pytest.fail("Changed runtime kwargs need fresh approval"),
            )
        assert isinstance(replay.result, Content)
        assert replay.result.type == "function_approval_request"

    async def test_opaque_runtime_kwarg_fails_closed(self) -> None:
        tracker = LabelTrackingFunctionMiddleware()
        policy = PolicyEnforcementFunctionMiddleware(approval_on_violation=True)
        variable_id = tracker.get_variable_store().store(
            "payload",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        context = FunctionInvocationContext(
            function=self._sink(accepts_untrusted=False),
            arguments={"value": f"[{variable_id}]"},
            kwargs={"opaque": object()},
        )
        context.metadata["call_id"] = "call-opaque"

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                context,
                lambda _context: pytest.fail("Opaque invocation must not execute"),
            )

        assert isinstance(context.result, dict)
        assert context.result["violation_type"] == "unsafe_approval_binding"

    async def test_pending_policy_approval_survives_session_restore(self) -> None:
        config = SecureAgentConfig(approval_on_violation=True)
        session = AgentSession(session_id="restored-approval")
        tracker, policy = await _get_session_security_middleware(config, session)
        variable_id = config.get_variable_store(session).store(
            ["durable", 1],
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
        )
        sink = self._sink(accepts_untrusted=False)
        request = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            session=session,
            kwargs={"session": session, "tenant": "one"},
        )
        request.metadata.update({"call_id": "call-restored", "function_call_occurrence_id": "occurrence-restored"})

        with pytest.raises(MiddlewareTermination):
            await FunctionMiddlewarePipeline(tracker, policy).execute(
                request,
                lambda _context: pytest.fail("Tool must wait for approval"),
            )
        approval_request = cast(Content, request.result)
        restored = AgentSession.from_dict(json.loads(json.dumps(session.to_dict())))
        restored_tracker, restored_policy = await _get_session_security_middleware(config, restored)
        replay = FunctionInvocationContext(
            function=sink,
            arguments={"value": f"[{variable_id}]"},
            session=restored,
            kwargs={"session": restored, "tenant": "one"},
        )
        replay.metadata.update({
            "call_id": "call-restored",
            "function_call_occurrence_id": "occurrence-restored",
            "approval_response": approval_request.to_function_approval_response(True),
        })
        executed = False

        async def execute(_context: FunctionInvocationContext) -> list[Content]:
            nonlocal executed
            executed = True
            return [Content.from_text("sent")]

        await FunctionMiddlewarePipeline(restored_tracker, restored_policy).execute(replay, execute)

        assert executed is True
        assert replay.metadata["user_approved_violation"] is True
