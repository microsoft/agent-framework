# Hosted Agents with Text Search RAG Demo

This demo showcases an agent that uses Retrieval-Augmented Generation (RAG) with text search capabilities that will be hosted as an agent endpoint running locally in a Docker container.

## What the Project Does

This project demonstrates how to:

- Build a customer support agent using the Agent Framework
- Implement a custom `TextSearchContextProvider` that simulates document retrieval
- Host the agent as an agent endpoint running in a Docker container

The agent responds to customer inquiries about:

- **Return & Refund Policies** - Triggered by keywords: "return", "refund"
- **Shipping Information** - Triggered by keyword: "shipping"
- **Product Care Instructions** - Triggered by keywords: "tent", "fabric"

## Prerequisites

- Azure OpenAI API access and credentials
- Required environment variables (see Configuration section)

## Configuration

Follow the `.env.example` file to set up the necessary environment variables for Azure OpenAI.

## Testing the Agent

> If you update the environment variables in the `.env` file or change the code or the dockerfile, make sure to rebuild the Docker image to apply the changes.

Coming soon!
