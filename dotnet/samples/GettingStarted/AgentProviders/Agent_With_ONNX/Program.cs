// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to create and use a simple AI agent with ONNX as the backend.
// WARNING: ONNX doesn't support function calling, so any function tools passed to the agent will be ignored.

using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.ML.OnnxRuntimeGenAI;

// E.g. C:\repos\Phi-4-mini-instruct-onnx\cpu_and_mobile\cpu-int4-rtn-block-32-acc-level-4
var modelPath = Environment.GetEnvironmentVariable("ONNX_MODEL_PATH") ?? throw new InvalidOperationException("ONNX_MODEL_PATH is not set.");

// Get a chat client for ONNX and use it to construct an AIAgent.
using OnnxRuntimeGenAIChatClient chatClient = new(modelPath);
AIAgent agent = chatClient.CreateAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Invoke the agent and output the text result.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
