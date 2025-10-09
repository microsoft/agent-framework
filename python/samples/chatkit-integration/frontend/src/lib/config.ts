// ChatKit configuration for the weather agent demo

import { StartScreenPrompt } from "@openai/chatkit";

export const THEME_STORAGE_KEY = "weather-agent-theme";

export const CHATKIT_API_URL = "/chatkit";
export const CHATKIT_API_DOMAIN_KEY =
  import.meta.env.VITE_CHATKIT_API_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export const GREETING =
  "👋 Hello! I'm your weather assistant. I can help you get weather information for any location and tell you the current time. What would you like to know?";

export const STARTER_PROMPTS: StartScreenPrompt[] = [
  {
    label: "Weather in New York",
    prompt: "What's the weather in New York?",
    icon: "compass",
  },
  {
    label: "Weather in London",
    prompt: "Tell me the weather in London",
    icon: "compass",
  },
  {
    label: "Current Time",
    prompt: "What time is it?",
    icon: "sparkle",
  },
  {
    label: "Weather in Tokyo",
    prompt: "What's the weather like in Tokyo?",
    icon: "compass",
  },
  {
    label: "Weather in San Francisco",
    prompt: "Get weather for San Francisco",
    icon: "compass",
  },
];
