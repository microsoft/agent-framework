# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
from pathlib import Path

from agent_framework import __version__ as agent_framework_version
from py2docfx.__main__ import main as py2docfx_main


async def generate_af_docs(root_path: Path):
    """Generate documentation for the Agent Framework using py2docfx.

    This function runs the py2docfx command with the specified parameters.
    """
    package = {
        "packages": [
            {
                "package_info": {
                    "name": "agent-framework",
                    "version": agent_framework_version,
                    "install_type": "pypi",
                    "extras": ["azure", "foundry"],
                },
                "sphinx_extensions": [
                    "sphinxcontrib.autodoc_pydantic",
                ],
                "extension_config": {
                    "autodoc_pydantic_model_show_json": False,
                    "autodoc_pydantic_model_show_config_summary": False,
                    "autodoc_pydantic_model_show_json_error_strategy": "coerce",
                    "python_use_unqualified_type_names": True,
                    "autodoc_preserve_defaults": True,
                    "autodoc_default_options": {
                        "members": True,
                        "member-order": "alphabetical",
                        "undoc-members": True,
                        "show-inheritance": True,
                        "imported-members": True,
                    },
                },
            }
        ],
        "required_packages": [
            {
                "install_type": "pypi",
                "name": "autodoc_pydantic",
                "version": ">=2.0.0",
            },
        ],
    }

    args = [
        "-o",
        str((root_path / "docs" / "build").absolute()),
        "-j",
        json.dumps(package),
    ]
    try:
        await py2docfx_main(args)
    except Exception as e:
        print(f"Error generating documentation: {e}")


if __name__ == "__main__":
    # Ensure the script is run from the correct directory
    current_path = Path(__file__).parent.parent.resolve()
    print(f"Current path: {current_path}")
    # ensure the dist folder exists
    dist_path = current_path / "dist"
    if not dist_path.exists():
        print(" Please run `poe build` to generate the dist folder.")
        exit(1)
    if os.getenv("PIP_FIND_LINKS") != str(dist_path.absolute()):
        print(f"Setting PIP_FIND_LINKS to {dist_path.absolute()}")
        os.environ["PIP_FIND_LINKS"] = str(dist_path.absolute())
    print(f"Generating documentation in: {current_path / 'docs' / 'build'}")
    # Generate the documentation
    asyncio.run(generate_af_docs(current_path))
