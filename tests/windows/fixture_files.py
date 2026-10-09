"""Public command-file publication for bounded native fixture helpers."""
import json
from uuid import uuid4


def publish_gate(path, value):
    temporary = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
    try:
        temporary.write_text(json.dumps(value))
        temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)
