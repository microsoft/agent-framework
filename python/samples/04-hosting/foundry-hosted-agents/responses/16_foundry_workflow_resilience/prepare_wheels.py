# Copyright (c) Microsoft. All rights reserved.

"""Copy and validate the private preview wheels used by the deployment."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

EXPECTED_WHEELS = (
    "agent_framework_foundry_hosting-*.whl",
    "azure_ai_agentserver_core-*.whl",
    "azure_ai_agentserver_invocations-*.whl",
    "azure_ai_agentserver_responses-*.whl",
)
GENERATED_REQUIREMENTS = "private-wheels.txt"


def _find_one(pattern: str, directories: list[Path]) -> Path:
    matches = [path for directory in directories for path in directory.glob(pattern)]
    if len(matches) != 1:
        locations = ", ".join(str(path) for path in directories)
        raise RuntimeError(f"Expected exactly one {pattern!r} wheel in {locations}; found {len(matches)}.")
    return matches[0]


def _validate_responses_preview(path: Path) -> None:
    with zipfile.ZipFile(path) as wheel:
        exposes_durability = any(
            b"resilient_background" in wheel.read(name) for name in wheel.namelist() if name.endswith(".py")
        )
    if not exposes_durability:
        raise RuntimeError(
            f"{path} does not expose the private durability API. "
            "The public and private artifacts use the same version; select the wheel from the private build."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent-framework-wheels",
        type=Path,
        required=True,
        help="Directory containing agent_framework_foundry_hosting-*.whl.",
    )
    parser.add_argument(
        "--agent-server-wheels",
        type=Path,
        required=True,
        help="Directory containing the private core, invocations, and responses AgentServer wheels.",
    )
    args = parser.parse_args()

    agent_framework_directory = args.agent_framework_wheels.resolve()
    agent_server_directory = args.agent_server_wheels.resolve()
    source_directories = [agent_framework_directory, agent_server_directory]
    for directory in source_directories:
        if not directory.is_dir():
            raise RuntimeError(f"Wheel directory does not exist: {directory}")

    sources: list[Path] = []
    for index, pattern in enumerate(EXPECTED_WHEELS):
        directories = [agent_framework_directory] if index == 0 else [agent_server_directory]
        source = _find_one(pattern, directories)
        if pattern == "azure_ai_agentserver_responses-*.whl":
            _validate_responses_preview(source)
        sources.append(source)

    destination = Path(__file__).parent / "src" / "resilient-translation-workflow" / "wheelhouse"
    destination.mkdir(parents=True, exist_ok=True)
    for old_wheel in destination.glob("*.whl"):
        old_wheel.unlink()

    for source in sources:
        shutil.copy2(source, destination / source.name)
        print(f"Copied {source.name}")

    requirements = destination / GENERATED_REQUIREMENTS
    requirements.write_text(
        "".join(f"./wheelhouse/{source.name}\n" for source in sources),
        encoding="utf-8",
    )
    print(f"Generated {requirements.name}")
    print(f"Prepared private deployment wheels in {destination}")


if __name__ == "__main__":
    main()
