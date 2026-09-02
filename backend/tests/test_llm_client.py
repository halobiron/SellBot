import ssl

from app.llm.client import FakeLLM, DeepSeekClient


def test_fake_llm_returns_queued():
    fake = FakeLLM(json_responses=[{"category": "tu_lanh"}], text_responses=["Chào anh"])
    assert fake.complete_json("s", "u") == {"category": "tu_lanh"}
    assert fake.complete_text("s", "u") == "Chào anh"


def test_extract_json_handles_fences():
    raw = "```json\n{\"a\": 1}\n```"
    assert DeepSeekClient._extract_json(raw) == {"a": 1}
    assert DeepSeekClient._extract_json('{"b": 2}') == {"b": 2}


def test_response_output_text_collects_only_visible_message_text():
    response = {
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [
                {"type": "output_text", "text": '{"a":'},
                {"type": "output_text", "text": "1}"},
            ]},
        ]
    }
    assert DeepSeekClient._response_output_text(response) == '{"a":1}'


def test_client_tls_context_does_not_depend_on_ssl_key_log(monkeypatch):
    monkeypatch.setenv("SSLKEYLOGFILE", r"C:\missing\sslkeys.log")
    client = DeepSeekClient("https://example.test/v1", "key", "model")
    assert isinstance(client._tls_context, ssl.SSLContext)
    assert client._tls_context.verify_mode == ssl.CERT_REQUIRED
