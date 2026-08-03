# Copyright (c) Microsoft. All rights reserved.

"""Provision Foundry Skills used by this sample.

For each ``skills/<name>/SKILL.md`` file in this directory, this script packages
the file as an in-memory ZIP and imports it through the Foundry project's
:class:`~azure.ai.projects.aio.AIProjectClient` so the skill becomes downloadable
by any hosted agent in the project.

If a skill with the same name already exists in Foundry, it is deleted first
so the script is safe to re-run after editing a ``SKILL.md`` file.

Usage (from this directory, with the venv activated and ``az login`` done):

    python provision_skills.py

Required env vars (also read from a local ``.env`` file if present):

    FOUNDRY_PROJECT_ENDPOINT   e.g. https://<account>.services.ai.azure.com/api/projects/<project>

Your identity needs the ``Azure AI User`` role on the Foundry project.
"""

import asyncio
import io
import os
import zipfile
from pathlib import Path

from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import CreateSkillVersionFromFilesBody
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

SKILLS_DIR = Path(__file__).parent / "skills"


def _zip_skill_md(skill_md: Path) -> bytes:
    """Return the bytes of a ZIP archive containing ``SKILL.md`` at the root."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md.read_text(encoding="utf-8"))
    return buffer.getvalue()


async def _delete_skill_if_exists(project: AIProjectClient, name: str) -> None:
    try:
        await project.beta.skills.delete(name)
    except ResourceNotFoundError:
        return
    print(f"  Deleted existing skill '{name}'.")


async def main() -> None:
    load_dotenv()

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    if not skill_files:
        raise RuntimeError(f"No SKILL.md files found under {SKILLS_DIR}.")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project,
    ):
        for skill_md in skill_files:
            name = skill_md.parent.name
            print(f"Provisioning skill '{name}' from {skill_md.relative_to(SKILLS_DIR.parent)}...")
            await _delete_skill_if_exists(project, name)
            imported = await project.beta.skills.create_from_files(
                name,
                content=CreateSkillVersionFromFilesBody(
                    files=[(f"{name}.zip", _zip_skill_md(skill_md), "application/zip")]
                ),
            )
            print(f"  Imported skill '{imported.name}' (id={imported.skill_id}, version={imported.version}).")

        print("Verifying skills via project.beta.skills.list()...")
        listed = {skill.name: skill async for skill in project.beta.skills.list()}
        for skill_md in skill_files:
            name = skill_md.parent.name
            skill = listed.get(name)
            if skill is None:
                raise RuntimeError(f"Skill '{name}' was imported but is not present in the project listing.")
            print(
                f"  OK '{skill.name}': id={skill.id}, "
                f"description={skill.description!r}, default_version={skill.default_version}"
            )

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
