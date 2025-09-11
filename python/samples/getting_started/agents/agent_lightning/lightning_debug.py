# type: ignore

import pandas as pd
from agentlightning import DevTaskLoader, Trainer, LLM, configure_logger
from lightning_client import Tau2Agent

from _tau2_helper import _to_native


def dev_task_loader() -> DevTaskLoader:
    dataset = pd.read_parquet("data/tasks_train.parquet")
    tasks = [_to_native(row.to_dict()) for _, row in dataset.iterrows()]

    return DevTaskLoader(
        tasks=tasks,
        resources={
            "main_llm": LLM(endpoint=proxy_base_url, model="gpt-4.1-mini", sampling_parameters={"temperature": 0.0}),
        },
    )


if __name__ == "__main__":
    configure_logger()
    trainer = Trainer(n_workers=1, dev=True, max_tasks=10)
    agent = Tau2Agent(trained_agents="assistant_agent")
    trainer.fit(agent, "http://localhost:9999/", dev_task_loader())
