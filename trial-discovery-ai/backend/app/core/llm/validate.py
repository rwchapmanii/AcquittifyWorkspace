import json
from jsonschema import validate, ValidationError

from app.core.llm.client import LLMClient
from app.core.llm.prompts import (
    build_pass1_repair_prompt,
    build_pass2_repair_prompt,
    build_pass4_repair_prompt,
)


class ValidationResult:
    def __init__(self, ok: bool, error: str | None = None) -> None:
        self.ok = ok
        self.error = error


def validate_json(data: dict, schema: dict) -> ValidationResult:
    try:
        validate(instance=data, schema=schema)
        return ValidationResult(ok=True)
    except ValidationError as exc:
        return ValidationResult(ok=False, error=str(exc))


def repair_json(raw_text: str) -> dict:
    # placeholder repair: attempt to parse directly
    return json.loads(raw_text)


def repair_json_with_llm(
    *, raw_text: str, schema: dict, model: str, pass_num: int
) -> dict:
    client = LLMClient()
    if pass_num == 1:
        prompt = build_pass1_repair_prompt(raw_text, json.dumps(schema))
    elif pass_num == 2:
        prompt = build_pass2_repair_prompt(raw_text, json.dumps(schema))
    elif pass_num == 4:
        prompt = build_pass4_repair_prompt(raw_text, json.dumps(schema))
    else:
        prompt = build_pass1_repair_prompt(raw_text, json.dumps(schema))
    repaired_text = client.complete_text(prompt=prompt, model=model, temperature=0.0)
    return json.loads(repaired_text)
