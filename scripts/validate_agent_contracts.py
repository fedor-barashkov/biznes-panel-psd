#!/usr/bin/env python3
"""Validate Construction AI JSON Schemas and positive/negative fixtures."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "docs" / "AGENTS" / "contracts" / "schemas"
FIXTURE_DIR = ROOT / "docs" / "AGENTS" / "contracts" / "fixtures"
FORMAT_CHECKER = FormatChecker()


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    errors: list[str] = []
    schemas = sorted(SCHEMA_DIR.glob("*.schema.json"))
    if not schemas:
        print("ERROR: no schemas found")
        return 2

    schema_map = {}
    for path in schemas:
        try:
            schema = load_json(path)
            Draft202012Validator.check_schema(schema)
            schema_map[path.name.removesuffix(".schema.json")] = schema
            print(f"SCHEMA OK  {path.relative_to(ROOT)}")
        except Exception as exc:  # report malformed JSON and invalid schemas
            errors.append(f"SCHEMA ERROR {path}: {exc}")

    fixtures = sorted(FIXTURE_DIR.glob("*.json"))
    if not fixtures:
        errors.append("No contract fixtures found")

    for path in fixtures:
        name = path.name
        expected_valid = name.endswith(".valid.json")
        expected_invalid = name.endswith(".invalid.json")
        if not (expected_valid or expected_invalid):
            errors.append(f"Fixture suffix must be .valid.json or .invalid.json: {path}")
            continue
        stem = name.removesuffix(".valid.json").removesuffix(".invalid.json")
        schema = schema_map.get(stem)
        if schema is None:
            errors.append(f"No matching schema for fixture: {path}")
            continue
        try:
            instance = load_json(path)
            validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
            violations = list(validator.iter_errors(instance))
            passed = not violations
            if expected_valid and not passed:
                details = "; ".join(
                    f"{list(error.absolute_path)}: {error.message}" for error in violations
                )
                errors.append(f"EXPECTED VALID but rejected {path}: {details}")
            elif expected_invalid and passed:
                errors.append(f"EXPECTED INVALID but accepted {path}")
            else:
                print(f"FIXTURE OK {path.relative_to(ROOT)} ({'valid' if expected_valid else 'invalid'} as expected)")
        except Exception as exc:
            errors.append(f"FIXTURE ERROR {path}: {exc}")

    if errors:
        print("\nVALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"\nVALIDATION PASSED: {len(schemas)} schemas; {len(fixtures)} fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
