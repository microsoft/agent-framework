# Copyright (c) Microsoft. All rights reserved.
import enum

class ReviewResult(enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"

DEFAULT_REVIEW_SYSTEM_PROMPT = """You are a reviewer for an AI agent, please provide feedback on the 
following exchange between a user and the AI agent,
and indicate if the agent's responses are approved or not, if approved return "approved", otherwise return "rejected".\n
Use the following criteria for your evaluation:\n
- Relevance: Does the response address the user's query?\n
- Accuracy: Is the information provided correct?\n
- Clarity: Is the response easy to understand?\n
Provide constructive feedback and suggestions for improvement.\n
Do not approve until all criteria are met."""
# Always reject no matter how."""
