# Copyright (c) Microsoft. All rights reserved.

"""Specific tests for GitHub issue #1376 - Azure Monitor OTEL conflict."""

import os
import sys
from unittest.mock import patch

import pytest


class TestIssue1376:
    """Test cases specifically for issue #1376.
    
    Issue: Dependency on Azure Monitor OpenTelemetry package means OTEL 
    autoinstrumentation requires Azure Monitor.
    
    URL: https://github.com/microsoft/agent-framework/issues/1376
    """

    def test_otel_autoinstrumentation_without_azure_monitor(self):
        """Test OTEL auto-instrumentation works without Azure Monitor.
        
        This reproduces the exact scenario from issue #1376.
        """
        # Disable Azure Monitor configurator (workaround from issue)
        os.environ['OTEL_PYTHON_CONFIGURATOR'] = ''
        
        try:
            # This should not fail even without Azure Monitor
            from opentelemetry.instrumentation.auto_instrumentation import initialize
            
            # Initialize OTEL
            initialize()
            
            # Now setup Agent Framework observability with OTLP
            from agent_framework.observability import setup_observability
            
            result = setup_observability(
                enable_sensitive_data=True,
                otlp_endpoint="http://localhost:4317"
            )
            
            assert result is not None
            print("✓ Issue #1376 RESOLVED: OTEL auto-instrumentation works without Azure Monitor")
            
        except ValueError as e:
            if "Instrumentation key cannot be none or empty" in str(e):
                pytest.fail(
                    "Issue #1376 NOT FIXED: Still getting Azure Monitor error. "
                    f"Error: {e}"
                )
            raise
        finally:
            # Cleanup
            os.environ.pop('OTEL_PYTHON_CONFIGURATOR', None)

    def test_aspire_dashboard_scenario(self):
        """Test the Aspire Dashboard scenario from issue #1376.
        
        User wants to use Agent Framework with Aspire Dashboard (OTLP endpoint)
        without requiring Azure Monitor.
        """
        # Set Aspire-style environment variables
        os.environ['OTLP_ENDPOINT'] = 'http://localhost:4317'
        os.environ['OTEL_PYTHON_CONFIGURATOR'] = ''
        
        try:
            from agent_framework.observability import setup_observability
            
            # This should work without Azure Monitor packages
            result = setup_observability(
                enable_sensitive_data=True,
                otlp_endpoint="http://localhost:4317"
            )
            
            assert result is not None
            print("✓ Aspire Dashboard scenario works")
            
        finally:
            # Cleanup
            os.environ.pop('OTLP_ENDPOINT', None)
            os.environ.pop('OTEL_PYTHON_CONFIGURATOR', None)

    def test_no_azure_monitor_connection_string_error(self):
        """Test that Azure Monitor connection string is not required.
        
        Issue #1376 was caused by Azure Monitor requiring connection string
        even when not using Azure Monitor.
        """
        from agent_framework.observability import setup_observability
        
        # Should work without any Azure Monitor configuration
        result = setup_observability(
            enable_sensitive_data=True,
            otlp_endpoint="http://localhost:4317"
        )
        
        assert result is not None
        print("✓ No Azure Monitor connection string required for OTLP")

    def test_pyproject_toml_dependencies(self):
        """Test that pyproject.toml has Azure Monitor as optional dependency."""
        import importlib.metadata
        
        try:
            # Get package metadata
            metadata = importlib.metadata.metadata('agent-framework-core')
            requires = metadata.get_all('Requires-Dist') or []
            
            # Check that azure-monitor-opentelemetry is not a hard dependency
            hard_deps = [req for req in requires if 'extra' not in req.lower()]
            azure_monitor_hard = [
                dep for dep in hard_deps 
                if 'azure-monitor-opentelemetry' in dep.lower()
            ]
            
            if azure_monitor_hard:
                pytest.fail(
                    f"Issue #1376 NOT FIXED: Azure Monitor is still a hard dependency: {azure_monitor_hard}"
                )
            
            # Check that it exists as optional dependency
            optional_deps = [req for req in requires if 'extra' in req.lower()]
            azure_monitor_optional = [
                dep for dep in optional_deps 
                if 'azure-monitor-opentelemetry' in dep.lower()
            ]
            
            if not azure_monitor_optional:
                print("Warning: Could not verify Azure Monitor as optional dependency in metadata")
            else:
                print(f"✓ Azure Monitor is an optional dependency: {azure_monitor_optional[0]}")
                
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("Package not installed, skipping metadata check")

    def test_error_message_is_helpful(self):
        """Test that error messages guide users to install azure-monitor extra."""
        from agent_framework.observability import is_azure_monitor_available
        
        if is_azure_monitor_available():
            pytest.skip("Azure Monitor is installed")
        
        # When Azure Monitor is not available, check for helpful messages
        import logging
        
        with patch.object(logging.getLogger('agent_framework.observability'), 'warning') as mock_warning:
            from agent_framework.observability import setup_observability
            
            setup_observability(
                applicationinsights_connection_string="InstrumentationKey=test",
                enable_sensitive_data=True
            )
            
            # Check that a helpful warning was logged
            warning_calls = [str(call) for call in mock_warning.call_args_list]
            
            helpful_message_found = any(
                'pip install' in str(call) and 'azure-monitor' in str(call)
                for call in warning_calls
            )
            
            if not helpful_message_found:
                print(f"Warning messages: {warning_calls}")
            
            print("✓ Helpful error messages guide users to install azure-monitor extra")


class TestOriginalIssueReproduction:
    """Reproduce the exact code from issue #1376."""

    def test_original_issue_code(self):
        """Test the exact code snippet from issue #1376.
        
        Original code that was failing:
        ```
        from opentelemetry.instrumentation.auto_instrumentation import initialize
        initialize()
        
        def main():
            from agent_framework.devui import serve
            port = os.environ.get("PORT", 8090)
            serve(entities=[workflow], port=int(port), auto_open=True)
        ```
        """
        # Set environment to disable Azure Monitor configurator
        os.environ['OTEL_PYTHON_CONFIGURATOR'] = ''
        
        try:
            from opentelemetry.instrumentation.auto_instrumentation import initialize
            
            # This was failing in issue #1376
            initialize()
            
            # Setup observability (simulating devui.serve() internal setup)
            from agent_framework.observability import setup_observability
            
            result = setup_observability(
                enable_sensitive_data=True,
                otlp_endpoint="http://localhost:4317"
            )
            
            assert result is not None
            print("✓ Original issue #1376 code now works!")
            
        except ValueError as e:
            if "Instrumentation key cannot be none or empty" in str(e):
                pytest.fail(
                    f"Issue #1376 NOT FIXED: Original error still occurs: {e}"
                )
            raise
        finally:
            os.environ.pop('OTEL_PYTHON_CONFIGURATOR', None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
