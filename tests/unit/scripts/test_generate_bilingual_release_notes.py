"""Tests for OpenRouter-powered bilingual release notes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module():
    script = Path(__file__).resolve().parents[3] / "scripts" / "generate_bilingual_release_notes.py"
    spec = importlib.util.spec_from_file_location("generate_bilingual_release_notes", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notes = _load_module()


def test_payload_requests_strict_structured_output():
    payload = notes.build_openrouter_payload("## Features\n- Add updates", "test/model")

    assert payload["model"] == "test/model"
    assert payload["provider"]["require_parameters"] is True
    json_schema = payload["response_format"]["json_schema"]
    assert json_schema["strict"] is True
    assert json_schema["schema"]["required"] == ["english_markdown", "polish_markdown"]


def test_extract_and_render_bilingual_notes():
    response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "english_markdown": "### Features\n- Add updates",
                            "polish_markdown": "### Funkcje\n- Dodano aktualizacje",
                        }
                    )
                }
            }
        ]
    }

    english, polish = notes.extract_bilingual_notes(response)
    body = notes.render_bilingual_body(english, polish)

    assert body.startswith("## English\n\n")
    assert "## Polski\n\n" in body
    assert "Dodano aktualizacje" in body


def test_parse_release_version():
    assert notes.parse_release_version("chore(main): release blackbone v0.1.0") == "0.1.0"


def test_polish_changelog_entry_is_inserted_and_replaced():
    original = "# Dziennik zmian\n\nOpis.\n"

    inserted = notes.upsert_polish_changelog_entry(original, "0.1.0", "## 0.1.0\n\nPierwsza wersja")
    replaced = notes.upsert_polish_changelog_entry(inserted, "0.1.0", "## 0.1.0\n\nPoprawiona wersja")

    assert "Pierwsza wersja" not in replaced
    assert "Poprawiona wersja" in replaced
    assert replaced.count("blackbone-release:0.1.0:start") == 1


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"english_markdown": "English only"}),
        json.dumps({"english_markdown": "same", "polish_markdown": "same"}),
    ],
)
def test_invalid_model_output_is_rejected(content):
    response = {"choices": [{"message": {"content": content}}]}

    with pytest.raises(ValueError):
        notes.extract_bilingual_notes(response)
