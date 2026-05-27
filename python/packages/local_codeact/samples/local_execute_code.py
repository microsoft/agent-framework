# Copyright (c) Microsoft. All rights reserved.

"""This sample demonstrates configuring and invoking Local CodeAct without Foundry hosting.

Local CodeAct executes LLM-generated Python in the local agent environment. This
sample is meant for a disposable sandbox, container, or VM. It shows the
configuration surface directly on `LocalExecuteCodeTool`: host tools, explicit
environment variables, workspace/file mounts, execution limits, and subprocess
execution mode.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from agent_framework import Content

from agent_framework_local_codeact import FileMount, LocalExecuteCodeTool, ProcessExecutionLimits


def convert_usd_to_eur(amount: float) -> dict[str, float]:
    """Convert a USD amount with a fixed demonstration exchange rate."""
    return {"usd": amount, "eur": round(amount * 0.92, 2)}


def describe_content(content: Content) -> str:
    """Return a short printable description for sample output."""
    if content.type == "text":
        return f"Text: {content.text}"
    if content.type == "data":
        return f"Data: {content.additional_properties.get('path')}"
    if content.type == "error":
        return f"Error: {content.error_details}"
    return f"{content.type}: {content}"


async def main() -> None:
    """Run a local execute-code call with representative configuration."""
    with tempfile.TemporaryDirectory(prefix="local-codeact-sample-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        workspace = temp_dir / "workspace"
        output_dir = temp_dir / "output"
        workspace.mkdir()
        output_dir.mkdir()
        (workspace / "amounts.txt").write_text("12.50\n7.50\n", encoding="utf-8")

        # 1. Configure the local execute-code tool.
        execute_code = LocalExecuteCodeTool(
            tools=[convert_usd_to_eur],
            approval_mode="never_require",
            workspace_root=workspace,
            file_mounts=[
                FileMount(
                    host_path=output_dir,
                    mount_path="/output",
                    mode="read-write",
                    write_bytes_limit=1024 * 1024,
                )
            ],
            execution_limits=ProcessExecutionLimits(
                timeout_seconds=5,
                max_code_bytes=16 * 1024,
                max_stdout_bytes=4 * 1024,
                max_stderr_bytes=4 * 1024,
                max_result_bytes=8 * 1024,
                max_captured_file_bytes=1024 * 1024,
                max_total_captured_file_bytes=2 * 1024 * 1024,
            ),
            env={"REPORT_TITLE": "Local CodeAct sample report"},
            execution_mode="subprocess",
            python_executable=sys.executable,
        )

        # 2. Execute generated Python. In a real agent run, the model would
        #    produce this code and call the `execute_code` tool.
        code = f"""
import os
from pathlib import Path

amounts = [
    float(line)
    for line in Path({str(workspace / "amounts.txt")!r}).read_text(encoding="utf-8").splitlines()
    if line
]
converted = await convert_usd_to_eur(amount=sum(amounts))

report_path = Path({str(output_dir / "report.txt")!r})
report_path.write_text(
    f"{{os.environ['REPORT_TITLE']}}\\nUSD: {{converted['usd']}}\\nEUR: {{converted['eur']}}\\n",
    encoding="utf-8",
)

print(os.environ["REPORT_TITLE"])
converted
"""

        # 3. Print text results and any captured files returned as data content.
        results = await execute_code.invoke(arguments={"code": code})
        for content in results:
            print(describe_content(content))


if __name__ == "__main__":
    asyncio.run(main())
