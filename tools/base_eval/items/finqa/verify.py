import ast
import json
import math
import re
import sys
from pathlib import Path

FIELDS = {
    "id": str,
    "context": str,
    "question": str,
    "answer": (int, float),
    "unit": str,
    "answer_format": str,
    "program": str,
    "steps": int,
}
OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
SCALE_WORDS = ("thousand", "million", "billion")


def safe_eval(node):
    if isinstance(node, ast.Expression):
        return safe_eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](safe_eval(node.left), safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -safe_eval(node.operand)
    raise ValueError(f"unsupported syntax: {ast.dump(node)}")


def program_numbers(tree):
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)]


def context_numbers(text):
    return {float(m.replace(",", "")) for m in NUMBER.findall(text)}


def structural_set(item):
    allowed = set(range(1, 11))
    if item["unit"] in ("percent", "percentage_points"):
        allowed.add(100)
    text = (item["context"] + " " + item["question"]).lower()
    if any(word in text for word in SCALE_WORDS):
        allowed.update({1000, 1000000})
    return allowed


def check_item(item):
    problems = []
    for name, kind in FIELDS.items():
        if name not in item:
            problems.append(f"missing field {name}")
        elif not isinstance(item[name], kind) or isinstance(item[name], bool):
            problems.append(f"field {name} has wrong type")
    if problems:
        return problems, []
    if not 1 <= item["steps"] <= 4:
        problems.append(f"steps {item['steps']} outside 1..4")
    tree = ast.parse(item["program"], mode="eval")
    value = safe_eval(tree)
    if not math.isclose(value, item["answer"], rel_tol=1e-9, abs_tol=0.0):
        problems.append(f"program gives {value!r}, answer is {item['answer']!r}")
    found = context_numbers(item["context"])
    allowed = structural_set(item)
    structural = []
    for number in program_numbers(tree):
        if float(number) in found:
            continue
        if number in allowed:
            structural.append(number)
            continue
        problems.append(f"number {number} not in context")
    return problems, structural


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("questions.json")
    items = json.loads(path.read_text(encoding="utf-8"))
    ids = [item.get("id") for item in items]
    failures = 0
    if len(set(ids)) != len(ids):
        print("FAIL duplicate ids")
        failures += 1
    for item in items:
        problems, structural = check_item(item)
        note = f" structural={structural}" if structural else ""
        if problems:
            failures += 1
            print(f"FAIL {item.get('id')}: " + "; ".join(problems))
        else:
            print(f"PASS {item['id']} answer={item['answer']!r} unit={item['unit']} steps={item['steps']}{note}")
    passed = len(items) - failures
    print(f"items={len(items)} passed={passed} failed={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
