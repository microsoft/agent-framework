# Get Started with Microsoft Agent Framework GitHub Copilot

Please install this package via pip:

```bash
pip install agent-framework-github-copilot --pre
```

## GitHub Copilot Agent

The GitHub Copilot agent enables integration with GitHub Copilot, allowing you to interact with Copilot's agentic capabilities through the Agent Framework.

### Native Copilot skills

You can load Copilot CLI-native skills by passing `skill_directories` in `default_options`:

```python
from copilot.session import PermissionRequestResult
from agent_framework_github_copilot import GitHubCopilotAgent


def approve_all(_request, _context):
    return PermissionRequestResult(kind="approved")


agent = GitHubCopilotAgent(
    default_options={
        "on_permission_request": approve_all,
        "skill_directories": ["./skills"],
    }
)
```
