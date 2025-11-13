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

- OpenAI API access and credentials
- Required environment variables (see Configuration section)

## Configuration

Follow the `.env.example` file to set up the necessary environment variables for OpenAI.

## Docker Deployment

Build and run using Docker:

```bash
# Build the Docker image
docker build -t hosted-agent-rag .

# Run the container
docker run -p 8088:8088 hosted-agent-rag
```

> If you update the environment variables in the `.env` file or change the code or the dockerfile, make sure to rebuild the Docker image to apply the changes.

## Testing the Agent

Once the agent is running, you can test it by sending queries that contain the trigger keywords. For example:

```bash
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses -d '{"input": "What is the return policy","stream":false}'
```

Expected response:

```bash
{"object":"response","metadata":{},"agent":null,"conversation":{"id":"conv_2GbSxDpJJ89B6N4FQkKhrHaz78Hjtxy9b30JEPuY9YFjJM0uw3"},"type":"message","role":"assistant","temperature":1.0,"top_p":1.0,"user":"","id":"resp_Bvffxq0iIzlVkx2I8x7hV4fglm9RBPWfMCpNtEpDT6ciV2IG6z","created_at":1763071467,"output":[{"id":"msg_2GbSxDpJJ89B6N4FQknLsnxkwwFS2FULJqRV9jMey2BOXljqUz","type":"message","status":"completed","role":"assistant","content":[{"type":"output_text","text":"As of the most recent update, Contoso Outdoors' return policy allows customers to return products within 30 days of purchase for a full refund or exchange, provided the items are in their original condition and packaging. However, make sure to check your purchase receipt or the company's website for the most updated and specific details, as policies can vary by location and may change over time.","annotations":[],"logprobs":[]}]}],"parallel_tool_calls":true,"status":"completed"}
```
