# Get Started with Microsoft Agent Framework Azure Cosmos DB Memory

Please install this package via pip:

```bash
pip install agent-framework-azure-cosmos-memory --pre
```

## Azure Cosmos DB Memory Context Provider

The Azure Cosmos DB Memory integration provides `CosmosMemoryContextProvider` for long-term semantic memory storage using the [Azure Cosmos DB Agent Memory Toolkit](https://github.com/AzureCosmosDB/AgentMemoryToolkit).

This context provider enables:
- **Semantic memory retrieval** - Facts, procedural knowledge, and episodic memories
- **Automatic memory extraction** - Conversation turns are processed to extract structured knowledge
- **User profile consolidation** - Cross-thread user profiles with preferences and facts
- **Memory reconciliation** - Deduplication and contradiction resolution

### Basic Usage Example

```python
from azure.identity.aio import DefaultAzureCredential
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

# A single AI Foundry endpoint powers both memory and the chat agent
foundry_endpoint = "https://<project>.services.ai.azure.com"

# Create the memory provider
memory_provider = CosmosMemoryContextProvider(
    cosmos_endpoint="https://<account>.documents.azure.com:443/",
    cosmos_database="ai_memory",
    foundry_endpoint=foundry_endpoint,
    credential=DefaultAzureCredential(),
)

# Create an agent with memory - reuses the same AI Foundry endpoint
agent = FoundryChatClient(
    project_endpoint=foundry_endpoint,
    model="gpt-4o-mini",
    credential=DefaultAzureCredential(),
).as_agent(
    instructions="You are a helpful assistant with long-term memory.",
    context_providers=[memory_provider]
)

# Use the agent - memories are automatically stored and retrieved
session = agent.create_session()
await agent.run("I love hiking and prefer vegetarian food.", session=session)
await agent.run("What do you know about my preferences?", session=session)
```

### Authentication Options

The provider supports the same authentication modes as other Azure integrations:

- **Managed identity / RBAC** (recommended): Pass `DefaultAzureCredential()`
- **Connection string**: Set environment variables
- **Environment variables**: `COSMOS_ENDPOINT`, `COSMOS_DATABASE`, `FOUNDRY_ENDPOINT`

### Development Setup

To avoid dependency conflicts with your system Python, it's recommended to use a virtual environment:

#### Option 1: Using venv (Built-in, Cross-Platform)

**Bash/Linux/macOS:**
```bash
# Navigate to the package directory
cd python/packages/azure-cosmos-memory

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install package in development mode with all dependencies
pip install -e ".[dev]"

# OPTIONAL: sample dependencies (needed for the samples). The samples also declare these
# inline via PEP 723, so you can instead run them with `uv run samples/<name>.py`.
pip install agent-framework-foundry python-dotenv

# Verify installation
python -c "from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider; print('✓ Package installed')"
```

**PowerShell:**
```powershell
# Navigate to the package directory
cd python\packages\azure-cosmos-memory

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# If you get execution policy errors, run first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install package in development mode with all dependencies
pip install -e ".[dev]"

# OPTIONAL: sample dependencies (needed for the samples). The samples also declare these
# inline via PEP 723, so you can instead run them with `uv run samples/<name>.py`.
pip install agent-framework-foundry python-dotenv

# Verify installation
python -c "from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider; print('✓ Package installed')"
```

**To deactivate the virtual environment:**
```bash
deactivate  # Works on all platforms
```

#### Option 2: Using uv (Fast Alternative)

If you have [uv](https://github.com/astral-sh/uv) installed:

```bash
# Sync all dependencies including dev dependencies
uv sync --prerelease=allow

# Run samples with uv (it manages the environment for you)
uv run python samples/interactive_chat.py
```

### How to Run the Samples

**Important:** Before running samples, complete the [Development Setup](#development-setup) above to create a virtual environment and install the package.

This package includes three samples demonstrating different usage patterns:

#### 1. **Basic Usage (`samples/basic_usage.py`)** - API Demonstration
This sample shows the **raw ContextProvider API** by manually calling `before_run()` and `after_run()`. It demonstrates:
- How the provider searches for memories
- How memories are injected into context
- How conversations are stored
- **Not a real agent** - just shows the API mechanics

**Run it:**

Ensure your virtual environment is activated, then:

```bash
# Bash/Linux/macOS
export COSMOS_ENDPOINT="https://<your-account>.documents.azure.com:443/"
export FOUNDRY_ENDPOINT="https://<your-project>.services.ai.azure.com"
python samples/basic_usage.py
```

```powershell
# PowerShell
$env:COSMOS_ENDPOINT="https://<your-account>.documents.azure.com:443/"
$env:FOUNDRY_ENDPOINT="https://<your-project>.services.ai.azure.com"
python samples/basic_usage.py
```

#### 2. **Interactive Chat (`samples/interactive_chat.py`)** - Real Agent Integration
This sample shows **real-world usage** with Agent Framework. It demonstrates:
- ✅ **Full Agent Framework integration** - actual chatbot you can interact with
- ✅ **Multi-turn conversations** - see memories persist across sessions
- ✅ **User/thread scoping** - test memory isolation
- ✅ **Interactive CLI** - chat with the agent, switch users, start new threads

**Prerequisites:**

1. **Complete [Development Setup](#development-setup)** - Create a venv and install the package with test dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
   The samples declare their own dependencies via [PEP 723](https://peps.python.org/pep-0723/) inline
   metadata, so you can also just run them with `uv run samples/interactive_chat.py`. To install the
   sample dependencies manually into your venv:
   ```bash
   pip install agent-framework-foundry python-dotenv
   ```

2. **Azure Resources** - You'll need:
   - An Azure Cosmos DB account with a database (e.g., `ai_memory`)
   - An Azure AI Foundry project with embedding and chat deployments
   - The following deployments configured in AI Foundry:
     - `text-embedding-3-large` (or your preferred embedding model)
     - `gpt-4o-mini` (or your preferred chat model)

3. **Configure environment variables** - Set these in your activated virtual environment.

   > **Note:** A **single** `FOUNDRY_ENDPOINT` powers everything:
   > - The **memory provider** uses it internally for embeddings + memory extraction.
   > - The **chat agent** you talk to uses it via `FoundryChatClient`.
   >
   > Authentication is via `DefaultAzureCredential` (i.e. `az login`), so **no API key is required**.

   **Bash/Linux/macOS:**
   ```bash
   # Cosmos DB
   export COSMOS_ENDPOINT="https://<your-account>.documents.azure.com:443/"
   export COSMOS_DATABASE="ai_memory"

   # AI Foundry - used by BOTH the memory provider and the chat agent
   export FOUNDRY_ENDPOINT="https://<your-project>.services.ai.azure.com"
   export EMBEDDING_MODEL="text-embedding-3-large"
   export CHAT_MODEL="gpt-4o-mini"
   ```

   **PowerShell:**
   ```powershell
   # Cosmos DB
   $env:COSMOS_ENDPOINT="https://<your-account>.documents.azure.com:443/"
   $env:COSMOS_DATABASE="ai_memory"

   # AI Foundry - used by BOTH the memory provider and the chat agent
   $env:FOUNDRY_ENDPOINT="https://<your-project>.services.ai.azure.com"
   $env:EMBEDDING_MODEL="text-embedding-3-large"
   $env:CHAT_MODEL="gpt-4o-mini"
   ```

4. **Ensure Azure authentication** - The samples use `DefaultAzureCredential`, which tries:
   - Environment variables (service principal)
   - Managed identity (if running in Azure)
   - Azure CLI (`az login`)
   - Interactive browser login (fallback)

   For local development, the easiest option is: `az login`

5. **Run the sample** (ensure your virtual environment is activated):

   **Bash/Linux/macOS:**
   ```bash
   # Make sure venv is activated (you should see (.venv) in your prompt)
   python samples/interactive_chat.py
   ```

   **PowerShell:**
   ```powershell
   # Make sure venv is activated (you should see (.venv) in your prompt)
   python samples/interactive_chat.py
   ```

**Interactive sample features:**
- Chat naturally and tell the assistant your preferences
- Use `/new` to start a new thread (memories persist across threads)
- Use `/user <id>` to switch users (test memory isolation)
- Use `/quit` to exit

The interactive sample demonstrates:
- Real agent with memory integration
- Multi-turn conversations with memory persisting across threads
- Multi-user and multi-thread memory scoping

#### 3. **Interactive Chat with Custom Extraction (`samples/interactive_chat_custom_extraction.py`)**

The same interactive chat as above, but wired with a **custom memory-extraction prompt** so you can control *what* the pipeline extracts. It uses a coding-assistant rubric that classifies architectural and technical decisions as durable facts. See [Custom Memory Extraction Rubric](#custom-memory-extraction-rubric) below for how the `prompts_dir` seam works.

Run it the same way as the interactive chat (same prerequisites and environment variables):

```bash
python samples/interactive_chat_custom_extraction.py
```

### Custom Memory Extraction Rubric

You can control both **how often** memories are extracted and **what** gets extracted.

#### Control extraction cadence (`processor_config`)

`processor_config` sets how many turns pass between each pipeline step. The provider forwards these
to the toolkit client via its `cadence_thresholds` argument (no global environment mutation); keys you
omit fall back to the toolkit's environment/defaults. This applies only when the provider builds the
client, so pass `processor_config` together with the connection arguments rather than a pre-built
`memory_client`:

```python
memory_provider = CosmosMemoryContextProvider(
    cosmos_endpoint=...,
    foundry_endpoint=...,
    processor_config={
        "FACT_EXTRACTION_EVERY_N": 1,    # Extract after every turn
        "DEDUP_EVERY_N": 3,              # Deduplicate every 3 extractions
        "USER_SUMMARY_EVERY_N": 5,       # Update user profile every 5 turns
        "THREAD_SUMMARY_EVERY_N": 10,    # Summarize thread every 10 turns
    },
)
```

#### Customize the extraction prompt (`prompts_dir`)

To change *what* the LLM extracts and how it classifies memories, supply your own Prompty templates via `prompts_dir`. When set, the toolkit's extraction and summarization steps read their templates (including `extract_memories.prompty`) from that directory instead of the bundled defaults:

```python
memory_provider = CosmosMemoryContextProvider(
    cosmos_endpoint=...,
    foundry_endpoint=...,
    prompts_dir="./my_prompts",
)
```

The directory must contain the complete template set, since the loader resolves each template by name with no fallback to the bundled copies. The simplest way to customize just the extraction rubric is to copy the toolkit's bundled templates and edit `extract_memories.prompty` (keeping its inputs and JSON output schema intact). See `samples/interactive_chat_custom_extraction.py` for a working example that builds this directory at runtime, so the custom prompt stays compatible with the installed toolkit's schema.

### Configuration

```python
memory_provider = CosmosMemoryContextProvider(
    source_id="cosmos_memory",                    # Provider identifier
    cosmos_endpoint="https://...",                # Cosmos DB endpoint
    cosmos_database="ai_memory",                  # Database name
    foundry_endpoint="https://...",               # AI Foundry endpoint
    credential=DefaultAzureCredential(),          # Azure credential

    # Memory retrieval options
    top_k=5,                                      # Number of memories to retrieve
    min_confidence=0.7,                           # Minimum confidence score (0.0-1.0)
    memory_types=["fact", "procedural"],          # Types to retrieve

    # Processing options
    auto_extract=True,                            # Auto-extract memories after runs
    processor_config={                            # Optional processor settings
        "FACT_EXTRACTION_EVERY_N": 1,            # Extract facts every N turns
        "DEDUP_EVERY_N": 5,                      # Deduplicate every N extractions
    }
)
```

### Memory Types

The provider retrieves four types of memories:

| Type | Description | Default TTL |
|------|-------------|-------------|
| **fact** | Declarative knowledge ("user prefers dark mode") | None |
| **procedural** | Behavioral rules ("always confirm before deleting") | None |
| **episodic** | Past experiences with context and outcomes | 90 days |
| **unclassified** | Memories that couldn't be confidently classified | None |

Each memory has a confidence score (0.0-1.0). Use `min_confidence` to filter low-quality extractions.

### Processing Pipeline

The memory toolkit automatically:

1. **Stores conversation turns** - Raw messages saved to Cosmos DB
2. **Extracts memories** - LLM extracts facts, rules, and experiences
3. **Generates summaries** - Thread and user-level summaries
4. **Reconciles duplicates** - Merges similar memories and resolves contradictions

Processing can run:
- **In-process** (default) - Zero infrastructure, suitable for prototypes and low TPS
- **Azure Functions** - Scalable processing via Cosmos DB change feed

### Working with Multiple Providers

Combine with other context providers for comprehensive memory:

```python
from agent_framework import InMemoryHistoryProvider
from agent_framework_azure_cosmos import CosmosHistoryProvider
from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

agent = client.as_agent(
    context_providers=[
        # Short-term: recent conversation
        InMemoryHistoryProvider("recent"),

        # Mid-term: persistent conversation history
        CosmosHistoryProvider(
            endpoint=cosmos_endpoint,
            credential=credential,
            database_name="agent-framework",
            container_name="chat-history",
        ),

        # Long-term: semantic memory with facts and profiles
        CosmosMemoryContextProvider(
            cosmos_endpoint=cosmos_endpoint,
            foundry_endpoint=foundry_endpoint,
            credential=credential,
        ),
    ]
)
```

### User and Thread Scoping

Memories are scoped by `user_id` and `thread_id`:

```python
session = agent.create_session()

# Set user_id and thread_id in the provider-scoped state (keyed by the provider's source_id)
scoped = session.state.setdefault("cosmos_memory", {})
scoped["user_id"] = "user-123"
scoped["thread_id"] = "thread-456"

await agent.run("Remember that I'm allergic to peanuts.", session=session)
```

If not provided, the provider uses `session.session_id` as both user and thread identifiers.

### Advanced: Custom Processing

For fine-grained control over memory processing:

```python
from azure.cosmos.agent_memory.aio import AsyncCosmosMemoryClient

# Create a custom memory client. To disable automatic extraction, zero the cadence thresholds
# on the client you build - the provider cannot reconfigure a client you pass in, so supplying
# a memory_client together with auto_extract=False or processor_config raises ValueError.
memory_client = AsyncCosmosMemoryClient(
    cosmos_endpoint=cosmos_endpoint,
    cosmos_database="ai_memory",
    ai_foundry_endpoint=ai_foundry_endpoint,
    use_default_credential=True,
    cadence_thresholds={
        "FACT_EXTRACTION_EVERY_N": 0,
        "THREAD_SUMMARY_EVERY_N": 0,
        "USER_SUMMARY_EVERY_N": 0,
    },
)

# Pass to the provider
memory_provider = CosmosMemoryContextProvider(
    memory_client=memory_client,
)

# Manually trigger processing when needed
await memory_client.process_now(user_id="user-123", thread_id="thread-456")
```

> To let the provider disable extraction for you, omit `memory_client` and pass `auto_extract=False`
> with the connection arguments instead - the provider then builds the client with the extraction
> and summary steps zeroed.

### Environment Variables

All configuration can be provided via environment variables:

**Using a `.env` file** (cross-platform, recommended):
```bash
COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE=ai_memory
FOUNDRY_ENDPOINT=https://<project>.services.ai.azure.com
EMBEDDING_MODEL=text-embedding-3-large
CHAT_MODEL=gpt-4o-mini

# Optional: Processing configuration
FACT_EXTRACTION_EVERY_N=1
DEDUP_EVERY_N=5
THREAD_SUMMARY_EVERY_N=10
USER_SUMMARY_EVERY_N=20
```

**Or set in your shell session:**

Bash/Linux/macOS:
```bash
export COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
export COSMOS_DATABASE=ai_memory
export FOUNDRY_ENDPOINT=https://<project>.services.ai.azure.com
```

PowerShell:
```powershell
$env:COSMOS_ENDPOINT="https://<account>.documents.azure.com:443/"
$env:COSMOS_DATABASE="ai_memory"
$env:FOUNDRY_ENDPOINT="https://<project>.services.ai.azure.com"
```

## See Also

- [Azure Cosmos DB Agent Memory Toolkit](https://github.com/AzureCosmosDB/AgentMemoryToolkit)
- [Agent Framework Context Providers](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/context-providers?pivots=programming-language-python)
- [agent-framework-azure-cosmos](https://pypi.org/project/agent-framework-azure-cosmos/) - For basic history and checkpoint storage
