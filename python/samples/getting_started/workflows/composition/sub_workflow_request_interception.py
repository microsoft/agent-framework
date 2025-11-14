# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from agent_framework import (
    Executor,
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    WorkflowOutputEvent,
    handler,
    response_handler,
)
from typing_extensions import Never

"""
This sample demonstrates how to handle request from the sub-workflow in the main workflow.

Prerequisite:
- Understanding of sub-workflows.
- Understanding of requests and responses.

This pattern is useful when you want to reuse a workflow that makes requests to an external system,
but you want to intercept those requests in the main workflow and handle them without further propagation
to the external system.

This sample implements a smart email delivery system that validates email addresses before sending emails.
1. We will start by creating a workflow that validates email addresses in a sequential manner. The validation
   consists of three steps: sanitization, format validation, and domain validation. The domain validation
   step will involve checking if the email domain is valid by making a request to an external system.
2. Then we will create a main workflow that uses the email validation workflow as a sub-workflow. The main
    workflow will intercept the domain validation requests from the sub-workflow and handle them internally
    without propagating them to an external system.
3. Once the email address is validated, the main workflow will proceed to send the email if the address is valid,
   or block the email if the address is invalid.
"""


@dataclass
class SanitizedEmailResult:
    """Result of email sanitization and validation.

    The properties get built up as the email address goes through
    the validation steps in the workflow.
    """

    original: str
    sanitized: str
    is_valid: bool


def build_email_address_validation_workflow() -> Workflow:
    """Build an email address validation workflow.

    This workflow consists of three steps (each is represented by an executor):
    1. Sanitize the email address, such as removing leading/trailing spaces.
    2. Validate the email address format, such as checking for "@" and domain.
    3. Extract the domain from the email address and request domain validation,
       after which it completes with the final result.
    """

    class EmailSanitizer(Executor):
        """Sanitize email address by trimming spaces."""

        @handler
        async def handle(self, email_address: str, ctx: WorkflowContext[SanitizedEmailResult]) -> None:
            """Trim leading and trailing spaces from the email address.

            This executor doesn't produce any workflow output, but sends the sanitized
            email address to the next executor in the workflow.
            """
            sanitized = email_address.strip()
            print(f"✂️ Sanitized email address: '{sanitized}'")
            await ctx.send_message(SanitizedEmailResult(original=email_address, sanitized=sanitized, is_valid=False))

    class EmailFormatValidator(Executor):
        """Validate email address format."""

        @handler
        async def handle(
            self,
            partial_result: SanitizedEmailResult,
            ctx: WorkflowContext[SanitizedEmailResult, SanitizedEmailResult],
        ) -> None:
            """Validate the email address format.

            This executor can potentially produce a workflow output (False if the format is invalid).
            When the format is valid, it sends the validated email address to the next executor in the workflow.
            """
            if "@" not in partial_result.sanitized or "." not in partial_result.sanitized.split("@")[-1]:
                print(f"❌ Invalid email format: '{partial_result.sanitized}'")
                await ctx.yield_output(
                    SanitizedEmailResult(
                        original=partial_result.original, sanitized=partial_result.sanitized, is_valid=False
                    )
                )
                return
            print(f"✅ Validated email format: '{partial_result.sanitized}'")
            await ctx.send_message(
                SanitizedEmailResult(
                    original=partial_result.original, sanitized=partial_result.sanitized, is_valid=False
                )
            )

    class DomainValidator(Executor):
        """Validate email domain."""

        def __init__(self, id: str):
            super().__init__(id=id)
            self._pending_domains: dict[str, SanitizedEmailResult] = {}

        @handler
        async def handle(self, partial_result: SanitizedEmailResult, ctx: WorkflowContext) -> None:
            """Extract the domain from the email address and request domain validation.

            This executor doesn't produce any workflow output, but sends a domain validation request
            to an external system to user for validation.
            """
            domain = partial_result.sanitized.split("@")[-1]
            print(f"🔍 Validating domain: '{domain}'")
            self._pending_domains[domain] = partial_result
            # Send a request to the external system via the request_info mechanism
            await ctx.request_info(request_data=domain, response_type=bool)

        @response_handler
        async def handle_domain_validation_response(
            self, original_request: str, is_valid: bool, ctx: WorkflowContext[Never, SanitizedEmailResult]
        ) -> None:
            """Handle the domain validation response.

            This method receives the response from the external system and yields the final
            validation result (True if both format and domain are valid, False otherwise).
            """
            if original_request not in self._pending_domains:
                raise ValueError(f"Received response for unknown domain: '{original_request}'")
            partial_result = self._pending_domains.pop(original_request)
            if is_valid:
                print(f"✅ Domain '{original_request}' is valid.")
                await ctx.yield_output(
                    SanitizedEmailResult(
                        original=partial_result.original, sanitized=partial_result.sanitized, is_valid=True
                    )
                )
            else:
                print(f"❌ Domain '{original_request}' is invalid.")
                await ctx.yield_output(
                    SanitizedEmailResult(
                        original=partial_result.original, sanitized=partial_result.sanitized, is_valid=False
                    )
                )

    # Build the workflow
    sanitizer = EmailSanitizer(id="email_sanitizer")
    format_validator = EmailFormatValidator(id="email_format_validator")
    domain_validator = DomainValidator(id="domain_validator")

    return (
        WorkflowBuilder()
        .set_start_executor(sanitizer)
        .add_edge(sanitizer, format_validator)
        .add_edge(format_validator, domain_validator)
        .build()
    )


@dataclass
class Email:
    recipient: str
    subject: str
    body: str


class SmartEmailOrchestrator(Executor):
    """Orchestrates email address validation using a sub-workflow."""

    def __init__(self, id: str, approved_domains: set[str]):
        """Initialize the orchestrator with a set of approved domains.

        Args:
            id: The executor ID.
            approved_domains: A set of domains that are considered valid.
        """
        super().__init__(id=id)
        self._approved_domains = approved_domains
        # Keep track of previously approved and disapproved recipients
        self._approved_recipients: set[str] = set()
        self._disapproved_recipients: set[str] = set()
        # Record pending emails waiting for validation results
        self._pending_emails: dict[str, Email] = {}

    @handler
    async def run(self, email: Email, ctx: WorkflowContext[Email | str, bool]) -> None:
        """Start the email delivery process.

        This handler receives an Email object. If the recipient has been previously approved,
        it sends the email object to the next executor to handle delivery. If the recipient
        has been previously disapproved, it yields False as the final result. Otherwise,
        it sends the recipient email address to the sub-workflow for validation.
        """
        recipient = email.recipient
        if recipient in self._approved_recipients:
            print(f"📧 Recipient '{recipient}' has been previously approved.")
            await ctx.send_message(email)
            return
        if recipient in self._disapproved_recipients:
            print(f"🚫 Blocking email to previously disapproved recipient: '{recipient}'")
            await ctx.yield_output(False)
            return

        print(f"🔍 Validating new recipient email address: '{recipient}'")
        self._pending_emails[recipient] = email
        await ctx.send_message(recipient)

    @handler
    async def handler_domain_validation_request(
        self, request: SubWorkflowRequestMessage, ctx: WorkflowContext[SubWorkflowResponseMessage]
    ) -> None:
        """Handle requests from the sub-workflow for domain validation.

        Note that the message type must be SubWorkflowRequestMessage to intercept the request. And
        the response must be sent back using SubWorkflowResponseMessage to route the response
        back to the sub-workflow.
        """
        if not isinstance(request.source_event.data, str):
            raise TypeError(f"Expected domain string, got {type(request.source_event.data)}")
        domain = request.source_event.data
        is_valid = domain in self._approved_domains
        print(f"🌐 External domain validation for '{domain}': {'valid' if is_valid else 'invalid'}")
        await ctx.send_message(request.create_response(is_valid), target_id=request.executor_id)

    @handler
    async def handle_validation_result(self, result: SanitizedEmailResult, ctx: WorkflowContext[Email, bool]) -> None:
        """Handle the email address validation result.

        This handler receives the validation result from the sub-workflow.
        If the email address is valid, it adds the recipient to the approved list
        and sends the email object to the next executor to handle delivery.
        If the email address is invalid, it adds the recipient to the disapproved list
        and yields False as the final result.
        """
        email = self._pending_emails.pop(result.original)
        email.recipient = result.sanitized  # Use the sanitized email address
        if result.is_valid:
            print(f"✅ Email address '{result.original}' is valid.")
            self._approved_recipients.add(result.original)
            await ctx.send_message(email)
        else:
            print(f"🚫 Email address '{result.original}' is invalid. Blocking email.")
            self._disapproved_recipients.add(result.original)
            await ctx.yield_output(False)


class EmailDelivery(Executor):
    """Simulates email delivery."""

    @handler
    async def handle(self, email: Email, ctx: WorkflowContext[Never, bool]) -> None:
        """Simulate sending the email and yield True as the final result."""
        print(f"📤 Sending email to '{email.recipient}' with subject '{email.subject}'")
        await asyncio.sleep(1)  # Simulate network delay
        print(f"✅ Email sent to '{email.recipient}' successfully.")
        await ctx.yield_output(True)


async def main() -> None:
    # A list of approved domains
    approved_domains = {"example.com", "company.com"}

    # Create executors in the main workflow
    orchestrator = SmartEmailOrchestrator(id="smart_email_orchestrator", approved_domains=approved_domains)
    email_delivery = EmailDelivery(id="email_delivery")

    # Create the sub-workflow for email address validation
    validation_workflow = build_email_address_validation_workflow()
    validation_workflow_executor = WorkflowExecutor(validation_workflow, id="email_validation_workflow")

    # Build the main workflow
    workflow = (
        WorkflowBuilder()
        .set_start_executor(orchestrator)
        .add_edge(orchestrator, validation_workflow_executor)
        .add_edge(validation_workflow_executor, orchestrator)
        .add_edge(orchestrator, email_delivery)
        .build()
    )

    test_emails = [
        Email(recipient="user1@example.com", subject="Hello User1", body="This is a test email."),
        Email(recipient=" user2@invalid", subject="Hello User2", body="This is a test email."),
        Email(recipient="  user3@company.com  ", subject="Hello User3", body="This is a test email."),
        Email(recipient="user4@unknown.com", subject="Hello User4", body="This is a test email."),
        # Re-send to an approved recipient
        Email(recipient="user1@example.com", subject="Hello User1", body="This is a test email."),
        # Re-send to a disapproved recipient
        Email(recipient=" user2@invalid", subject="Hello User2", body="This is a test email."),
    ]

    # Execute the workflow
    for email in test_emails:
        print(f"\n🚀 Processing email to '{email.recipient}'")
        async for event in workflow.run_stream(email):
            if isinstance(event, WorkflowOutputEvent):
                print(f"🎉 Final result for '{email.recipient}': {'Delivered' if event.data else 'Blocked'}")


if __name__ == "__main__":
    asyncio.run(main())
