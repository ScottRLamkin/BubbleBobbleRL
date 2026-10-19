"""Exit 0 if a per-level evaluation JSON holds 99 levels x 10 valid outcomes."""
import json
import sys

d = json.load(open(sys.argv[1]))["per_level"]
ok = len(d) == 99 and all(len(v) == 10 and set(v) <= {"clear", "death", "timeout"} for v in d.values())
sys.exit(0 if ok else 1)
