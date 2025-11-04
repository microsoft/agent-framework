# Copyright (c) Microsoft. All rights reserved.
from pathlib import Path

from agent_framework_declarative import load_maml


def main():
    """Create an agent from a declarative yaml specification and run it."""
    current_path = Path(__file__).parent
    yaml_path = current_path.parent.parent.parent.parent / "agent-samples" / "chatclient" / "Assistant.yaml"

    with yaml_path.open("r") as f:
        yaml_str = f.read()
    agent = load_maml(yaml_str)
    print(agent)


if __name__ == "__main__":
    main()
