# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses a local shell tool and a code interpreter tool for working with files, and hosted using the **Responses protocol**.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. The agent supports both streaming (SSE events) and non-streaming (JSON) response modes.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

### Tools

This agent uses two tools:

1. **Local Shell Tool (`run_bash`)** – Executes shell commands locally to perform filesystem operations such as listing files, reading file contents, or creating directories. The tool captures stdout, stderr, and the exit code of the command and returns them as a string.
2. **Code Interpreter Tool (`code_interpreter`)** – Allows the agent to execute Python code in a safe, sandboxed environment. This tool can be used to read and manipulate file contents, perform calculations, or run other Python logic as part of the agent's responses.

> In this sample, the local shell tool is a function tool defined in Python using the `@tool` decorator from the Agent Framework. The code interpreter tool is a managed tool provided by [Foundry Toolbox](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox). Learn more about foundry toolbox integration with hosted agents with this [sample](../04_foundry_toolbox/).

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

An extra environoment variable `TOOLBOX_NAME` must be set to the name of the Foundry Toolbox that the agent should load at runtime. This allows the agent host to dynamically retrieve the correct toolbox from Foundry when it starts. Run the following:

```bash
export TOOLBOX_NAME="<your-toolbox-name>"
```

Or in PowerShell:

```powershell
$env:TOOLBOX_NAME="<your-toolbox-name>"
```

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Find the quarterly report under `{cwd}/resources` and tell me the difference of revenue between q1 2026 and q1 2025?"}'
```

The server will respond with a JSON object containing the response text and a response ID. You can use this response ID to continue the conversation in subsequent requests.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

## Uploading a file to a session

Deploying the agent won't automatically upload the files included with this sample to Foundry. To make these files available to the agent at runtime, you must upload them to a [hosted agent session](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions). Files are tied to a specific hosted agent session, so each time you start a new session you will need to upload the files again if the agent needs access to them during that session.

After you deploy the agent to Foundry, you have two ways to interact with the agent:

1. Using `azd ai agent invoke`.
2. Through the Foundry portal.

### Using `azd ai agent invoke`

After successfully deploying the agent to Foundry, run the following command:

> You must remain in the directory where your `azd` project is initialized so that the CLI can locate the deployed agent configuration.

```bash
azd ai agent invoke "Hi!"
```

The command will invoke the agent and the server will create a new session if one does not already exist for this interaction, returning the agent's response from the hosted agent session. Run the following if you want to force a new session:

```bash
azd ai agent invoke --new-session "Hi!"
```

Run the following command to upload a file to the hosted agent session:

```bash
azd ai agent files upload -f <path-to-contoso-q1-2026-report.text>
```

> The above command will automatically detect the last active session and upload the file to that session without requiring you to explicitly provide a session ID. It is also possible to specify a particular session ID to upload the file to a specific hosted agent session by using the `--session-id` flag. Run `azd ai agent files upload -h` to see the full list of options and flags available for the `upload` command.

Once the file is uploaded to the hosted agent session, the agent will be able to access it during that session and use it to respond to queries that reference the uploaded file.

Invoke the agent again with a query that references the uploaded file to see how it can now use the file in its responses. For example:

```bash
azd ai agent invoke "Find the quarterly report under the home directory and tell me the difference of revenue between q1 2026 and q1 2025?"
```

### Using the Foundry Portal

Similar to using the `azd` CLI, you must invoke the agent first to create a session:

![alt text](./resources/start-a-session.png)

Once the session is created, you can grad the session ID and use `azd ai agent files upload --session-id <session-id>` to upload files to that specific hosted agent session.

![alt text](./resources/session-started.png)

Or you can upload files directly through the Foundry portal by navigating to Files tab in the agent playground:

![alt text](./resources/file-upload-portal.png)
