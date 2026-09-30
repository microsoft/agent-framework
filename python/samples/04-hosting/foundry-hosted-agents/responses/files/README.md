# Session files (Responses protocol)

This agent reads **only explicitly uploaded UTF-8 files in `$HOME/sample_files`**
inside the current Foundry hosted sandbox. It does not expose the working
directory, accept arbitrary directories, or read the sample's packaged resources
automatically. `list_files()` lists regular uploads; `read_file(filename)` takes a
single filename, not a path.

The reader opens every directory component and the file without following
symlinks, using directory descriptors rather than a check-then-open pathname.
Replacing a directory or file with a symlink cannot redirect a read outside the
upload directory. It rejects traversal, absolute paths, Windows-style paths,
control characters, directory/file symlinks, non-regular files, invalid UTF-8 and
files larger than **1,000,000 bytes**. It checks size before reading, then uses a
bounded read to catch growth during the read. POSIX descriptor-relative,
`O_NOFOLLOW` and `O_DIRECTORY` support are required; unsupported platforms fail
closed rather than falling back to an unsafe reader.

## Prerequisites and lifecycle

Set `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`, plus either
`TOOLBOX_ENDPOINT` or `TOOLBOX_NAME`. The Toolbox needs a code-interpreter tool;
see the [Toolbox sample](../foundry_toolbox/). Authenticate local runs with
`az login`. Deployed runs use the sandbox's managed identity.

`ResponsesHostServer(agent=create_agent, history_source="agent_server")` creates
fresh clients and a Toolbox MCP connection for each request and closes their
transports afterward. The MCP writer therefore inherits **this** request's
platform call ID, not an earlier caller's. The outer Responses service supplies
history; the host disables downstream model storage. An outer `store=false`
request writes no host-managed state, but does not undo external tool side
effects or delete uploads.

Foundry session files and Toolbox code-interpreter container files are different
resources. Reading an upload returns its text; it does not mount that upload into
the Toolbox container. This sample does not implement native generated-file
citations or automatically close microsoft/agent-framework#7916.

## Upload and read locally

Run the host using the [parent instructions](../../README.md#running-the-agent-host-locally).
In the same environment and with the **same `HOME`**, explicitly stage the
packaged report:

```bash
uv run python upload_file.py resources/contoso_q1_2026_report.txt --local
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Read contoso_q1_2026_report.txt and compare Q1 revenue."}'
```

The helper applies the same bounded-read and symlink checks to the selected
source and destination. `--local` never calls Azure. Local query/body session IDs
do **not** create separate filesystem sandboxes: a local server is a single-user
development process. To simulate two sandboxes, run hosts with separate `HOME`
directories and upload only to the first. The second must list no uploads and
must not be able to read the first host's file. Do not expose this local server
as an authenticated multi-user production service.

## Upload to a hosted sandbox

Deploy using the [parent instructions](../../README.md#deploying-the-agent-to-foundry),
then create/select a Foundry hosted session and set `FOUNDRY_AGENT_NAME`.
Use the **Foundry `agent_session_id`**, not an outer `response.id`,
`previous_response_id`, conversation ID or MAF `AgentSession.session_id`.

```bash
uv run python upload_file.py resources/contoso_q1_2026_report.txt \
  --session-id "<sandbox-A>"
```

The SDK uploads to `sample_files/contoso_q1_2026_report.txt`, relative to that
sandbox's home directory. A portal/CLI upload to the home directory's root will
not be visible to these tools; specify the `sample_files/` destination, or use
this helper. No real upload is performed by the sample's offline tests.

Send the request to the deployed agent's Responses endpoint, routing to the same
sandbox. Responses supports the query selector:

```text
POST <responses-endpoint>?agent_session_id=<sandbox-A>
{"input":"Read contoso_q1_2026_report.txt and compare Q1 revenue."}
```

The equivalent body selector is:

```json
{
  "agent_session_id": "<sandbox-A>",
  "input": "Read contoso_q1_2026_report.txt and compare Q1 revenue."
}
```

Use **one** selector. Foundry routes it to the sandbox; the host validates the
resolved request identity against the platform-configured
`FOUNDRY_AGENT_SESSION_ID`. A mismatch fails closed. Neither a caller option nor
a filename can select another sandbox's home directory.

For a hosted isolation check, upload only to sandbox A and read there. Send the
same prompt to a fresh sandbox B without uploading: its `list_files()` must be
empty and the named read must fail. Upload separately to B if it needs the file.
Do not claim this live check ran unless those resources and uploads were
explicitly authorized.

## Offline checks

From `python/`, run:

```bash
uv run pytest samples/04-hosting/foundry-hosted-agents/responses/files/tests -q
```

The tests use temporary home directories, including descriptor-replacement
checks. They require no Foundry project, credentials, deployment or real files.
