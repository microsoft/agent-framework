# type: ignore

import os
import pandas as pd
import json

for file_path in os.listdir("results"):
    all_data = []
    for line in open(os.path.join("results", file_path)):
        row_data = json.loads(line)
        all_data.append(row_data)
    accuracy = sum(d["evaluation"]["reward"] for d in all_data) / len(all_data)
    print(f"{file_path}: {accuracy}")
