import { Agent, defineTool } from "@microsoft/agent-framework-core";
import { OpenAIChatCompletionClient } from "@microsoft/agent-framework-openai";

const getWeather = defineTool({
  name: "get_weather",
  description: "Get the current weather for a city.",
  parameters: {
    type: "object",
    properties: {
      city: { type: "string", description: "The city name." },
    },
    required: ["city"],
    additionalProperties: false,
  },
  execute: ({ city }) => `${String(city)}: 21 C and sunny`,
});

const agent = new Agent({
  name: "WeatherAgent",
  client: new OpenAIChatCompletionClient(),
  instructions: "Answer weather questions concisely.",
  tools: [getWeather],
});

const response = await agent.run("What is the weather in Seattle?");
console.log(response.text);
