# Copyright (c) Microsoft. All rights reserved.

import debugpy
import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from py2docfx.__main__ import main as py2docfx_main

load_dotenv()


async def generate_af_docs(root_path: Path):
    """Generate documentation for the Agent Framework using py2docfx.

    This function runs the py2docfx command with the specified parameters.
    """
    package = {
        "packages": [
            {
                "package_info": {
                    "name": "agent-framework-core",
                    "version": "1.0.0b251001",
                    "install_type": "pypi",
                    "extras": ["all"]
                },
                "sphinx_extensions": [
                    "sphinxcontrib.autodoc_pydantic",
                    "sphinx-pydantic",
                    "sphinx.ext.autosummary"
                ],
                "extension_config": {
                    "napoleon_google_docstring": 1,
                    "napoleon_preprocess_types": 1,
                    "napoleon_use_param": 0,
                    "autodoc_pydantic_field_doc_policy": "both",
                    "autodoc_pydantic_model_show_json": 0,
                    "autodoc_pydantic_model_show_config_summary": 1,
                    "autodoc_pydantic_model_show_field_summary": 1,
                    "autodoc_pydantic_model_hide_paramlist": 0,
                    "autodoc_pydantic_model_show_json_error_strategy": "coerce",
                    "autodoc_pydantic_settings_show_config_summary": 1,
                    "autodoc_pydantic_settings_show_field_summary": 1,
                    "python_use_unqualified_type_names": 1,
                    "autodoc_preserve_defaults": 1,
                    "autodoc_class_signature": "separated",
                    "autodoc_typehints": "description",
                    "autodoc_typehints_format": "fully-qualified",
                    "autodoc_default_options": {
                        "members": 1,
                        "member-order": "alphabetical",
                        "undoc-members": 1,
                        "show-inheritance": 1,
                        "imported-members": 1,
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
            {
                "install_type": "pypi",
                "name": "sphinx-pydantic",
            }
        ],
    }

    args = [
        "-o",
        str((root_path / "docs" / "build").absolute()),
        "-j",
        json.dumps(package),
        "--verbose"
    ]
    try:
        await py2docfx_main(args)
    except Exception as e:
        print(f"Error generating documentation: {e}")


if __name__ == "__main__":
    # Ensure the script is run from the correct directory
    debug = False
    if debug:
        debugpy.listen(("localhost", 5678))
        debugpy.wait_for_client()
        debugpy.breakpoint()

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
