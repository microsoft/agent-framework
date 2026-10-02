# Copyright (c) Microsoft. All rights reserved.

"""Persist an approval workflow, exit, and resume it from a second process."""

import argparse
import asyncio
import sys

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler, response_handler

from agent_framework_postgres import PostgresCheckpointStorage


class PrepareOrder(Executor):
    """Prepare an order before handing it to a reviewer."""

    @handler
    async def prepare(self, order: str, ctx: WorkflowContext[str]) -> None:
        ctx.set_state("prepared_order", order)
        print(f"Prepared order: {order}")
        await ctx.send_message(order)


class ReviewOrder(Executor):
    """Wait for an explicit approval decision."""

    @handler
    async def request_approval(self, order: str, ctx: WorkflowContext) -> None:
        await ctx.request_info(request_data=order, response_type=bool)

    @response_handler
    async def receive_approval(self, original_request: str, approved: bool, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(f"{'Approved' if approved else 'Rejected'} order: {original_request}")


def create_workflow(storage: PostgresCheckpointStorage) -> Workflow:
    """Build the same graph and executor identities in each process."""
    prepare = PrepareOrder(id="prepare")
    review = ReviewOrder(id="review")
    return (
        WorkflowBuilder(start_executor=prepare, name="postgres-approval", checkpoint_storage=storage)
        .add_edge(prepare, review)
        .build()
    )


async def main(arguments: argparse.Namespace) -> None:
    """Run one phase using POSTGRES_CONNECTION_STRING from the environment."""
    async with PostgresCheckpointStorage(
        application_id=arguments.application_id,
        tenant_id=arguments.tenant_id,
        run_id=arguments.run_id,
        schema=arguments.schema,
    ) as storage:
        await storage.ensure_table()
        workflow = create_workflow(storage)
        latest = await storage.get_latest(workflow_name=workflow.name)
        if arguments.action == "start":
            if latest is not None:
                raise ValueError("This run already has checkpoints. Resume it or choose a new run ID.")
            events = workflow.run(arguments.order, stream=True)
        else:
            if latest is None or not latest.pending_request_info_events:
                raise ValueError("No pending approval exists for this application, tenant, and run.")
            responses = {
                request_id: arguments.decision == "approve" for request_id in latest.pending_request_info_events
            }
            events = workflow.run(checkpoint_id=latest.checkpoint_id, responses=responses, stream=True)

        async for event in events:
            if event.type == "request_info":
                print(f"Waiting for approval: {event.data}")
            elif event.type == "output":
                print(event.data)

        latest = await storage.get_latest(workflow_name=workflow.name)
        if latest is not None:
            print(f"Checkpoint saved: {latest.checkpoint_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "resume"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--application-id", default="checkpoint-sample")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--order", default="PO-1042")
    parser.add_argument("--decision", choices=("approve", "reject"))
    arguments = parser.parse_args()
    if arguments.action == "resume" and arguments.decision is None:
        parser.error("resume requires --decision approve or --decision reject")
    if sys.version_info >= (3, 12):
        asyncio.run(main(arguments), loop_factory=asyncio.SelectorEventLoop)
    else:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main(arguments))
