# type: ignore

import os
import pandas as pd
import json

# Load train and test task IDs
train_tasks_df = pd.read_parquet("data/tasks_train_serialized.parquet")
test_tasks_df = pd.read_parquet("data/tasks_test_serialized.parquet")
train_task_ids = set(train_tasks_df["id"].tolist())
test_task_ids = set(test_tasks_df["id"].tolist())

for file_path in os.listdir("results"):
    if os.path.isdir(os.path.join("results", file_path)):
        continue

    all_data = []
    train_data = []
    test_data = []

    for line in open(os.path.join("results", file_path)):
        row_data = json.loads(line)
        all_data.append(row_data)

        task_id = row_data["task"]["id"]
        if task_id in train_task_ids:
            train_data.append(row_data)
        elif task_id in test_task_ids:
            test_data.append(row_data)

    all_accuracy = sum(d["evaluation"]["reward"] for d in all_data) / len(all_data)
    train_accuracy = sum(d["evaluation"]["reward"] for d in train_data) / len(train_data) if train_data else 0.0
    test_accuracy = sum(d["evaluation"]["reward"] for d in test_data) / len(test_data) if test_data else 0.0

    print(f"{file_path}:")
    print(f"  All: {all_accuracy:.4f} ({len(all_data)} tasks)")
    print(f"  Train: {train_accuracy:.4f} ({len(train_data)} tasks)")
    print(f"  Test: {test_accuracy:.4f} ({len(test_data)} tasks)")
