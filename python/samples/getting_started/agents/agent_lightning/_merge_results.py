# type: ignore

import os
import json

path = "results/09121631"

data = []
existing_ids = set()
for file in os.listdir(path):
    if file.endswith(".jsonl"):
        with open(os.path.join(path, file)) as f:
            for line in f:
                line_data = json.loads(line)
                if line_data["id"] in existing_ids:
                    continue
                existing_ids.add(line_data["id"])
                data.append(line_data)

data.sort(key=lambda x: int(x["id"]))
with open(f"{path}/merged.jsonl", "w") as f:
    for line_data in data:
        f.write(json.dumps(line_data, default=str) + "\n")
