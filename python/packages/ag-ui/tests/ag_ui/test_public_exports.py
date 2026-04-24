# Copyright (c) Microsoft. All rights reserved.

"""Public export coverage for AG-UI package surfaces."""


def test_agent_framework_ag_ui_exports_workflow() -> None:
    """Runtime package should export AgentFrameworkWorkflow."""
    from agent_framework_ag_ui import AgentFrameworkWorkflow

    assert AgentFrameworkWorkflow.__name__ == "AgentFrameworkWorkflow"


def test_core_ag_ui_lazy_exports_include_only_stable_api() -> None:
    """Core facade should expose only the stable high-level AG-UI API."""
    from agent_framework import ag_ui

    assert hasattr(ag_ui, "AgentFrameworkWorkflow")
    assert hasattr(ag_ui, "AgentFrameworkAgent")
    assert hasattr(ag_ui, "AGUIChatClient")
    assert hasattr(ag_ui, "add_agent_framework_fastapi_endpoint")
    assert hasattr(ag_ui, "state_update")

    assert not hasattr(ag_ui, "WorkflowFactory")
    assert not hasattr(ag_ui, "AGUIRequest")
    assert not hasattr(ag_ui, "RunMetadata")


def test_agent_framework_ag_ui_exports_state_update() -> None:
    """Runtime package should export the ``state_update`` helper."""
    from agent_framework_ag_ui import state_update

    assert callable(state_update)


def test_core_ag_ui_lazy_exports_include_event_converter_and_http_service() -> None:
    """Core facade must expose AGUIEventConverter, AGUIHttpService, and __version__."""
    from agent_framework import ag_ui

    assert hasattr(ag_ui, "AGUIEventConverter")
    assert hasattr(ag_ui, "AGUIHttpService")
    assert hasattr(ag_ui, "__version__")
