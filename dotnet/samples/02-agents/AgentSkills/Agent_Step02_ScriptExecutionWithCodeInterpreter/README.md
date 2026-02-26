# Script Execution with Code Interpreter

This sample demonstrates how to use **Agent Skills** with **script execution** via the hosted code interpreter.

## What's Different from Step01?

In the [basic skills sample](../Agent_Step01_BasicSkills/), skills only provide instructions and resources as text. This sample adds **script execution** — the agent can load Python scripts from skill resources and execute them using the LLM provider's built-in code interpreter.

This is enabled by configuring `FileAgentSkillScriptExecutor.HostedCodeInterpreter()` on the skills provider options:

```csharp
var skillsProvider = new FileAgentSkillsProvider(
    skillPath: Path.Combine(AppContext.BaseDirectory, "skills"),
    options: new FileAgentSkillsProviderOptions
    {
        ScriptExecutor = FileAgentSkillScriptExecutor.HostedCodeInterpreter()
    });
```

## Skills Included

### password-generator
Generates secure passwords using a Python script with configurable length and complexity.
- `scripts/generate.py` — Password generation script
- `references/PASSWORD_GUIDELINES.md` — Recommended length and symbol sets by use case

## Project Structure

```
Agent_Step02_ScriptExecutionWithCodeInterpreter/
├── Program.cs
├── Agent_Step02_ScriptExecutionWithCodeInterpreter.csproj
└── skills/
    └── password-generator/
        ├── SKILL.md
        ├── scripts/
        │   └── generate.py
        └── references/
            └── PASSWORD_GUIDELINES.md
```

## Running the Sample

### Prerequisites
- .NET 10.0 SDK
- Azure OpenAI endpoint with a deployed model that supports code interpreter

### Setup
1. Set environment variables:
   ```bash
   export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
   export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
   ```

2. Run the sample:
   ```bash
   dotnet run
   ```

### Example

The sample asks the agent to generate a secure password. The agent:
1. Loads the password-generator skill
2. Reads the `generate.py` script via `read_skill_resource`
3. Executes the script using the code interpreter with appropriate parameters
4. Returns the generated password

## Learn More

- [Agent Skills Specification](https://agentskills.io/)
- [Step01: Basic Skills](../Agent_Step01_BasicSkills/) — Skills without script execution
- [Microsoft Agent Framework Documentation](../../../../../docs/)
