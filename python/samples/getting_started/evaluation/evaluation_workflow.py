# Copyright (c) Microsoft. All rights reserved.

import asyncio

from dotenv import load_dotenv
load_dotenv()

from shared_models import AgentFrameworkMessage
from utils import create_mock_evaluation_workflow, run_evaluation_workflow


async def create_conversation(items: list[dict[str, AgentFrameworkMessage]], metadata: dict[str, str] | None = None) -> str:
    thread_id = metadata.get("thread_id") if metadata else None
    run_id = metadata.get("run_id") if metadata else None

    agent_eval_input = {
        "thread_id": thread_id,
        "run_id": run_id,
    }

    workflow = create_mock_evaluation_workflow()
    result = await run_evaluation_workflow(workflow, agent_eval_input["thread_id"], agent_eval_input["run_id"])


if __name__ == "__main__":
    metadata = {
        "thread_id": "[mock-thread-id]",
        "run_id": "[mock-run-id]"
    }
    asyncio.run(create_conversation(items=[], metadata=metadata))
