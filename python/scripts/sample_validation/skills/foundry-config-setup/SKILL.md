---
name: foundry-config-setup
description: Resolve missing setup caused by a hardcoded Foundry project endpoint or model in a sample. Use when a sample fails because it uses a placeholder/hardcoded project_endpoint (for example "https://your-project.services.ai.azure.com") or a hardcoded model instead of reading them from the environment.
license: MIT
compatibility: Works with any model that supports tool use.
metadata:
  author: agent-framework-samples
  version: "1.0"
---

## Usage

Some samples (notably those under `01-get-started`) hardcode the Foundry
project endpoint and model directly in the `FoundryChatClient` constructor
using placeholder values, for example:

```python
client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4o",
    credential=AzureCliCredential(),
)
```

These placeholder values are not real and the sample cannot run as written.
The validation environment provides the real values through environment
variables, so the sample must read them from the environment instead.

When you detect a hardcoded/placeholder `project_endpoint` (or `model`) that
is causing the sample to fail with missing or invalid setup:

1. Replace the hardcoded `project_endpoint` value with a read from the
   `FOUNDRY_PROJECT_ENDPOINT` environment variable.
2. Replace the hardcoded `model` value with a read from the `FOUNDRY_MODEL`
   environment variable.
3. Ensure `import os` is present at the top of the file.

The corrected constructor should look like:

```python
import os

client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=AzureCliCredential(),
)
```

These samples are intentionally written with hardcoded placeholders, so this
is expected setup—not a defect in the sample. After applying the change,
re-run the sample and report the result as a `success` if it now runs. Do not
include a suggested `fix`.
