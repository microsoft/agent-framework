# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Teams channel for :mod:`agent_framework_hosting`.

Built on the official ``microsoft-teams-apps`` SDK (microsoft/teams.py).
Surfaces Teams-native affordances on top of Azure Bot Service: streaming
via :class:`~microsoft_teams.apps.HttpStream`, Adaptive Cards (via an
outbound transform hook), citations, and message-feedback callbacks.
"""

from ._channel import (
    TeamsChannel,
    TeamsCitation,
    TeamsFeedbackContext,
    TeamsFeedbackHandler,
    TeamsOutboundContext,
    TeamsOutboundPayload,
    TeamsOutboundTransform,
    teams_isolation_key,
)

__all__ = [
    "TeamsChannel",
    "TeamsCitation",
    "TeamsFeedbackContext",
    "TeamsFeedbackHandler",
    "TeamsOutboundContext",
    "TeamsOutboundPayload",
    "TeamsOutboundTransform",
    "teams_isolation_key",
]
