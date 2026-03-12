# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for prompt injection defense system."""

import json
import pytest
from agent_framework import (
    ContentLabel,
    IntegrityLabel,
    ConfidentialityLabel,
    ContentVariableStore,
    VariableReferenceContent,
    combine_labels,
    store_untrusted_content,
    LabelTrackingFunctionMiddleware,
    PolicyEnforcementFunctionMiddleware,
    FunctionInvocationContext,
)
from agent_framework._tools import FunctionTool
from pydantic import BaseModel


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
            metadata={"user_id": "123"}
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
            metadata={"source": "external"}
        )
        
        data = label.to_dict()
        assert data["integrity"] == "untrusted"
        assert data["confidentiality"] == "user_identity"
        assert data["metadata"]["source"] == "external"
    
    def test_label_deserialization(self):
        """Test label deserialization from dict."""
        data = {
            "integrity": "trusted",
            "confidentiality": "private",
            "metadata": {"key": "value"}
        }
        
        label = ContentLabel.from_dict(data)
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PRIVATE
        assert label.metadata["key"] == "value"


class TestCombineLabels:
    """Tests for label combination logic."""
    
    def test_combine_empty(self):
        """Test combining no labels returns default."""
        label = combine_labels()
        assert label.integrity == IntegrityLabel.TRUSTED
        assert label.confidentiality == ConfidentialityLabel.PUBLIC
    
    def test_combine_single(self):
        """Test combining single label."""
        input_label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        )
        
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
        ref = VariableReferenceContent(
            variable_id="var_abc123",
            label=label,
            description="Test content"
        )
        
        assert ref.variable_id == "var_abc123"
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.description == "Test content"
        assert ref.type == "variable_reference"
    
    def test_reference_serialization(self):
        """Test serializing variable reference."""
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        ref = VariableReferenceContent(
            variable_id="var_abc123",
            label=label,
            description="Test"
        )
        
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
            "description": "Test"
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
            "description": "Test"
        }
        
        ref = VariableReferenceContent.from_dict(data)
        assert ref.variable_id == "var_abc123"
        assert ref.label.integrity == IntegrityLabel.UNTRUSTED
        assert ref.description == "Test"


class TestStoreUntrustedContent:
    """Tests for store_untrusted_content helper."""
    
    def test_store_with_label(self):
        """Test storing content with explicit label."""
        label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        )
        
        ref = store_untrusted_content(
            "test content",
            label=label,
            description="Test"
        )
        
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
        
        function = FunctionTool(
            fn=mock_fn,
            name="mock_function",
            description="Mock function",
            args_schema=MockArgs
        )
        return function
    
    @pytest.mark.asyncio
    async def test_label_attached_to_context(self, middleware, mock_function):
        """Test that label is attached to context metadata."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "mock result"
        
        await middleware.process(context, next_fn)
        
        assert "security_label" in context.metadata
        label = context.metadata["security_label"]
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
            additional_properties={"source_integrity": "trusted"}
        )
        
        args = trusted_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=trusted_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "mock result"
        
        await middleware.process(context, next_fn)
        
        label = context.metadata["security_label"]
        assert label.integrity == IntegrityLabel.TRUSTED
    
    @pytest.mark.asyncio
    async def test_tool_without_source_integrity_defaults_untrusted(self, middleware, mock_function):
        """Test that tools without source_integrity declaration default to UNTRUSTED."""
        # mock_function has no additional_properties, so no source_integrity
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "mock result"
        
        await middleware.process(context, next_fn)
        
        label = context.metadata["security_label"]
        # Should default to UNTRUSTED (safe default)
        assert label.integrity == IntegrityLabel.UNTRUSTED
    
    @pytest.mark.asyncio
    async def test_input_labels_propagate_to_output(self, middleware):
        """Test that untrusted input labels propagate to output."""
        # Create a trusted function
        class TrustedArgs(BaseModel):
            data: dict
        
        async def process_fn(data: dict) -> str:
            return f"processed"
        
        trusted_function = FunctionTool(
            fn=process_fn,
            name="process_data",
            description="Process data",
            args_schema=TrustedArgs,
            additional_properties={"source_integrity": "trusted"}
        )
        
        # Create argument that contains untrusted label
        args = trusted_function.args_schema(data={
            "content": "test",
            "security_label": {"integrity": "untrusted", "confidentiality": "public"}
        })
        
        context = FunctionInvocationContext(
            function=trusted_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "processed result"
        
        await middleware.process(context, next_fn)
        
        label = context.metadata["security_label"]
        # Even though source_integrity is trusted, input has untrusted label
        # Combined result should be UNTRUSTED
        assert label.integrity == IntegrityLabel.UNTRUSTED
    
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
            additional_properties={"source_integrity": "trusted"}
        )
        
        # Create a VariableReferenceContent with UNTRUSTED label
        untrusted_label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_ref = VariableReferenceContent(
            variable_id="var_test123",
            label=untrusted_label,
            description="Test variable"
        )
        
        # Pass the VariableReferenceContent as an argument
        context = FunctionInvocationContext(
            function=trusted_function,
            arguments=trusted_function.args_schema(var_ref={"test": "value"})  # Regular dict
        )
        # But also pass the actual VariableReferenceContent in kwargs
        context.kwargs = {"var_ref_obj": var_ref}
        
        async def next_fn():
            context.result = "processed"
        
        await middleware.process(context, next_fn)
        
        label = context.metadata["security_label"]
        # The VariableReferenceContent label should be extracted and combined
        assert label.integrity == IntegrityLabel.UNTRUSTED


class TestPolicyEnforcementMiddleware:
    """Tests for PolicyEnforcementFunctionMiddleware."""
    
    @pytest.fixture
    def middleware(self):
        """Create middleware instance."""
        return PolicyEnforcementFunctionMiddleware(
            allow_untrusted_tools={"allowed_function"},
            block_on_violation=True
        )
    
    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""
        class MockArgs(BaseModel):
            arg: str
        
        async def mock_fn(arg: str) -> str:
            return f"result: {arg}"
        
        function = FunctionTool(
            fn=mock_fn,
            name="restricted_function",
            description="Restricted function",
            args_schema=MockArgs
        )
        return function
    
    @pytest.mark.asyncio
    async def test_trusted_call_allowed(self, middleware, mock_function):
        """Test that trusted tool calls are allowed."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        # Set trusted label
        label = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["security_label"] = label
        
        async def next_fn():
            context.result = "mock result"
        
        await middleware.process(context, next_fn)
        
        assert context.result == "mock result"
        assert not getattr(context, "terminate", False)
    
    @pytest.mark.asyncio
    async def test_untrusted_call_blocked(self, middleware, mock_function):
        """Test that untrusted tool calls are blocked."""
        args = mock_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        # Set untrusted context label (policy enforcement uses context_label)
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["context_label"] = label
        
        async def next_fn():
            context.result = "should not execute"
        
        await middleware.process(context, next_fn)
        
        assert getattr(context, "terminate", False)
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
            fn=mock_fn,
            name="allowed_function",
            description="Allowed function",
            args_schema=MockArgs
        )
        
        args = allowed_function.args_schema(arg="test")
        context = FunctionInvocationContext(
            function=allowed_function,
            arguments=args
        )
        
        # Set untrusted context label (policy enforcement uses context_label)
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        context.metadata["context_label"] = label
        
        async def next_fn():
            context.result = "allowed result"
        
        await middleware.process(context, next_fn)
        
        assert context.result == "allowed result"
        assert not getattr(context, "terminate", False)
    
    def test_audit_log_recording(self, middleware, mock_function):
        """Test that violations are recorded in audit log."""
        initial_count = len(middleware.get_audit_log())
        assert initial_count == 0


class TestAutomaticHiding:
    """Tests for automatic variable hiding functionality."""
    
    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""
        class MockArgs(BaseModel):
            pass
        
        async def mock_fn() -> str:
            return "test result"
        
        function = FunctionTool(
            fn=mock_fn,
            name="test_function",
            description="Test function",
            args_schema=MockArgs
        )
        return function
    
    @pytest.fixture
    def middleware_auto_hide(self, mock_function):
        """Create middleware with automatic hiding enabled."""
        return LabelTrackingFunctionMiddleware(
            auto_hide_untrusted=True,
            hide_threshold=IntegrityLabel.UNTRUSTED
        )
    
    @pytest.fixture
    def middleware_no_auto_hide(self, mock_function):
        """Create middleware with automatic hiding disabled."""
        return LabelTrackingFunctionMiddleware(
            auto_hide_untrusted=False
        )
    
    @pytest.mark.asyncio
    async def test_untrusted_result_auto_hidden(self, middleware_auto_hide, mock_function):
        """Test that UNTRUSTED results are automatically hidden."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        # By default, AI-generated calls are UNTRUSTED
        
        async def next_fn():
            context.result = "sensitive data"
        
        await middleware_auto_hide.process(context, next_fn)
        
        # Result is now a JSON string (middleware re-serializes for the LLM API)
        parsed = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert isinstance(parsed, dict)
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
            additional_properties={"source_integrity": "trusted"}
        )
        
        args = trusted_function.args_schema()
        context = FunctionInvocationContext(
            function=trusted_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "trusted data"
        
        await middleware_auto_hide.process(context, next_fn)
        
        # Result should remain unchanged (TRUSTED is not hidden)
        assert context.result == "trusted data"
        assert not isinstance(context.result, VariableReferenceContent)
    
    @pytest.mark.asyncio
    async def test_auto_hide_disabled(self, middleware_no_auto_hide, mock_function):
        """Test that untrusted results are not hidden when auto_hide is disabled."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "sensitive data"
        
        await middleware_no_auto_hide.process(context, next_fn)
        
        # Result should remain unchanged even if UNTRUSTED
        assert context.result == "sensitive data"
        assert not isinstance(context.result, VariableReferenceContent)
    
    @pytest.mark.asyncio
    async def test_variable_metadata_tracking(self, middleware_auto_hide, mock_function):
        """Test that variable metadata is properly tracked."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "private data"
        
        await middleware_auto_hide.process(context, next_fn)
        
        # Check variable metadata
        parsed = json.loads(context.result) if isinstance(context.result, str) else context.result
        var_id = parsed["variable_id"]
        metadata = middleware_auto_hide.get_variable_metadata(var_id)
        assert metadata is not None
        assert "function_name" in metadata
    
    @pytest.mark.asyncio
    async def test_list_variables(self, middleware_auto_hide, mock_function):
        """Test that list_variables returns all stored variables."""
        args1 = mock_function.args_schema()
        context1 = FunctionInvocationContext(
            function=mock_function,
            arguments=args1
        )
        
        args2 = mock_function.args_schema()
        context2 = FunctionInvocationContext(
            function=mock_function,
            arguments=args2
        )
        
        async def next_fn1():
            context1.result = "data1"
        
        async def next_fn2():
            context2.result = "data2"
        
        await middleware_auto_hide.process(context1, next_fn1)
        await middleware_auto_hide.process(context2, next_fn2)
        
        variables = middleware_auto_hide.list_variables()
        assert len(variables) == 2
        parsed1 = json.loads(context1.result) if isinstance(context1.result, str) else context1.result
        parsed2 = json.loads(context2.result) if isinstance(context2.result, str) else context2.result
        assert parsed1["variable_id"] in variables
        assert parsed2["variable_id"] in variables
    
    @pytest.mark.asyncio
    async def test_thread_local_middleware_access(self, middleware_auto_hide, mock_function):
        """Test that middleware can be accessed via thread-local storage."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            from agent_framework._security_middleware import get_current_middleware
            
            # Should be able to access middleware from thread-local
            current = get_current_middleware()
            assert current is middleware_auto_hide
            
            context.result = "test"
        
        await middleware_auto_hide.process(context, next_fn)
    
    @pytest.mark.asyncio
    async def test_inspect_variable_uses_middleware_store(self, middleware_auto_hide, mock_function):
        """Test that inspect_variable uses the middleware's variable store."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "hidden content"
        
        await middleware_auto_hide.process(context, next_fn)
        
        parsed = json.loads(context.result) if isinstance(context.result, str) else context.result
        var_id = parsed["variable_id"]
        
        # Verify we can retrieve the content from the store
        store = middleware_auto_hide.get_variable_store()
        content, label = store.retrieve(var_id)
        assert content == "hidden content"
        assert label.integrity == IntegrityLabel.UNTRUSTED
    
    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate_variables(self, middleware_auto_hide, mock_function):
        """Test that multiple tool calls accumulate variables in the store."""
        for i in range(5):
            args = mock_function.args_schema()
            context = FunctionInvocationContext(
                function=mock_function,
                arguments=args
            )
            
            async def next_fn(data=f"data_{i}"):
                context.result = data
            
            await middleware_auto_hide.process(context, next_fn)
        
        # Should have 5 variables
        variables = middleware_auto_hide.list_variables()
        assert len(variables) == 5


class TestSecureAgentConfig:
    """Tests for SecureAgentConfig helper class."""
    
    def test_create_config_defaults(self):
        """Test creating config with default values."""
        from agent_framework import SecureAgentConfig
        
        config = SecureAgentConfig()
        
        # Should have middleware
        middleware = config.get_middleware()
        assert len(middleware) == 2
        assert isinstance(middleware[0], LabelTrackingFunctionMiddleware)
        assert isinstance(middleware[1], PolicyEnforcementFunctionMiddleware)
    
    def test_create_config_with_options(self):
        """Test creating config with custom options."""
        from agent_framework import SecureAgentConfig
        
        config = SecureAgentConfig(
            auto_hide_untrusted=True,
            allow_untrusted_tools={"fetch_data", "search"},
            block_on_violation=True,
        )
        
        middleware = config.get_middleware()
        assert len(middleware) == 2
        
        label_tracker = middleware[0]
        policy_enforcer = middleware[1]
        
        assert label_tracker.auto_hide_untrusted is True
        assert "fetch_data" in policy_enforcer.allow_untrusted_tools
        assert "search" in policy_enforcer.allow_untrusted_tools
    
    def test_get_tools_returns_security_tools(self):
        """Test that get_tools returns quarantined_llm and inspect_variable."""
        from agent_framework import SecureAgentConfig
        
        config = SecureAgentConfig()
        tools = config.get_tools()
        
        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "quarantined_llm" in tool_names
        assert "inspect_variable" in tool_names
    
    def test_get_instructions_returns_string(self):
        """Test that get_instructions returns instruction text."""
        from agent_framework import SecureAgentConfig, SECURITY_TOOL_INSTRUCTIONS
        
        config = SecureAgentConfig()
        instructions = config.get_instructions()
        
        assert isinstance(instructions, str)
        assert len(instructions) > 100
        assert instructions == SECURITY_TOOL_INSTRUCTIONS
        assert "quarantined_llm" in instructions
        assert "inspect_variable" in instructions


class TestGetSecurityTools:
    """Tests for get_security_tools function."""
    
    def test_get_security_tools_from_module(self):
        """Test importing get_security_tools from agent_framework."""
        from agent_framework import get_security_tools
        
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
        from agent_framework import quarantined_llm
        
        # Store a variable
        store = middleware_with_store.get_variable_store()
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_id = store.store("Test content for processing", label)
        
        # Call quarantined_llm with variable_id
        result = await quarantined_llm(
            prompt="Process this content",
            variable_ids=[var_id]
        )
        
        assert result["quarantined"] is True
        assert var_id in result["variables_processed"]
        assert len(result["content_summary"]) == 1
        assert "27 chars" in result["content_summary"][0]  # len("Test content for processing")
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_with_multiple_variable_ids(self, middleware_with_store):
        """Test quarantined_llm retrieves multiple variables."""
        from agent_framework import quarantined_llm
        
        # Store multiple variables
        store = middleware_with_store.get_variable_store()
        label = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        var_id1 = store.store("First content", label)
        var_id2 = store.store("Second content", label)
        
        # Call quarantined_llm with multiple variable_ids
        result = await quarantined_llm(
            prompt="Compare these",
            variable_ids=[var_id1, var_id2]
        )
        
        assert result["quarantined"] is True
        assert len(result["variables_processed"]) == 2
        assert var_id1 in result["variables_processed"]
        assert var_id2 in result["variables_processed"]
        assert len(result["content_summary"]) == 2
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_with_unknown_variable_id(self, middleware_with_store):
        """Test quarantined_llm handles unknown variable IDs gracefully."""
        from agent_framework import quarantined_llm
        
        # Call with non-existent variable ID
        result = await quarantined_llm(
            prompt="Process this",
            variable_ids=["var_nonexistent"]
        )
        
        # Should still return a result, just with UNTRUSTED label
        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"
        assert "var_nonexistent" in result["variables_processed"]
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_without_variable_ids(self, middleware_with_store):
        """Test quarantined_llm works with labelled_data instead of variable_ids."""
        from agent_framework import quarantined_llm
        
        result = await quarantined_llm(
            prompt="Process this data",
            labelled_data={
                "data": {
                    "content": "Some external data",
                    "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                }
            }
        )
        
        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"

    @pytest.mark.asyncio
    async def test_quarantined_llm_with_legacy_label_key(self, middleware_with_store):
        """Test quarantined_llm accepts legacy 'label' key for backward compatibility."""
        from agent_framework import quarantined_llm
        
        result = await quarantined_llm(
            prompt="Process this data",
            labelled_data={
                "data": {
                    "content": "Some external data",
                    "label": {"integrity": "untrusted", "confidentiality": "public"}  # Legacy key
                }
            }
        )
        
        assert result["quarantined"] is True
        assert result["security_label"]["integrity"] == "untrusted"


class TestMiddlewareSetCurrent:
    """Tests for middleware _set_as_current and _clear_current methods."""
    
    def test_set_and_clear_current(self):
        """Test setting and clearing thread-local middleware reference."""
        from agent_framework._security_middleware import get_current_middleware
        
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
        from agent_framework._security_middleware import get_current_middleware
        
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
        
        function = FunctionTool(
            fn=mock_fn,
            name="test_function",
            description="Test function",
            args_schema=MockArgs
        )
        return function
    
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
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "untrusted result"
        
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
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "untrusted result"
        
        # Initial context should be TRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        
        await middleware.process(context, next_fn)
        
        # Context should STILL be TRUSTED because result was hidden
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        # Result should be a serialized variable reference (JSON string)
        parsed = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert isinstance(parsed, dict)
        assert parsed.get("type") == "variable_reference"
    
    @pytest.mark.asyncio
    async def test_context_label_passed_to_policy_enforcement(self, middleware, mock_function):
        """Test that context label is passed in metadata for policy enforcement."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = "result"
        
        await middleware.process(context, next_fn)
        
        # Both call label and context label should be in metadata
        assert "security_label" in context.metadata
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
            additional_properties={"source_integrity": "trusted"}
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
            current_context.result = "result"
        
        # First call: trusted function (TRUSTED)
        context1 = FunctionInvocationContext(
            function=trusted_function,
            arguments=trusted_function.args_schema()
        )
        current_context = context1
        
        await middleware.process(context1, next_fn)
        
        # Context should still be TRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.TRUSTED
        
        # Second call: untrusted function (UNTRUSTED)
        context2 = FunctionInvocationContext(
            function=untrusted_function,
            arguments=untrusted_function.args_schema()
        )
        current_context = context2
        
        await middleware.process(context2, next_fn)
        
        # Context should now be UNTRUSTED
        assert middleware.get_context_label().integrity == IntegrityLabel.UNTRUSTED
        
        # Third call: trusted function again
        context3 = FunctionInvocationContext(
            function=trusted_function,
            arguments=trusted_function.args_schema()
        )
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
        return PolicyEnforcementFunctionMiddleware(
            allow_untrusted_tools={"allowed_function"},
            block_on_violation=True
        )
    
    @pytest.fixture
    def mock_function(self):
        """Create mock FunctionTool."""
        class MockArgs(BaseModel):
            arg: str = "default"
        
        async def mock_fn(arg: str = "default") -> str:
            return f"result: {arg}"
        
        function = FunctionTool(
            fn=mock_fn,
            name="restricted_function",
            description="Restricted function",
            args_schema=MockArgs
        )
        return function
    
    @pytest.mark.asyncio
    async def test_policy_blocks_in_untrusted_context(self, label_middleware, policy_middleware, mock_function):
        """Test that policy blocks tool calls when context is UNTRUSTED."""
        # First, taint the context
        label_middleware._update_context_label(ContentLabel(integrity=IntegrityLabel.UNTRUSTED))
        
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        # Set up labels as if label_middleware ran
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "should not reach"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be blocked due to untrusted context
        assert getattr(context, "terminate", False) is True
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
            args_schema=MockArgs
        )
        
        args = allowed_function.args_schema()
        context = FunctionInvocationContext(
            function=allowed_function,
            arguments=args
        )
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "allowed"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be allowed
        assert context.result == "allowed"
        assert not getattr(context, 'terminate', False)


# ========== Phase 1: Message-Level Label Tracking Tests ==========

class TestLabeledMessage:
    """Tests for LabeledMessage class."""
    
    def test_create_user_message_defaults_to_trusted(self):
        """Test that user messages are TRUSTED by default."""
        from agent_framework import LabeledMessage
        
        msg = LabeledMessage(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED
        assert msg.is_trusted()
    
    def test_create_system_message_defaults_to_trusted(self):
        """Test that system messages are TRUSTED by default."""
        from agent_framework import LabeledMessage
        
        msg = LabeledMessage(role="system", content="You are an assistant.")
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED
    
    def test_create_tool_message_defaults_to_untrusted(self):
        """Test that tool messages are UNTRUSTED by default."""
        from agent_framework import LabeledMessage
        
        msg = LabeledMessage(role="tool", content="External API result")
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert not msg.is_trusted()
    
    def test_create_assistant_message_no_sources(self):
        """Test assistant message without sources defaults to TRUSTED."""
        from agent_framework import LabeledMessage
        
        msg = LabeledMessage(role="assistant", content="I'll help you.")
        assert msg.security_label.integrity == IntegrityLabel.TRUSTED
    
    def test_create_assistant_message_with_untrusted_source(self):
        """Test assistant message inherits UNTRUSTED from sources."""
        from agent_framework import LabeledMessage
        
        untrusted_source = ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        msg = LabeledMessage(
            role="assistant",
            content="Based on the data...",
            source_labels=[untrusted_source]
        )
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
    
    def test_explicit_label_overrides_inference(self):
        """Test that explicit label overrides role-based inference."""
        from agent_framework import LabeledMessage
        
        explicit_label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        )
        msg = LabeledMessage(
            role="user",  # Would normally be TRUSTED
            content="Hello",
            security_label=explicit_label
        )
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert msg.security_label.confidentiality == ConfidentialityLabel.PRIVATE
    
    def test_message_serialization(self):
        """Test LabeledMessage serialization to dict."""
        from agent_framework import LabeledMessage
        
        msg = LabeledMessage(
            role="user",
            content="Hello",
            message_index=5,
            metadata={"key": "value"}
        )
        
        data = msg.to_dict()
        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert data["message_index"] == 5
        assert data["security_label"]["integrity"] == "trusted"
    
    def test_message_deserialization(self):
        """Test LabeledMessage deserialization from dict."""
        from agent_framework import LabeledMessage
        
        data = {
            "role": "tool",
            "content": "API result",
            "security_label": {"integrity": "untrusted", "confidentiality": "public"},
            "message_index": 3
        }
        
        msg = LabeledMessage.from_dict(data)
        assert msg.role == "tool"
        assert msg.security_label.integrity == IntegrityLabel.UNTRUSTED
        assert msg.message_index == 3
    
    def test_from_message_convenience_method(self):
        """Test creating LabeledMessage from a standard message dict."""
        from agent_framework import LabeledMessage
        
        standard_msg = {"role": "user", "content": "What's the weather?"}
        labeled = LabeledMessage.from_message(standard_msg, index=0)
        
        assert labeled.role == "user"
        assert labeled.content == "What's the weather?"
        assert labeled.message_index == 0
        assert labeled.is_trusted()


class TestMiddlewareMessageLabeling:
    """Tests for middleware message label tracking."""
    
    def test_label_message(self):
        """Test labeling a message by index."""
        middleware = LabelTrackingFunctionMiddleware()
        
        label = ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        )
        middleware.label_message(5, label)
        
        retrieved = middleware.get_message_label(5)
        assert retrieved is not None
        assert retrieved.integrity == IntegrityLabel.UNTRUSTED
    
    def test_get_unlabeled_message_returns_none(self):
        """Test that unlabeled messages return None."""
        middleware = LabelTrackingFunctionMiddleware()
        
        assert middleware.get_message_label(999) is None
    
    def test_label_messages_batch(self):
        """Test batch labeling of messages."""
        from agent_framework import LabeledMessage
        middleware = LabelTrackingFunctionMiddleware()
        
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "tool", "content": "External data"},
        ]
        
        labeled = middleware.label_messages(messages)
        
        assert len(labeled) == 3
        assert labeled[0].security_label.integrity == IntegrityLabel.TRUSTED
        assert labeled[1].security_label.integrity == IntegrityLabel.TRUSTED
        assert labeled[2].security_label.integrity == IntegrityLabel.UNTRUSTED
        
        # Check that labels are stored in middleware
        all_labels = middleware.get_all_message_labels()
        assert len(all_labels) == 3
    
    def test_reset_clears_message_labels(self):
        """Test that reset_context_label also clears message labels."""
        middleware = LabelTrackingFunctionMiddleware()
        
        middleware.label_message(0, ContentLabel())
        middleware.label_message(1, ContentLabel())
        
        assert len(middleware.get_all_message_labels()) == 2
        
        middleware.reset_context_label()
        
        assert len(middleware.get_all_message_labels()) == 0


# ========== Phase 2: Content Lineage Tracking Tests ==========

class TestContentLineage:
    """Tests for ContentLineage class."""
    
    def test_create_lineage(self):
        """Test creating ContentLineage."""
        from agent_framework import ContentLineage
        
        lineage = ContentLineage(
            content_id="result_123",
            derived_from=["var_abc", "var_def"],
            transformation="llm_summary",
            combined_label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        assert lineage.content_id == "result_123"
        assert lineage.derived_from == ["var_abc", "var_def"]
        assert lineage.transformation == "llm_summary"
        assert lineage.is_derived()
    
    def test_lineage_not_derived(self):
        """Test lineage without derivation sources."""
        from agent_framework import ContentLineage
        
        lineage = ContentLineage(content_id="original_123")
        assert not lineage.is_derived()
    
    def test_lineage_serialization(self):
        """Test ContentLineage serialization."""
        from agent_framework import ContentLineage
        
        lineage = ContentLineage(
            content_id="test_id",
            derived_from=["src_1"],
            transformation="extract",
            combined_label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            metadata={"key": "value"}
        )
        
        data = lineage.to_dict()
        assert data["content_id"] == "test_id"
        assert data["derived_from"] == ["src_1"]
        assert data["transformation"] == "extract"
        assert data["combined_label"]["integrity"] == "untrusted"
    
    def test_lineage_deserialization(self):
        """Test ContentLineage deserialization."""
        from agent_framework import ContentLineage
        
        data = {
            "content_id": "test_id",
            "derived_from": ["src_1", "src_2"],
            "transformation": "combine",
            "combined_label": {"integrity": "untrusted", "confidentiality": "private"}
        }
        
        lineage = ContentLineage.from_dict(data)
        assert lineage.content_id == "test_id"
        assert len(lineage.derived_from) == 2
        assert lineage.combined_label.integrity == IntegrityLabel.UNTRUSTED


class TestMiddlewareLineageTracking:
    """Tests for middleware lineage tracking."""
    
    def test_track_lineage(self):
        """Test tracking content lineage."""
        middleware = LabelTrackingFunctionMiddleware()
        
        lineage = middleware.track_lineage(
            content_id="result_123",
            derived_from=["var_abc", "var_def"],
            transformation="llm_summary",
            combined_label=ContentLabel(integrity=IntegrityLabel.UNTRUSTED),
            metadata={"prompt": "Summarize"}
        )
        
        assert lineage.content_id == "result_123"
        assert middleware.get_lineage("result_123") is not None
    
    def test_get_all_lineage(self):
        """Test getting all tracked lineage."""
        middleware = LabelTrackingFunctionMiddleware()
        
        middleware.track_lineage(
            content_id="r1",
            derived_from=["s1"],
            transformation="t1",
            combined_label=ContentLabel()
        )
        middleware.track_lineage(
            content_id="r2",
            derived_from=["s2"],
            transformation="t2",
            combined_label=ContentLabel()
        )
        
        all_lineage = middleware.get_all_lineage()
        assert len(all_lineage) == 2
        assert "r1" in all_lineage
        assert "r2" in all_lineage
    
    def test_reset_clears_lineage(self):
        """Test that reset_context_label also clears lineage."""
        middleware = LabelTrackingFunctionMiddleware()
        
        middleware.track_lineage(
            content_id="r1",
            derived_from=["s1"],
            transformation="t1",
            combined_label=ContentLabel()
        )
        
        assert len(middleware.get_all_lineage()) == 1
        
        middleware.reset_context_label()
        
        assert len(middleware.get_all_lineage()) == 0


# ========== Quarantined LLM Auto-Hide Tests ==========

class TestQuarantinedLLMAutoHide:
    """Tests for quarantined_llm auto-hiding of UNTRUSTED results."""
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_auto_hides_untrusted_result(self):
        """Test that quarantined_llm auto-hides UNTRUSTED results."""
        from agent_framework import quarantined_llm, LabelTrackingFunctionMiddleware
        from agent_framework._security_middleware import _current_middleware
        
        middleware = LabelTrackingFunctionMiddleware()
        
        # Store some untrusted content
        var_id = middleware.get_variable_store().store(
            "untrusted external data",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        # Set middleware context
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Summarize this data",
                variable_ids=[var_id],
                auto_hide_result=True
            )
            
            # Result should be auto-hidden since input was UNTRUSTED
            assert result["auto_hidden"] is True
            assert result["type"] == "variable_reference"
            assert "variable_id" in result
            assert result["variable_id"].startswith("var_")
            
            # Lineage should be included
            assert "lineage" in result
            assert result["lineage"]["derived_from"] == [var_id]
            assert result["lineage"]["transformation"] == "quarantined_llm"
        finally:
            _current_middleware.instance = None
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_no_hide_when_disabled(self):
        """Test that auto_hide_result=False prevents hiding."""
        from agent_framework import quarantined_llm, LabelTrackingFunctionMiddleware
        from agent_framework._security_middleware import _current_middleware
        
        middleware = LabelTrackingFunctionMiddleware()
        
        var_id = middleware.get_variable_store().store(
            "untrusted data",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Process this",
                variable_ids=[var_id],
                auto_hide_result=False
            )
            
            # Result should NOT be hidden
            assert result["auto_hidden"] is False
            assert "response" in result
            assert "type" not in result or result.get("type") != "variable_reference"
        finally:
            _current_middleware.instance = None
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_trusted_result_not_hidden(self):
        """Test that TRUSTED results are not auto-hidden."""
        from agent_framework import quarantined_llm, LabelTrackingFunctionMiddleware
        from agent_framework._security_middleware import _current_middleware
        
        middleware = LabelTrackingFunctionMiddleware()
        
        # Store TRUSTED content (unusual but possible)
        var_id = middleware.get_variable_store().store(
            "trusted system data",
            ContentLabel(integrity=IntegrityLabel.TRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Process this",
                variable_ids=[var_id],
                auto_hide_result=True  # Still enabled
            )
            
            # Result should NOT be hidden because input was TRUSTED
            assert result["auto_hidden"] is False
            assert "response" in result
        finally:
            _current_middleware.instance = None
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_includes_lineage(self):
        """Test that quarantined_llm always includes lineage tracking."""
        from agent_framework import quarantined_llm, LabelTrackingFunctionMiddleware
        from agent_framework._security_middleware import _current_middleware
        
        middleware = LabelTrackingFunctionMiddleware()
        
        var1 = middleware.get_variable_store().store(
            "data1",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        var2 = middleware.get_variable_store().store(
            "data2",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Compare these",
                variable_ids=[var1, var2]
            )
            
            # Check lineage
            lineage = result["lineage"]
            assert var1 in lineage["derived_from"]
            assert var2 in lineage["derived_from"]
            assert lineage["transformation"] == "quarantined_llm"
            assert lineage["combined_label"]["integrity"] == "untrusted"
            
            # Check middleware tracked the lineage
            all_lineage = middleware.get_all_lineage()
            assert len(all_lineage) == 1
        finally:
            _current_middleware.instance = None


class TestQuarantineClient:
    """Tests for quarantine chat client functionality."""
    
    def test_set_and_get_quarantine_client(self):
        """Test setting and getting the quarantine client."""
        from agent_framework import set_quarantine_client, get_quarantine_client
        
        # Initially should be None (or whatever state it's in)
        # Clear it first
        set_quarantine_client(None)
        assert get_quarantine_client() is None
        
        # Create a mock client
        class MockClient:
            async def get_response(self, messages, **kwargs):
                pass
        
        mock_client = MockClient()
        set_quarantine_client(mock_client)
        
        assert get_quarantine_client() is mock_client
        
        # Clean up
        set_quarantine_client(None)
        assert get_quarantine_client() is None
    
    def test_secure_agent_config_sets_quarantine_client(self):
        """Test that SecureAgentConfig sets the quarantine client."""
        from agent_framework import SecureAgentConfig, get_quarantine_client, set_quarantine_client
        
        # Clear any existing client
        set_quarantine_client(None)
        
        # Create a mock client
        class MockClient:
            async def get_response(self, messages, **kwargs):
                pass
        
        mock_client = MockClient()
        
        # Create config with quarantine client
        config = SecureAgentConfig(
            quarantine_chat_client=mock_client
        )
        
        # Should have set the global client
        assert get_quarantine_client() is mock_client
        
        # Config should also return the client
        assert config.get_quarantine_client() is mock_client
        
        # Clean up
        set_quarantine_client(None)
    
    def test_secure_agent_config_without_quarantine_client(self):
        """Test SecureAgentConfig without quarantine client doesn't set one."""
        from agent_framework import SecureAgentConfig, get_quarantine_client, set_quarantine_client
        
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
        from agent_framework import (
            quarantined_llm, 
            set_quarantine_client, 
            get_quarantine_client,
            LabelTrackingFunctionMiddleware,
            ContentLabel,
            IntegrityLabel,
        )
        from agent_framework._security_middleware import _current_middleware
        from unittest.mock import AsyncMock, MagicMock
        
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
            "Some email content with [INJECTION ATTEMPT]",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Summarize this email",
                variable_ids=[var_id]
            )
            
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
            assert call_args.kwargs.get("tool_choice") == "none"
            
            # Since it's untrusted and auto_hide is True, result should be hidden
            assert result["auto_hidden"] is True
            assert "variable_id" in result
            
        finally:
            _current_middleware.instance = None
            set_quarantine_client(None)
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_fallback_without_client(self):
        """Test that quarantined_llm falls back to placeholder without client."""
        from agent_framework import (
            quarantined_llm, 
            set_quarantine_client,
            LabelTrackingFunctionMiddleware,
            ContentLabel,
            IntegrityLabel,
        )
        from agent_framework._security_middleware import _current_middleware
        
        # Clear the client
        set_quarantine_client(None)
        
        middleware = LabelTrackingFunctionMiddleware()
        var_id = middleware.get_variable_store().store(
            "Some content",
            ContentLabel(integrity=IntegrityLabel.TRUSTED)  # Use trusted to see response directly
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Process this content",
                variable_ids=[var_id],
                auto_hide_result=False  # Disable auto-hide to see the response
            )
            
            # Should use placeholder response
            assert "response" in result
            assert "[Quarantined LLM Response] Processed:" in result["response"]
            
        finally:
            _current_middleware.instance = None
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_handles_client_error(self):
        """Test that quarantined_llm handles client errors gracefully."""
        from agent_framework import (
            quarantined_llm, 
            set_quarantine_client,
            LabelTrackingFunctionMiddleware,
            ContentLabel,
            IntegrityLabel,
        )
        from agent_framework._security_middleware import _current_middleware
        from unittest.mock import AsyncMock, MagicMock
        
        # Create a mock client that raises an error
        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(side_effect=Exception("API Error"))
        
        set_quarantine_client(mock_client)
        
        middleware = LabelTrackingFunctionMiddleware()
        var_id = middleware.get_variable_store().store(
            "Some content",
            ContentLabel(integrity=IntegrityLabel.TRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            result = await quarantined_llm(
                prompt="Process this",
                variable_ids=[var_id],
                auto_hide_result=False
            )
            
            # Should fall back to error message
            assert "response" in result
            assert "[Quarantined LLM Error]" in result["response"]
            assert "API Error" in result["response"]
            
        finally:
            _current_middleware.instance = None
            set_quarantine_client(None)
    
    @pytest.mark.asyncio
    async def test_quarantined_llm_builds_correct_messages(self):
        """Test that quarantined_llm builds messages correctly with content."""
        from agent_framework import (
            quarantined_llm, 
            set_quarantine_client,
            LabelTrackingFunctionMiddleware,
            ContentLabel,
            IntegrityLabel,
        )
        from agent_framework._security_middleware import _current_middleware
        from unittest.mock import AsyncMock, MagicMock
        
        mock_response = MagicMock()
        mock_response.text = "Summary"
        
        mock_client = MagicMock()
        mock_client.get_response = AsyncMock(return_value=mock_response)
        
        set_quarantine_client(mock_client)
        
        middleware = LabelTrackingFunctionMiddleware()
        
        # Store multiple pieces of content
        var1 = middleware.get_variable_store().store(
            "Email 1: Hello world",
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        var2 = middleware.get_variable_store().store(
            {"subject": "Test", "body": "Content"},  # Dict content
            ContentLabel(integrity=IntegrityLabel.UNTRUSTED)
        )
        
        _current_middleware.instance = middleware
        
        try:
            await quarantined_llm(
                prompt="Summarize both emails",
                variable_ids=[var1, var2]
            )
            
            # Check the user message includes both pieces of content
            call_args = mock_client.get_response.call_args
            messages = call_args.kwargs.get("messages") or call_args.args[0]
            user_message = messages[1].text
            
            assert "Summarize both emails" in user_message
            assert "Retrieved Content" in user_message
            assert "Email 1: Hello world" in user_message
            assert '"subject": "Test"' in user_message  # Dict should be JSON serialized
            
        finally:
            _current_middleware.instance = None
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
        
        function = FunctionTool(
            fn=mock_fn,
            name="fetch_items",
            description="Fetch items",
            args_schema=MockArgs
        )
        return function
    
    @pytest.mark.asyncio
    async def test_mixed_trust_items_in_list(self, middleware, mock_function):
        """Test that untrusted items are hidden while trusted items remain visible."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            # Return list with mixed trust items
            context.result = [
                {
                    "id": 1,
                    "content": "trusted content",
                    "additional_properties": {
                        "security_label": {"integrity": "trusted", "confidentiality": "public"}
                    }
                },
                {
                    "id": 2,
                    "content": "untrusted content with [INJECTION]",
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                    }
                },
                {
                    "id": 3,
                    "content": "another trusted item",
                    "additional_properties": {
                        "security_label": {"integrity": "trusted", "confidentiality": "public"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert isinstance(result, list)
        assert len(result) == 3
        
        # First item should be visible (trusted)
        assert isinstance(result[0], dict)
        assert result[0]["id"] == 1
        assert result[0]["content"] == "trusted content"
        
        # Second item should be hidden (untrusted) - replaced with serialized VariableReferenceContent dict
        assert isinstance(result[1], dict)
        assert result[1].get("type") == "variable_reference"
        assert result[1]["security_label"]["integrity"] == "untrusted"
        
        # Third item should be visible (trusted)
        assert isinstance(result[2], dict)
        assert result[2]["id"] == 3
    
    @pytest.mark.asyncio
    async def test_all_trusted_items_visible(self, middleware, mock_function):
        """Test that all trusted items remain fully visible."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = [
                {
                    "id": 1,
                    "data": "safe data 1",
                    "additional_properties": {
                        "security_label": {"integrity": "trusted", "confidentiality": "public"}
                    }
                },
                {
                    "id": 2,
                    "data": "safe data 2",
                    "additional_properties": {
                        "security_label": {"integrity": "trusted", "confidentiality": "public"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert len(result) == 2
        # Both should be visible dicts
        assert isinstance(result[0], dict)
        assert isinstance(result[1], dict)
        assert result[0]["data"] == "safe data 1"
        assert result[1]["data"] == "safe data 2"
    
    @pytest.mark.asyncio
    async def test_all_untrusted_items_hidden(self, middleware, mock_function):
        """Test that all untrusted items are hidden."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = [
                {
                    "id": 1,
                    "data": "unsafe [INJECTION]",
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                    }
                },
                {
                    "id": 2,
                    "data": "also unsafe",
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert len(result) == 2
        # Both should be serialized VariableReferenceContent dicts
        assert isinstance(result[0], dict) and result[0].get("type") == "variable_reference"
        assert isinstance(result[1], dict) and result[1].get("type") == "variable_reference"
    
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
        
        args = untrusted_function.args_schema()
        context = FunctionInvocationContext(
            function=untrusted_function,
            arguments=args
        )
        
        async def next_fn():
            # Items without additional_properties.security_label
            context.result = [
                {"id": 1, "data": "no label here"},
                {"id": 2, "data": "also no label"},
            ]
        
        await middleware.process(context, next_fn)
        
        # Without embedded labels, the entire result is hidden because
        # the fallback label is UNTRUSTED (from tool's default source_integrity)
        # This is the backward-compatible behavior for tools that don't use per-item labels
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert isinstance(result, dict)
        assert result.get("type") == "variable_reference"
        assert result["security_label"]["integrity"] == "untrusted"
        
        # The call/result label should be UNTRUSTED
        label = context.metadata.get("security_label")
        assert label.integrity == IntegrityLabel.UNTRUSTED
    
    @pytest.mark.asyncio
    async def test_nested_dict_with_labeled_items(self, middleware, mock_function):
        """Test nested structure with labeled items inside a dict."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = {
                "emails": [
                    {
                        "id": 1,
                        "body": "safe",
                        "additional_properties": {
                            "security_label": {"integrity": "trusted", "confidentiality": "public"}
                        }
                    },
                    {
                        "id": 2,
                        "body": "unsafe [INJECTION]",
                        "additional_properties": {
                            "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                        }
                    },
                ],
                "count": 2,
            }
        
        await middleware.process(context, next_fn)
        
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert "emails" in result
        assert result["count"] == 2
        
        emails = result["emails"]
        assert len(emails) == 2
        # First email visible, second hidden
        assert isinstance(emails[0], dict)
        assert emails[0]["body"] == "safe"
        assert isinstance(emails[1], dict) and emails[1].get("type") == "variable_reference"
    
    @pytest.mark.asyncio
    async def test_combined_label_reflects_all_items(self, middleware, mock_function):
        """Test that combined label is most restrictive across all items."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = [
                {
                    "id": 1,
                    "additional_properties": {
                        "security_label": {"integrity": "trusted", "confidentiality": "public"}
                    }
                },
                {
                    "id": 2,
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "private"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        # Combined label should be UNTRUSTED (most restrictive integrity)
        # and PRIVATE (most restrictive confidentiality)
        label = context.metadata.get("security_label")
        assert label.integrity == IntegrityLabel.UNTRUSTED
        assert label.confidentiality == ConfidentialityLabel.PRIVATE
    
    @pytest.mark.asyncio
    async def test_hidden_items_stored_in_variable_store(self, middleware, mock_function):
        """Test that hidden items can be retrieved from the variable store."""
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = [
                {
                    "id": 1,
                    "secret": "hidden data",
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        # Get the variable reference
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        var_ref = result[0]
        assert isinstance(var_ref, dict)
        assert var_ref.get("type") == "variable_reference"
        
        # Retrieve from store
        store = middleware.get_variable_store()
        content, label = store.retrieve(var_ref["variable_id"])
        
        # Should have the original content
        assert content["id"] == 1
        assert content["secret"] == "hidden data"
        assert label.integrity == IntegrityLabel.UNTRUSTED
    
    @pytest.mark.asyncio
    async def test_auto_hide_disabled_shows_all_items(self, mock_function):
        """Test that with auto_hide_untrusted=False, all items are visible."""
        middleware = LabelTrackingFunctionMiddleware(auto_hide_untrusted=False)
        
        args = mock_function.args_schema()
        context = FunctionInvocationContext(
            function=mock_function,
            arguments=args
        )
        
        async def next_fn():
            context.result = [
                {
                    "id": 1,
                    "data": "untrusted but visible",
                    "additional_properties": {
                        "security_label": {"integrity": "untrusted", "confidentiality": "public"}
                    }
                },
            ]
        
        await middleware.process(context, next_fn)
        
        # Item should NOT be hidden even though untrusted
        result = json.loads(context.result) if isinstance(context.result, str) else context.result
        assert isinstance(result[0], dict)
        assert result[0]["data"] == "untrusted but visible"


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
        return PolicyEnforcementFunctionMiddleware(
            block_on_violation=True
        )
    
    @pytest.fixture
    def create_function_with_max_confidentiality(self):
        """Factory to create mock function with max_allowed_confidentiality."""
        def _create(name: str, max_conf: str):
            class MockArgs(BaseModel):
                arg: str = "default"
            
            async def mock_fn(arg: str = "default") -> str:
                return f"result: {arg}"
            
            function = FunctionTool(
                fn=mock_fn,
                name=name,
                description=f"Function with max_allowed_confidentiality={max_conf}",
                args_schema=MockArgs,
                additional_properties={"max_allowed_confidentiality": max_conf}
            )
            return function
        return _create
    
    @pytest.mark.asyncio
    async def test_public_data_allowed_to_public_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PUBLIC data can be written to PUBLIC destination."""
        # Context is PUBLIC
        label_middleware._update_context_label(ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.PUBLIC
        ))
        
        function = create_function_with_max_confidentiality("send_public", "public")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "sent"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be allowed
        assert context.result == "sent"
        assert not getattr(context, 'terminate', False)
    
    @pytest.mark.asyncio
    async def test_private_data_blocked_from_public_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PRIVATE data cannot be written to PUBLIC destination (data exfiltration blocked)."""
        # Context contains PRIVATE data
        label_middleware._update_context_label(ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        ))
        
        function = create_function_with_max_confidentiality("send_to_public", "public")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "should not reach"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be blocked
        assert getattr(context, "terminate", False) is True
        assert "error" in context.result
        assert "exfiltration" in context.result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_user_identity_data_blocked_from_private_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test USER_IDENTITY data cannot be written to PRIVATE destination."""
        # Context contains USER_IDENTITY data
        label_middleware._update_context_label(ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.USER_IDENTITY
        ))
        
        function = create_function_with_max_confidentiality("send_to_private", "private")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "should not reach"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be blocked
        assert getattr(context, "terminate", False) is True
        assert "error" in context.result
    
    @pytest.mark.asyncio
    async def test_private_data_allowed_to_private_destination(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test PRIVATE data can be written to PRIVATE destination."""
        # Context contains PRIVATE data
        label_middleware._update_context_label(ContentLabel(
            integrity=IntegrityLabel.TRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        ))
        
        function = create_function_with_max_confidentiality("send_to_private", "private")
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "sent to private"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be allowed
        assert context.result == "sent to private"
        assert not getattr(context, 'terminate', False)
    
    @pytest.mark.asyncio
    async def test_combined_integrity_and_confidentiality_violation(
        self, label_middleware, policy_middleware, create_function_with_max_confidentiality
    ):
        """Test that both integrity AND confidentiality violations are detected."""
        # Context is UNTRUSTED + PRIVATE
        label_middleware._update_context_label(ContentLabel(
            integrity=IntegrityLabel.UNTRUSTED,
            confidentiality=ConfidentialityLabel.PRIVATE
        ))
        
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
                "max_allowed_confidentiality": "public"  # Rejects private data
            }
        )
        
        args = function.args_schema()
        context = FunctionInvocationContext(function=function, arguments=args)
        
        context.metadata["security_label"] = ContentLabel(integrity=IntegrityLabel.TRUSTED)
        context.metadata["context_label"] = label_middleware.get_context_label()
        
        async def next_fn():
            context.result = "should not reach"
        
        await policy_middleware.process(context, next_fn)
        
        # Should be blocked (either violation should block)
        assert getattr(context, "terminate", False) is True
        assert "error" in context.result


class TestCheckConfidentialityAllowed:
    """Tests for check_confidentiality_allowed helper function."""
    
    def test_public_to_public_allowed(self):
        """Test PUBLIC data can be written to PUBLIC destination."""
        from agent_framework import check_confidentiality_allowed
        
        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PUBLIC) is True
    
    def test_public_to_private_allowed(self):
        """Test PUBLIC data can be written to PRIVATE destination."""
        from agent_framework import check_confidentiality_allowed
        
        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.PRIVATE) is True
    
    def test_public_to_user_identity_allowed(self):
        """Test PUBLIC data can be written to USER_IDENTITY destination."""
        from agent_framework import check_confidentiality_allowed
        
        public_label = ContentLabel(confidentiality=ConfidentialityLabel.PUBLIC)
        assert check_confidentiality_allowed(public_label, ConfidentialityLabel.USER_IDENTITY) is True
    
    def test_private_to_public_blocked(self):
        """Test PRIVATE data cannot be written to PUBLIC destination."""
        from agent_framework import check_confidentiality_allowed
        
        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PUBLIC) is False
    
    def test_private_to_private_allowed(self):
        """Test PRIVATE data can be written to PRIVATE destination."""
        from agent_framework import check_confidentiality_allowed
        
        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.PRIVATE) is True
    
    def test_private_to_user_identity_allowed(self):
        """Test PRIVATE data can be written to USER_IDENTITY destination."""
        from agent_framework import check_confidentiality_allowed
        
        private_label = ContentLabel(confidentiality=ConfidentialityLabel.PRIVATE)
        assert check_confidentiality_allowed(private_label, ConfidentialityLabel.USER_IDENTITY) is True
    
    def test_user_identity_to_public_blocked(self):
        """Test USER_IDENTITY data cannot be written to PUBLIC destination."""
        from agent_framework import check_confidentiality_allowed
        
        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.PUBLIC) is False
    
    def test_user_identity_to_private_blocked(self):
        """Test USER_IDENTITY data cannot be written to PRIVATE destination."""
        from agent_framework import check_confidentiality_allowed
        
        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.PRIVATE) is False
    
    def test_user_identity_to_user_identity_allowed(self):
        """Test USER_IDENTITY data can be written to USER_IDENTITY destination."""
        from agent_framework import check_confidentiality_allowed
        
        ui_label = ContentLabel(confidentiality=ConfidentialityLabel.USER_IDENTITY)
        assert check_confidentiality_allowed(ui_label, ConfidentialityLabel.USER_IDENTITY) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
