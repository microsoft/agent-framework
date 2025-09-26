# Copyright (c) Microsoft. All rights reserved.

"""This sample performs RL training for a tau2 agent from `agent-framework-lab-tau2`.

It requires one GPU of at least 80GB of memory.
"""

# import asyncio
# from agent_framework.lab.tau2 import TAU2, TAU2TelemetryConfig

# async def main():
#     telemetry_config = TAU2TelemetryConfig(
#         enable_tracing=True,
#         trace_to_file=True,
#         file_path="tau2_traces.jsonl"
#     )
#     runner = TAU2(telemetry_config=telemetry_config)
#     await runner.run(run_task, level=1, max_n=5, parallel=2)
