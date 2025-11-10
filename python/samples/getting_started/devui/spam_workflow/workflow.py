# Copyright (c) Microsoft. All rights reserved.

"""Spam Detection Workflow Sample for DevUI.

The following sample demonstrates a comprehensive 4-step workflow with multiple executors
that process, detect spam, and handle email messages. This workflow illustrates
complex branching logic with human-in-the-loop approval and realistic processing delays.

Workflow Steps:
1. Email Preprocessor - Cleans and prepares the email
2. Spam Detector - Analyzes content and determines if the message is spam (with human approval)
3a. Spam Handler - Processes spam messages (quarantine, log, remove)
3b. Message Responder - Handles legitimate messages (validate, respond)
4. Final Processor - Completes the workflow with logging and cleanup
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Annotated

from agent_framework import (
    Case,
    Default,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from pydantic import BaseModel, Field
from typing_extensions import Never

# Define response model with clear user guidance
class SpamDecision(BaseModel):
    """User's decision on whether the email is spam."""
    decision: Literal["spam", "not spam"] = Field(
        description="Enter 'spam' to mark as spam, or 'not spam' to mark as legitimate"
    )


@dataclass
class EmailContent:
    """A data class to hold the processed email content."""

    original_message: str
    cleaned_message: str
    word_count: int
    has_suspicious_patterns: bool = False


@dataclass
class SpamDetectorResponse:
    """A data class to hold the spam detection results."""

    email_content: EmailContent
    is_spam: bool = False
    confidence_score: float = 0.0
    spam_reasons: list[str] | None = None
    human_reviewed: bool = False
    human_decision: str | None = None
    ai_original_classification: bool = False

    def __post_init__(self):
        """Initialize spam_reasons list if None."""
        if self.spam_reasons is None:
            self.spam_reasons = []


@dataclass
class SpamApprovalRequest:
    """Human-in-the-loop approval request for spam classification."""

    email_message: str = ""
    detected_as_spam: bool = False
    confidence: float = 0.0
    reasons: str = ""


@dataclass
class ProcessingResult:
    """A data class to hold the final processing result."""

    original_message: str
    action_taken: str
    processing_time: float
    status: str
    is_spam: bool
    confidence_score: float
    spam_reasons: list[str]
    was_human_reviewed: bool = False
    human_override: str | None = None
    ai_original_decision: bool = False


class EmailRequest(BaseModel):
    """Request model for email processing."""

    email: str = Field(
        description="The email message to be processed.",
        default="Hi there, are you interested in our new urgent offer today? Click here!",
    )


class EmailPreprocessor(Executor):
    """Step 1: An executor that preprocesses and cleans email content."""

    @handler
    async def handle_email(self, email: EmailRequest, ctx: WorkflowContext[EmailContent]) -> None:
        """Clean and preprocess the email message."""
        await asyncio.sleep(1.5)  # Simulate preprocessing time

        # Simulate email cleaning
        cleaned = email.email.strip().lower()
        word_count = len(email.email.split())

        # Check for suspicious patterns
        suspicious_patterns = ["urgent", "limited time", "act now", "free money"]
        has_suspicious = any(pattern in cleaned for pattern in suspicious_patterns)

        result = EmailContent(
            original_message=email.email,
            cleaned_message=cleaned,
            word_count=word_count,
            has_suspicious_patterns=has_suspicious,
        )

        await ctx.send_message(result)




class SpamDetector(Executor):
    """Step 2: An executor that analyzes content and determines if a message is spam."""

    def __init__(self, spam_keywords: list[str], id: str):
        """Initialize the executor with spam keywords."""
        super().__init__(id=id)
        self._spam_keywords = spam_keywords

    @handler
    async def handle_email_content(self, email_content: EmailContent, ctx: WorkflowContext[SpamApprovalRequest]) -> None:
        """Analyze email content and determine if the message is spam, then request human approval."""
        await asyncio.sleep(2.0)  # Simulate analysis and detection time

        email_text = email_content.cleaned_message

        # Analyze content for risk indicators
        contains_links = "http" in email_text or "www" in email_text
        has_attachments = "attachment" in email_text
        sentiment_score = 0.5 if email_content.has_suspicious_patterns else 0.8

        # Build risk indicators
        risk_indicators: list[str] = []
        if email_content.has_suspicious_patterns:
            risk_indicators.append("suspicious_language")
        if contains_links:
            risk_indicators.append("contains_links")
        if has_attachments:
            risk_indicators.append("has_attachments")
        if email_content.word_count < 10:
            risk_indicators.append("too_short")

        # Check for spam keywords
        keyword_matches = [kw for kw in self._spam_keywords if kw in email_text]

        # Calculate spam probability
        spam_score = 0.0
        spam_reasons: list[str] = []

        if keyword_matches:
            spam_score += 0.4
            spam_reasons.append(f"spam_keywords: {keyword_matches}")

        if email_content.has_suspicious_patterns:
            spam_score += 0.3
            spam_reasons.append("suspicious_patterns")

        if len(risk_indicators) >= 3:
            spam_score += 0.2
            spam_reasons.append("high_risk_indicators")

        if sentiment_score < 0.4:
            spam_score += 0.1
            spam_reasons.append("negative_sentiment")

        is_spam = spam_score >= 0.5

        # Store detection result in executor state for later use
        # Store minimal data needed (not complex objects that don't serialize well)
        await ctx.set_executor_state({
            "original_message": email_content.original_message,
            "cleaned_message": email_content.cleaned_message,
            "word_count": email_content.word_count,
            "has_suspicious_patterns": email_content.has_suspicious_patterns,
            "is_spam": is_spam,
            "ai_original_classification": is_spam,  # Store original AI decision
            "confidence_score": spam_score,
            "spam_reasons": spam_reasons
        })

        # Request human approval before proceeding using new API
        approval_request = SpamApprovalRequest(
            email_message=email_text[:200],  # First 200 chars
            detected_as_spam=is_spam,
            confidence=spam_score,
            reasons=", ".join(spam_reasons) if spam_reasons else "no specific reasons"
        )

        await ctx.request_info(
            request_data=approval_request,
            response_type=SpamDecision,
        )

    @response_handler
    async def handle_human_response(
        self,
        original_request: SpamApprovalRequest,
        response: SpamDecision,
        ctx: WorkflowContext[SpamDetectorResponse]
    ) -> None:
        """Process human approval response and continue workflow."""
        print(f"[SpamDetector] handle_human_response called with response: {response}")

        # Get stored detection result
        state = await ctx.get_executor_state() or {}
        print(f"[SpamDetector] Retrieved state: {state}")
        ai_original = state.get("ai_original_classification", False)
        confidence_score = state.get("confidence_score", 0.0)
        spam_reasons = state.get("spam_reasons", [])

        # Parse human decision from the response model
        human_decision = response.decision.strip().lower()

        # Determine final classification based on human input
        if human_decision in ["not spam"]:
            is_spam = False
        elif human_decision in ["spam"]:
            is_spam = True
        else:
            # Default to AI decision if unclear
            is_spam = ai_original

        # Reconstruct EmailContent from stored primitives
        email_content = EmailContent(
            original_message=state.get("original_message", ""),
            cleaned_message=state.get("cleaned_message", ""),
            word_count=state.get("word_count", 0),
            has_suspicious_patterns=state.get("has_suspicious_patterns", False)
        )

        result = SpamDetectorResponse(
            email_content=email_content,
            is_spam=is_spam,
            confidence_score=confidence_score,
            spam_reasons=spam_reasons,
            human_reviewed=True,
            human_decision=response.decision,
            ai_original_classification=ai_original
        )

        print(f"[SpamDetector] Sending SpamDetectorResponse: is_spam={is_spam}, confidence={confidence_score}, human_reviewed=True")
        await ctx.send_message(result)
        print(f"[SpamDetector] Message sent successfully")


class SpamHandler(Executor):
    """Step 3a: An executor that handles spam messages with quarantine and logging."""

    @handler
    async def handle_spam_detection(
        self,
        spam_result: SpamDetectorResponse,
        ctx: WorkflowContext[ProcessingResult],
    ) -> None:
        """Handle spam messages by quarantining and logging."""
        if not spam_result.is_spam:
            raise RuntimeError("Message is not spam, cannot process with spam handler.")

        await asyncio.sleep(2.2)  # Simulate spam handling time

        result = ProcessingResult(
            original_message=spam_result.email_content.original_message,
            action_taken="quarantined_and_logged",
            processing_time=2.2,
            status="spam_handled",
            is_spam=spam_result.is_spam,
            confidence_score=spam_result.confidence_score,
            spam_reasons=spam_result.spam_reasons or [],
            was_human_reviewed=spam_result.human_reviewed,
            human_override=spam_result.human_decision,
            ai_original_decision=spam_result.ai_original_classification,
        )

        await ctx.send_message(result)


class LegitimateMessageHandler(Executor):
    """Step 3b: An executor that handles legitimate (non-spam) messages."""

    @handler
    async def handle_spam_detection(
        self,
        spam_result: SpamDetectorResponse,
        ctx: WorkflowContext[ProcessingResult],
    ) -> None:
        """Respond to legitimate messages."""
        if spam_result.is_spam:
            raise RuntimeError("Message is spam, cannot respond with message responder.")

        await asyncio.sleep(2.5)  # Simulate response time

        result = ProcessingResult(
            original_message=spam_result.email_content.original_message,
            action_taken="delivered_to_inbox",
            processing_time=2.5,
            status="message_processed",
            is_spam=spam_result.is_spam,
            confidence_score=spam_result.confidence_score,
            spam_reasons=spam_result.spam_reasons or [],
            was_human_reviewed=spam_result.human_reviewed,
            human_override=spam_result.human_decision,
            ai_original_decision=spam_result.ai_original_classification,
        )

        await ctx.send_message(result)


class FinalProcessor(Executor):
    """Step 4: An executor that completes the workflow with final logging and cleanup."""

    @handler
    async def handle_processing_result(
        self,
        result: ProcessingResult,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Complete the workflow with final processing and logging."""
        await asyncio.sleep(1.5)  # Simulate final processing time

        total_time = result.processing_time + 1.5

        # Build classification status with human review info
        classification = "SPAM" if result.is_spam else "LEGITIMATE"

        # Add human review context
        review_status = ""
        if result.was_human_reviewed:
            if result.ai_original_decision != result.is_spam:
                review_status = " (human-overridden)"
            else:
                review_status = " (human-verified)"

        # Build appropriate message based on classification
        if result.is_spam:
            # For spam messages
            spam_indicators = ", ".join(result.spam_reasons) if result.spam_reasons else "none detected"

            if result.was_human_reviewed:
                ai_status = "SPAM" if result.ai_original_decision else "LEGITIMATE"
                human_decision = result.human_override if result.human_override else "unknown"

                completion_message = (
                    f"Email classified as {classification}{review_status}.\n"
                    f"AI detected: {ai_status} (confidence: {result.confidence_score:.2f})\n"
                    f"Human reviewer: {human_decision}\n"
                    f"Spam indicators: {spam_indicators}\n"
                    f"Action: Message quarantined for review\n"
                    f"Processing time: {total_time:.1f}s"
                )
            else:
                completion_message = (
                    f"Email classified as {classification} (confidence: {result.confidence_score:.2f}).\n"
                    f"Spam indicators: {spam_indicators}\n"
                    f"Action: Message quarantined for review\n"
                    f"Processing time: {total_time:.1f}s"
                )
        else:
            # For legitimate messages
            if result.was_human_reviewed:
                ai_status = "SPAM" if result.ai_original_decision else "LEGITIMATE"
                human_decision = result.human_override if result.human_override else "unknown"

                completion_message = (
                    f"Email classified as {classification}{review_status}.\n"
                    f"AI detected: {ai_status} (confidence: {result.confidence_score:.2f})\n"
                    f"Human reviewer: {human_decision}\n"
                    f"Action: Delivered to inbox\n"
                    f"Processing time: {total_time:.1f}s"
                )
            else:
                completion_message = (
                    f"Email classified as {classification} (confidence: {result.confidence_score:.2f}).\n"
                    f"Action: Delivered to inbox\n"
                    f"Processing time: {total_time:.1f}s"
                )

        await ctx.yield_output(completion_message)


# DevUI will provide checkpoint storage automatically via the new workflow API
# No need to create checkpoint storage here anymore!

# Create the workflow instance that DevUI can discover
spam_keywords = ["spam", "advertisement", "offer", "click here", "winner", "congratulations", "urgent"]

# Create all the executors for the 4-step workflow
email_preprocessor = EmailPreprocessor(id="email_preprocessor")
spam_detector = SpamDetector(spam_keywords, id="spam_detector")
spam_handler = SpamHandler(id="spam_handler")
legitimate_message_handler = LegitimateMessageHandler(id="legitimate_message_handler")
final_processor = FinalProcessor(id="final_processor")

# Build the comprehensive 4-step workflow with branching logic and HIL support
# Note: No .with_checkpointing() call - DevUI will pass checkpoint_storage at runtime
workflow = (
    WorkflowBuilder(
        name="Email Spam Detector",
        description="4-step email classification workflow with human-in-the-loop spam approval",
    )
    .set_start_executor(email_preprocessor)
    .add_edge(email_preprocessor, spam_detector)
    # HIL handled within spam_detector via @response_handler
    # Continue with branching logic after human approval
    # Only route SpamDetectorResponse messages (not SpamApprovalRequest)
    .add_switch_case_edge_group(
        spam_detector,
        [
            Case(condition=lambda x: isinstance(x, SpamDetectorResponse) and x.is_spam, target=spam_handler),
            Default(target=legitimate_message_handler),  # Default handles non-spam and non-SpamDetectorResponse messages
        ],
    )
    .add_edge(spam_handler, final_processor)
    .add_edge(legitimate_message_handler, final_processor)
    .build()
)

# Note: Workflow metadata is determined by executors and graph structure


def main():
    """Launch the spam detection workflow in DevUI."""
    from agent_framework.devui import serve

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)

    logger.info("Starting Spam Detection Workflow")
    logger.info("Available at: http://localhost:8090")
    logger.info("Entity ID: workflow_spam_detection")

    # Launch server with the workflow
    serve(entities=[workflow], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
