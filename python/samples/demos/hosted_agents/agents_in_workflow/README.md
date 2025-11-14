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

## Testing the Agent

> If you update the environment variables in the `.env` file or change the code or the dockerfile, make sure to rebuild the Docker image to apply the changes.

Coming soon!
