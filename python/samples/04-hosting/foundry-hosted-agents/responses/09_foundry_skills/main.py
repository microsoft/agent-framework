# Copyright (c) Microsoft. All rights reserved.

"""Foundry Skills hosted agent sample.

At startup, this agent downloads each Foundry Skill named in
``SKILL_NAMES`` from the project's ``beta.skills`` API, unpacks each
one into a separate runtime directory under ``downloaded_skills/``, and wires
that directory into a :class:`SkillsProvider` so the agent advertises the
skills to the model and loads them on demand (progressive disclosure).

Upload the skills to Foundry once with ``provision_skills.py`` before running
this sample.
"""

import asyncio
import io
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Final

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Runtime directory where skills downloaded from Foundry are unpacked.
# Kept separate from the static ``skills/`` source folder so the two never
# get confused: the source folder is the input to ``provision_skills.py``
# and the runtime folder is the output of this script's bootstrap step.
DOWNLOADED_SKILLS_DIR: Final = Path(__file__).parent / "downloaded_skills"

logger = logging.getLogger(__name__)


async def _bootstrap_skills(endpoint: str, skill_names: list[str], target_dir: Path) -> None:
    """Download each named skill via ``project.beta.skills`` and unpack it as ``<target_dir>/<name>/SKILL.md``."""
    if target_dir.exists():  # noqa: ASYNC240
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)  # noqa: ASYNC240

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
    ):
        for name in skill_names:
            logger.info(f"Downloading skill '{name}' from Foundry...")
            stream = await project.beta.skills.download(name)
            zip_bytes = b"".join([chunk async for chunk in stream])
            skill_dir = target_dir / name
            skill_dir.mkdir()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(skill_dir)
            if not (skill_dir / "SKILL.md").is_file():
                raise RuntimeError(f"Downloaded archive for '{name}' did not contain a SKILL.md at the root.")


async def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    skill_names = [name.strip() for name in os.environ["SKILL_NAMES"].split(",") if name.strip()]
    if not skill_names:
        raise RuntimeError("SKILL_NAMES must list at least one skill name.")

    # Pull the latest copy of each skill from Foundry into a runtime-only folder.
    await _bootstrap_skills(project_endpoint, skill_names, DOWNLOADED_SKILLS_DIR)

    # Build a SkillsProvider over the unpacked folder. The provider advertises
    # each skill's name + description to the model and exposes the ``load_skill``
    # tool the model uses to retrieve the full SKILL.md body on demand. No
    # script_runner is configured because the skills in this sample are
    # instruction-only.
    skills_provider = SkillsProvider.from_paths(skill_paths=str(DOWNLOADED_SKILLS_DIR))

    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions="You are a customer-support assistant for Contoso Outdoors.",
        context_providers=[skills_provider],
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )
    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
