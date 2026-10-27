"""Disk cache for every LLM response (cost control + offline reproducibility)."""

import hashlib
import json
import os


class ResponseCache:
    def __init__(self, path="data/narration/cache"):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def key(self, agent, model, prompt):
        return hashlib.sha256(f"{agent}|{model}|{prompt}".encode("utf-8")).hexdigest()[:32]

    def get(self, key):
        p = os.path.join(self.path, key + ".json")
        if os.path.exists(p):
            self.hits += 1
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        self.misses += 1
        return None

    def put(self, key, record):
        with open(os.path.join(self.path, key + ".json"), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
