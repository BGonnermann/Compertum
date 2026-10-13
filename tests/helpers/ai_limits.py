"""Observe native adapter limits without contacting any provider."""
import json
from compertum.runtime.managed import constrain_ai_adapter
print(json.dumps(constrain_ai_adapter()))
