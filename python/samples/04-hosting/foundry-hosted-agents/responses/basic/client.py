# Copyright (c) Microsoft. All rights reserved.

"""Call a deployed Responses agent with stored, one-shot, and background requests."""

import os
from time import sleep

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            credential=credential,
            allow_preview=True,
        ) as project,
    ):
        openai = project.get_openai_client(agent_name=os.environ["FOUNDRY_AGENT_NAME"])
        conversation = openai.conversations.create()
        first = openai.responses.create(input="Introduce yourself.", conversation=conversation.id, store=True)
        second = openai.responses.create(
            input="Answer briefly.",
            conversation=conversation.id,
            store=True,
            max_output_tokens=300,
            extra_body={"max_tokens": 150},
        )
        print(f"Stored response {first.id}; continued with {second.id}: {second.output_text}")

        one_shot = openai.responses.create(input="Say hello.", store=False)
        print(f"Unstored response (id cannot be retrieved): {one_shot.output_text}")

        background = openai.responses.create(input="Write a report.", store=True, background=True)
        response_id = background.id
        while background.status in ("queued", "in_progress"):
            sleep(2)
            background = openai.responses.retrieve(response_id)
        if background.status != "completed":
            raise RuntimeError(f"Background response {response_id} ended with status {background.status}.")
        print(f"Background response {response_id}: {background.output_text}")


if __name__ == "__main__":
    main()
