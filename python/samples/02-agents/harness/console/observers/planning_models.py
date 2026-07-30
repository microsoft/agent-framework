# Copyright (c) Microsoft. All rights reserved.

"""Pydantic models for structured planning output.

These models define the JSON schema that the agent produces when in planning
mode via `response_format`. The schema enables consistent rendering of
clarification questions and approval requests in the console UI.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PlanningResponseType(str, Enum):
    """Type of planning response from the agent."""

    CLARIFICATION = "clarification"
    """The agent needs clarification and presents options for the user to choose from."""

    APPROVAL = "approval"
    """The agent is seeking approval to proceed with execution."""


class PlanningQuestion(BaseModel):
    """A single question or item within a PlanningResponse.

    For clarification: contains the question text and optional choices.
    For approval: contains the plan summary for the user to approve.
    """

    message: str = Field(
        description=(
            "For clarifications, this has the question that needs to be clarified "
            "with the user. For approvals, this would contain a summary of the "
            "execution plan that the user needs to approve."
        ),
    )
    choices: list[str] | None = Field(
        default=None,
        description=(
            "For clarifications, this has a list of options that the user can "
            "choose from. null for approvals.\n\n"
            "Note: for clarifications, the user will always also be presented with "
            "a free form input option, so make sure that each choice provided here "
            "is a valid input for the next turn.\n"
            'E.g. if the question is "Which stock are you referring to?" then valid '
            'choices might be ["AAPL", "MSFT", "GOOG"], and the user could also type '
            "their own answer.\n"
            'Invalid choices would be ["Enter tickers directly", "Paste tickers"], '
            "since these conflict with the already existing freeform option, and "
            "don't directly provide valid inputs for the next turn."
        ),
    )


class PlanningResponse(BaseModel):
    """Structured response from the agent while in planning mode.

    Used with structured output (`response_format`) to enable consistent
    rendering of clarification questions and approval requests.
    """

    type: PlanningResponseType = Field(
        description=(
            "Use 'clarification' when you need clarification around the user "
            "request and you want to present the user with options to choose from. "
            "Use 'approval' when you are ready to start execution, but need "
            "approval to start executing."
        ),
    )
    questions: list[PlanningQuestion] = Field(
        description=(
            "For clarifications, this has one or more questions to ask the user "
            "(each with choices). For approvals, this has exactly one item "
            "containing the plan summary for the user to approve."
        ),
    )
