# Copyright (c) Microsoft. All rights reserved.
from agent_framework_purview import PurviewSettings


def test_settings_defaults():
    s = PurviewSettings(app_name="x")
    assert s.app_name == "x"
    assert s.graph_base_uri.startswith("https://graph.microsoft.com")
