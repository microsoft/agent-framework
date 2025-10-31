# Copyright (c) Microsoft. All rights reserved.

"""Spam Detection Workflow Sample for DevUI.

The following sample demonstrates a comprehensive 5-step workflow with multiple executors
that process, analyze, detect spam, and handle email messages. This workflow illustrates
complex branching logic and realistic processing delays to demonstrate the workflow framework.

Workflow Steps:
1. Email Preprocessor - Cleans and prepares the email
2. Content Analyzer - Analyzes email content and structure
3. Spam Detector - Determines if the message is spam
4a. Spam Handler - Processes spam messages (quarantine, log, remove)
4b. Message Responder - Handles legitimate messages (validate, respond)
5. Final Processor - Completes the workflow with logging and cleanup
"""

import asyncio
import logging
from dataclasses import dataclass

from agent_framework import (
    Case,
    Default,
    Executor,
    InMemoryCheckpointStorage,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from pydantic import BaseModel, Field
from typing_extensions import Never


@dataclass
class EmailContent:
    """A data class to hold the processed email content."""

    original_message: str
    cleaned_message: str
    word_count: int
    has_suspicious_patterns: bool = False


@dataclass
class ContentAnalysis:
    """A data class to hold content analysis results."""

    email_content: EmailContent
    sentiment_score: float
    contains_links: bool
    has_attachments: bool
    risk_indicators: list[str]


@dataclass
class SpamDetectorResponse:
    """A data class to hold the spam detection results."""

    analysis: ContentAnalysis
    is_spam: bool = False
    confidence_score: float = 0.0
    spam_reasons: list[str] | None = None

    def __post_init__(self):
        """Initialize spam_reasons list if None."""
        if self.spam_reasons is None:
            self.spam_reasons = []


@dataclass
class SpamApprovalRequest(RequestInfoMessage):
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


class ContentAnalyzer(Executor):
    """Step 2: An executor that analyzes email content and structure."""

    @handler
    async def handle_email_content(self, email_content: EmailContent, ctx: WorkflowContext[ContentAnalysis]) -> None:
        """Analyze the email content for various indicators."""
        await asyncio.sleep(2.0)  # Simulate analysis time

        # Simulate content analysis
        sentiment_score = 0.5 if email_content.has_suspicious_patterns else 0.8
        contains_links = "http" in email_content.cleaned_message or "www" in email_content.cleaned_message
        has_attachments = "attachment" in email_content.cleaned_message

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

        analysis = ContentAnalysis(
            email_content=email_content,
            sentiment_score=sentiment_score,
            contains_links=contains_links,
            has_attachments=has_attachments,
            risk_indicators=risk_indicators,
        )

        await ctx.send_message(analysis)


class SpamDetector(Executor):
    """Step 3: An executor that determines if a message is spam based on analysis."""

    def __init__(self, spam_keywords: list[str], human_reviewer_id: str, id: str):
        """Initialize the executor with spam keywords."""
        super().__init__(id=id)
        self._spam_keywords = spam_keywords
        self._human_reviewer_id = human_reviewer_id

    @handler
    async def handle_analysis(self, analysis: ContentAnalysis, ctx: WorkflowContext[SpamApprovalRequest]) -> None:
        """Determine if the message is spam and request human approval."""
        await asyncio.sleep(1.8)  # Simulate detection time

        # Check for spam keywords
        email_text = analysis.email_content.cleaned_message
        keyword_matches = [kw for kw in self._spam_keywords if kw in email_text]

        # Calculate spam probability
        spam_score = 0.0
        spam_reasons: list[str] = []

        if keyword_matches:
            spam_score += 0.4
            spam_reasons.append(f"spam_keywords: {keyword_matches}")

        if analysis.email_content.has_suspicious_patterns:
            spam_score += 0.3
            spam_reasons.append("suspicious_patterns")

        if len(analysis.risk_indicators) >= 3:
            spam_score += 0.2
            spam_reasons.append("high_risk_indicators")

        if analysis.sentiment_score < 0.4:
            spam_score += 0.1
            spam_reasons.append("negative_sentiment")

        is_spam = spam_score >= 0.5

        # Store detection result in executor state for later use
        # Store minimal data needed (not complex objects that don't serialize well)
        await ctx.set_executor_state({
            "original_message": analysis.email_content.original_message,
            "cleaned_message": analysis.email_content.cleaned_message,
            "word_count": analysis.email_content.word_count,
            "is_spam": is_spam,
            "confidence_score": spam_score,
            "spam_reasons": spam_reasons
        })

        # Request human approval before proceeding
        approval_request = SpamApprovalRequest(
            email_message=email_text[:200],  # First 200 chars
            detected_as_spam=is_spam,
            confidence=spam_score,
            reasons=", ".join(spam_reasons) if spam_reasons else "no specific reasons"
        )

        await ctx.send_message(approval_request, target_id=self._human_reviewer_id)

    @handler
    async def handle_human_response(
        self,
        response: RequestResponse[SpamApprovalRequest, str],
        ctx: WorkflowContext[SpamDetectorResponse]
    ) -> None:
        """Process human approval response and continue workflow."""
        print(f"[SpamDetector] handle_human_response called with response: {response.data}")

        # Get stored detection result
        state = await ctx.get_executor_state() or {}
        print(f"[SpamDetector] Retrieved state: {state}")
        is_spam = state.get("is_spam", False)
        confidence_score = state.get("confidence_score", 0.0)
        spam_reasons = state.get("spam_reasons", [])

        # Parse human decision
        human_decision = (response.data or "").strip().lower()

        # Override spam detection if human disagrees
        if human_decision in ["approve", "not spam", "legitimate", "no"]:
            is_spam = False
        elif human_decision in ["reject", "spam", "yes"]:
            is_spam = True

        # Reconstruct EmailContent and ContentAnalysis from stored primitives
        email_content = EmailContent(
            original_message=state.get("original_message", ""),
            cleaned_message=state.get("cleaned_message", ""),
            word_count=state.get("word_count", 0),
            has_suspicious_patterns=False  # Not critical for final output
        )

        analysis = ContentAnalysis(
            email_content=email_content,
            sentiment_score=0.5,  # Not critical for final output
            contains_links=False,
            has_attachments=False,
            risk_indicators=[]
        )

        result = SpamDetectorResponse(
            analysis=analysis,
            is_spam=is_spam,
            confidence_score=confidence_score,
            spam_reasons=spam_reasons
        )

        print(f"[SpamDetector] Sending SpamDetectorResponse: is_spam={is_spam}, confidence={confidence_score}")
        await ctx.send_message(result)
        print(f"[SpamDetector] Message sent successfully")


class SpamHandler(Executor):
    """Step 4a: An executor that handles spam messages with quarantine and logging."""

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
            original_message=spam_result.analysis.email_content.original_message,
            action_taken="quarantined_and_logged",
            processing_time=2.2,
            status="spam_handled",
            is_spam=spam_result.is_spam,
            confidence_score=spam_result.confidence_score,
            spam_reasons=spam_result.spam_reasons or [],
        )

        await ctx.send_message(result)


class MessageResponder(Executor):
    """Step 4b: An executor that responds to legitimate messages."""

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
            original_message=spam_result.analysis.email_content.original_message,
            action_taken="responded_and_filed",
            processing_time=2.5,
            status="message_processed",
            is_spam=spam_result.is_spam,
            confidence_score=spam_result.confidence_score,
            spam_reasons=spam_result.spam_reasons or [],
        )

        await ctx.send_message(result)


class FinalProcessor(Executor):
    """Step 5: An executor that completes the workflow with final logging and cleanup."""

    @handler
    async def handle_processing_result(
        self,
        result: ProcessingResult,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        """Complete the workflow with final processing and logging."""
        await asyncio.sleep(1.5)  # Simulate final processing time

        total_time = result.processing_time + 1.5

        # Include classification details in completion message
        classification = "SPAM" if result.is_spam else "LEGITIMATE"
        reasons = ", ".join(result.spam_reasons) if result.spam_reasons else "none"

        completion_message = (
            f"Email classified as {classification} (confidence: {result.confidence_score:.2f}). "
            f"Reasons: {reasons}. "
            f"Action: {result.action_taken}, "
            f"Status: {result.status}, "
            f"Total time: {total_time:.1f}s"
        )

        await ctx.yield_output(completion_message)


# Create checkpoint storage for HIL support
checkpoint_storage = InMemoryCheckpointStorage()

# Create the workflow instance that DevUI can discover
spam_keywords = ["spam", "advertisement", "offer", "click here", "winner", "congratulations", "urgent"]

# Create all the executors for the 5-step workflow
email_preprocessor = EmailPreprocessor(id="email_preprocessor")
content_analyzer = ContentAnalyzer(id="content_analyzer")
human_reviewer = RequestInfoExecutor(id="human_reviewer")
spam_detector = SpamDetector(spam_keywords, human_reviewer_id=human_reviewer.id, id="spam_detector")
spam_handler = SpamHandler(id="spam_handler")
message_responder = MessageResponder(id="message_responder")
final_processor = FinalProcessor(id="final_processor")

# Build the comprehensive 5-step workflow with branching logic and HIL support
workflow = (
    WorkflowBuilder(
        name="Email Spam Detector",
        description="5-step email classification workflow with human-in-the-loop spam approval",
    )
    .set_start_executor(email_preprocessor)
    .add_edge(email_preprocessor, content_analyzer)
    .add_edge(content_analyzer, spam_detector)
    # HIL: spam_detector -> human_reviewer -> spam_detector
    .add_edge(spam_detector, human_reviewer)
    .add_edge(human_reviewer, spam_detector)
    # Continue with branching logic after human approval
    # Only route SpamDetectorResponse messages (not SpamApprovalRequest)
    .add_switch_case_edge_group(
        spam_detector,
        [
            Case(condition=lambda x: isinstance(x, SpamDetectorResponse) and x.is_spam, target=spam_handler),
            Default(target=message_responder),  # Default handles non-spam and non-SpamDetectorResponse messages
        ],
    )
    .add_edge(spam_handler, final_processor)
    .add_edge(message_responder, final_processor)
    .with_checkpointing(checkpoint_storage=checkpoint_storage)
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
