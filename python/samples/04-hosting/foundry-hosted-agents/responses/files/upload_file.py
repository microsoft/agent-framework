# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "azure-ai-projects>=2.3.0,<2.8.0",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Upload one bounded UTF-8 file into a selected sandbox's sample_files directory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from file_access import UPLOAD_DIRECTORY, read_upload_source, write_local_upload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Explicitly selected local UTF-8 file, at most 1,000,000 bytes")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--session-id", help="Foundry agent_session_id, not a response ID or MAF session ID")
    destination.add_argument("--local", action="store_true", help="Stage under this process's HOME for a local host")
    args = parser.parse_args()
    data = read_upload_source(args.file)
    if args.local:
        write_local_upload(args.file.name, data)
        print(f"Staged {UPLOAD_DIRECTORY}/{args.file.name} for the local host.")
        return

    load_dotenv()
    with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential, allow_preview=True
        ) as project,
    ):
        project.agents.upload_session_file(
            agent_name=os.environ["FOUNDRY_AGENT_NAME"],
            session_id=args.session_id,
            content=data,
            path=f"{UPLOAD_DIRECTORY}/{args.file.name}",
        )
    print(f"Uploaded {UPLOAD_DIRECTORY}/{args.file.name} to the selected Foundry sandbox.")


if __name__ == "__main__":
    main()
