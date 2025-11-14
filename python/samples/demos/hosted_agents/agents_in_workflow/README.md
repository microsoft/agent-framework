# Hosted Workflow Agents Demo

This demo showcases an agent that is backed by a workflow of multiple agents running concurrently, hosted as an agent endpoint in a Docker container.

## What the Project Does

This project demonstrates how to:

- Build a workflow of agents using the Agent Framework
- Host the workflow agent as an agent endpoint running in a Docker container

The agent responds to product launch strategy inquiries by concurrently leveraging insights from three specialized agents:

- **Researcher Agent** - Provides market research insights
- **Marketer Agent** - Crafts marketing value propositions and messaging
- **Legal Agent** - Reviews for compliance and legal considerations

## Prerequisites

- OpenAI API access and credentials
- Required environment variables (see Configuration section)

## Configuration

Follow the `.env.example` file to set up the necessary environment variables for OpenAI.

## Docker Deployment

Build and run using Docker:

```bash
# Build the Docker image
docker build -t hosted-agent-workflow .

# Run the container
docker run -p 8088:8088 hosted-agent-workflow
```

> If you update the environment variables in the `.env` file or change the code or the dockerfile, make sure to rebuild the Docker image to apply the changes.

## Testing the Agent

Once the agent is running, you can test it by sending queries that contain the trigger keywords. For example:

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses -d '{"input": "We are launching a new budget-friendly electric bike for urban commuters.","stream":false}'
```

> Expected response is not shown here for brevity. The response will include insights from the researcher, marketer, and legal agents based on the input prompt.
