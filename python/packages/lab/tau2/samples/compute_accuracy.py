# Copyright (c) Microsoft. All rights reserved.

import json
import os
import re

results = []

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

    all_accuracy = sum(d["evaluation"]["reward"] for d in all_data) / len(all_data)
    failed = sum(d.get("error") is not None for d in all_data)

    print(f"{file_path}:")
    print(f"  All: {all_accuracy:.4f} ({len(all_data)} tasks)")
    print(f"  Failed: {failed} tasks")

    # Parse filename to extract model and window size
    match = re.match(r"(.+?)(?:_sw-(\d+))?_user-.+?\.jsonl$", file_path)
    if match:
        model = match.group(1)
        window_size = match.group(2) if match.group(2) else "N/A"

        # Extract user simulator from filename
        user_match = re.search(r"_user-([^_]+)", file_path)
        user_simulator = user_match.group(1) if user_match else "N/A"

        results.append(
            {
                "model": model,
                "window_size": window_size,
                "user_simulator": user_simulator,
                "all_accuracy": all_accuracy,
            }
        )

print("\n" + "=" * 80)
print("SUMMARY TABLE")
print("=" * 80)
print("Assistant window\tUser simulator\tAccuracy (all)\tAccuracy (train subset)\tAccuracy (test subset)")

for result in results:
    print(f"{result['model']}\t{result['window_size']}\t{result['user_simulator']}\t{result['all_accuracy']:.2f}")
