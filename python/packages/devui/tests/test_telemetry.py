# Copyright (c) Microsoft. All rights reserved.

"""Tests for telemetry configuration and functionality."""

import os
from unittest.mock import Mock, patch

import pytest

from agent_framework_devui import AgentFrameworkDebugServer
from agent_framework_devui._execution import ExecutionEngine

# Import shared test utilities
from .test_utils import MockAgent, create_mock_workflow


class TestTelemetryConfiguration:
    """Test telemetry configuration parsing and application."""

    def test_telemetry_none_mode(self):
        """Test that 'none' mode disables all telemetry."""
        server = AgentFrameworkDebugServer(telemetry_mode="none", include_sensitive_data=False)
        
        assert server.telemetry_config['enable_framework_traces'] is False
        assert server.telemetry_config['enable_workflow_traces'] is False
        assert server.telemetry_config['enable_sensitive_data'] is False

    def test_telemetry_framework_mode(self):
        """Test that 'framework' mode enables only framework traces."""
        server = AgentFrameworkDebugServer(telemetry_mode="framework", include_sensitive_data=False)
        
        assert server.telemetry_config['enable_framework_traces'] is True
        assert server.telemetry_config['enable_workflow_traces'] is False
        assert server.telemetry_config['enable_sensitive_data'] is False

    def test_telemetry_workflow_mode(self):
        """Test that 'workflow' mode enables only workflow traces."""
        server = AgentFrameworkDebugServer(telemetry_mode="workflow", include_sensitive_data=False)
        
        assert server.telemetry_config['enable_framework_traces'] is False
        assert server.telemetry_config['enable_workflow_traces'] is True
        assert server.telemetry_config['enable_sensitive_data'] is False

    def test_telemetry_all_mode(self):
        """Test that 'all' mode enables all traces."""
        server = AgentFrameworkDebugServer(telemetry_mode="all", include_sensitive_data=False)
        
        assert server.telemetry_config['enable_framework_traces'] is True
        assert server.telemetry_config['enable_workflow_traces'] is True
        assert server.telemetry_config['enable_sensitive_data'] is False

    def test_sensitive_data_flag(self):
        """Test that sensitive data flag works correctly."""
        server = AgentFrameworkDebugServer(telemetry_mode="framework", include_sensitive_data=True)
        
        assert server.telemetry_config['enable_framework_traces'] is True
        assert server.telemetry_config['enable_workflow_traces'] is False
        assert server.telemetry_config['enable_sensitive_data'] is True

    def test_environment_variables_set(self):
        """Test that environment variables are set correctly."""
        # Clear any existing env vars
        original_otel = os.environ.get('AGENT_FRAMEWORK_ENABLE_OTEL')
        original_workflow = os.environ.get('AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL')
        original_sensitive = os.environ.get('AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA')
        
        try:
            # Remove env vars to test clean slate
            for var in ['AGENT_FRAMEWORK_ENABLE_OTEL', 'AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL', 'AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA']:
                if var in os.environ:
                    del os.environ[var]
            
            # Test 'all' mode with sensitive data
            server = AgentFrameworkDebugServer(telemetry_mode="all", include_sensitive_data=True)
            
            # Check environment variables were set
            assert os.environ.get('AGENT_FRAMEWORK_ENABLE_OTEL') == 'true'
            assert os.environ.get('AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL') == 'true'
            assert os.environ.get('AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA') == 'true'
            
        finally:
            # Restore original env vars
            if original_otel is not None:
                os.environ['AGENT_FRAMEWORK_ENABLE_OTEL'] = original_otel
            elif 'AGENT_FRAMEWORK_ENABLE_OTEL' in os.environ:
                del os.environ['AGENT_FRAMEWORK_ENABLE_OTEL']
                
            if original_workflow is not None:
                os.environ['AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL'] = original_workflow
            elif 'AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL' in os.environ:
                del os.environ['AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL']
                
            if original_sensitive is not None:
                os.environ['AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA'] = original_sensitive
            elif 'AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA' in os.environ:
                del os.environ['AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA']

    def test_execution_engine_receives_config(self):
        """Test that ExecutionEngine receives telemetry configuration."""
        server = AgentFrameworkDebugServer(telemetry_mode="workflow", include_sensitive_data=True)
        
        # Check that execution engine has the right config
        assert server.execution_engine.telemetry_config['enable_framework_traces'] is False
        assert server.execution_engine.telemetry_config['enable_workflow_traces'] is True
        assert server.execution_engine.telemetry_config['enable_sensitive_data'] is True

    @pytest.mark.asyncio
    async def test_agent_execution_respects_config(self):
        """Test that agent execution respects telemetry configuration."""
        # Use proper mock agent from shared utilities
        mock_agent = MockAgent("test_agent")
        mock_tracing_manager = Mock()
        
        # Test with framework traces disabled
        execution_engine = ExecutionEngine(telemetry_config={
            'enable_framework_traces': False,
            'enable_workflow_traces': False,
            'enable_sensitive_data': False,
        })
        
        events = []
        async for event in execution_engine.execute_agent_streaming(
            agent=mock_agent,
            message="test message",
            thread_id="test-thread",
            tracing_manager=mock_tracing_manager
        ):
            events.append(event)
        
        # Should have at least a completion event, and possibly agent updates
        assert len(events) >= 1
        assert events[-1].type == "completion"  # Last event should be completion
        
        # If there are agent updates, they should come before completion
        if len(events) > 1:
            for event in events[:-1]:  # All but the last event
                assert event.type == "agent_run_update"
        
        # Main test: Tracing manager should not be set up since framework traces are disabled
        mock_tracing_manager.setup_streaming_tracing.assert_not_called()

    @pytest.mark.asyncio
    async def test_workflow_execution_respects_config(self):
        """Test that workflow execution respects telemetry configuration."""
        # Use proper mock workflow from shared utilities
        mock_workflow = create_mock_workflow("test_workflow")
        mock_tracing_manager = Mock()
        
        # Test with workflow traces disabled
        execution_engine = ExecutionEngine(telemetry_config={
            'enable_framework_traces': False,
            'enable_workflow_traces': False,
            'enable_sensitive_data': False,
        })
        
        events = []
        async for event in execution_engine.execute_workflow_streaming(
            workflow=mock_workflow,
            input_data={"test": "data"},
            tracing_manager=mock_tracing_manager
        ):
            events.append(event)
        
        # Should have workflow structure and completion events
        assert len(events) >= 2
        assert events[0].type == "workflow_structure"
        assert events[-1].type == "completion"
        
        # Tracing manager should not be set up since workflow traces are disabled
        mock_tracing_manager.setup_streaming_tracing.assert_not_called()


def test_debug_function_passes_telemetry_config():
    """Test that the debug() function properly passes telemetry configuration."""
    from agent_framework_devui import debug, DebugServer
    
    # Mock DebugServer to capture arguments
    with patch.object(DebugServer, '__init__', return_value=None) as mock_init:
        with patch.object(DebugServer, 'start') as mock_start:
            # This should fail with mock, but we can check the call
            try:
                debug(
                    agents_dir="test_dir",
                    port=8080,
                    host="localhost",
                    telemetry_mode="workflow",
                    include_sensitive_data=True
                )
            except AttributeError:
                pass  # Expected since we mocked __init__
            
            # Check that DebugServer was called with correct telemetry args
            mock_init.assert_called_once_with(
                agents_dir="test_dir",
                port=8080,
                host="localhost",
                telemetry_mode="workflow",
                include_sensitive_data=True
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])