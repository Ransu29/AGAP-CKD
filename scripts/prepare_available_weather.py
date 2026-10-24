"""Prepare downloaded historical weather without requiring a climate baseline."""
import argparse
import json
from agap.climate.available import prepare_available_weather
from agap.config import ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--start", default="2021-01-01")
parser.add_argument("--end", default="2024-12-31")
args = parser.parse_args()
print(json.dumps(prepare_available_weather(ROOT, args.start, args.end), indent=2))
