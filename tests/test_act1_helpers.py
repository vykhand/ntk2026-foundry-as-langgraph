"""The Act 1 smoke path parses Responses API objects correctly (no server needed)."""

from __future__ import annotations

from scripts.act1 import output_text, tool_calls

RESPONSE = {
    "id": "resp_123",
    "output": [
        {"type": "function_call", "name": "preferences", "arguments": "{}", "call_id": "c1"},
        {"type": "function_call_output", "call_id": "c1", "output": "{}"},
        {"type": "function_call", "name": "program_search", "arguments": "{}", "call_id": "c2"},
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Tukaj je urnik.\n"},
                {"type": "output_text", "text": '```json\n{"items": []}\n```'},
            ],
        },
    ],
}


def test_output_text_joins_message_parts_only():
    assert output_text(RESPONSE) == 'Tukaj je urnik.\n\n```json\n{"items": []}\n```'


def test_tool_calls_lists_function_calls_in_order():
    assert tool_calls(RESPONSE) == ["preferences", "program_search"]


def test_empty_response_is_handled():
    assert output_text({}) == ""
    assert tool_calls({"output": []}) == []
