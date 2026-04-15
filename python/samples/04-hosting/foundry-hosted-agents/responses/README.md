# Hosting agents with Foundry Hosting and the `responses` API

This folder contains a list of samples that show how to host agents using the `responses` API and deploy them to Foundry Hosting.

| Sample | Description |
| --- | --- |
| [01_basic](./01_basic) | A basic example of hosting an agent with the `responses` API and carrying on a multi-turn conversation. |
| [02_local_tools](./02_local_tools) | An example of hosting an agent with the `responses` API and local tools including a function tool and a local shell tool. |
| [03_remote_mcp](./03_remote_mcp) | An example of hosting an agent with the `responses` API and remote MCPs, including a GitHub MCP server and a Foundry Toolboox. |
| [04_workflows](./04_workflows) | An example of hosting a workflow with the `responses` API. |

## Running the server locally

Navigate to the sample directory and run the following command to start the server:

```bash
python main.py
```

## Interacting with the agent

There two ways to interact with the agent: sending HTTP requests to the server or using the `azd` CLI:

### Invoke with `azd`

```bash
azd ai agent invoke --local "Hi"
```

### Sending HTTP requests

Send a POST request to the server with a JSON body containing a "message" field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "Hi"}'
```

> See the individual samples for more examples of interacting with the agent.

## Deploying to a Docker container

Navigate to the sample directory and build the Docker image:

```bash
docker build -t hosted-agent-sample .
```

Run the container, passing in the required environment variables:

```bash
docker run -p 8088:8088 \
  -e FOUNDRY_PROJECT_ENDPOINT=<your-endpoint> \
  -e FOUNDRY_MODEL=<your-model> \
  hosted-agent-sample
```

The server will be available at `http://localhost:8088`. You can send requests using the same `curl` command shown above.

## Deploying to Foundry

TODO

## Using the deployed agent in Agent Framework

After deploying the agent, you can also try to use the agent in Agent Framework. Refer to the [using_deployed_agent.py](./using_deployed_agent.py) sample for an example of how to do this.
