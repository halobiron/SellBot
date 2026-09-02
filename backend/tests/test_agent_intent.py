from app.llm.client import FakeLLM
import pytest

from app.agent_core.intent import IntentServiceUnavailableError, extract_intent
from tests.agent_helpers import make_db


class BoomLLM:
    def complete_json(self, system, user, schema_hint=""):
        raise RuntimeError("llm down")

    def complete_text(self, s, u):
        return ""

    def stream_text(self, s, u):
        yield ""


def _db(tmp_path):
    db = str(tmp_path / "i.db")
    make_db(db, [{"category": "Tủ Lạnh", "brand": "Toshiba", "price_clean": 12_000_000, "specs": {}},
                 {"category": "Máy giặt", "brand": "LG", "price_clean": 9_000_000, "specs": {}}])
    return db


def test_llm_intent_maps_fields(tmp_path):
    db = _db(tmp_path)
    llm = FakeLLM(json_responses=[{"category": "Tủ Lạnh", "budget_max": 20000000,
                                   "brand": "Toshiba", "priority_features": ["tiết kiệm điện"],
                                   "needs_clarification": False, "is_meta_inquiry": False,
                                   "clarification_questions": []}])
    intent = extract_intent("mua tủ lạnh toshiba dưới 20tr tiết kiệm điện", [], llm, db)
    assert intent["category"] == "Tủ Lạnh"
    assert intent["budget_max"] == 20000000
    assert intent["priority_features"] == ["tiết kiệm điện"]
    assert intent["needs_clarification"] is False


def test_llm_error_is_reported_to_the_caller(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(IntentServiceUnavailableError):
        extract_intent("mua tủ lạnh 15 triệu", [], BoomLLM(), db)


def test_code_request_is_off_topic_not_unsupported_product(tmp_path):
    db = _db(tmp_path)
    llm = FakeLLM(json_responses=[{
        "category": None, "unsupported_product": None,
        "is_chitchat": True, "is_policy_question": False,
        "needs_clarification": False,
    }])
    intent = extract_intent("hãy code cho tôi file C++ ra dòng Hello World", [], llm, db)
    assert intent["is_chitchat"] is True
    assert intent["unsupported_product"] is None
    assert intent["category"] is None


def test_intent_prompt_requires_short_general_knowledge_reply(tmp_path):
    db = _db(tmp_path)
    llm = FakeLLM(json_responses=[{
        "is_chitchat": True,
        "smalltalk_reply": "Kinh tế chính trị nghiên cứu kinh tế trong quan hệ với quyền lực xã hội.",
    }])
    intent = extract_intent("kinh tế chính trị là gì", [], llm, db)
    assert intent["is_chitchat"] is True
    assert intent["smalltalk_reply"]
    assert "BẮT BUỘC điền smalltalk_reply" in llm.calls[0][0]


def test_shopping_for_computer_to_code_is_not_off_topic(tmp_path):
    db = str(tmp_path / "shop-code.db")
    make_db(db, [{"category": "Máy tính để bàn", "brand": "Dell",
                  "price_clean": 15_000_000, "specs": {}}])
    llm = FakeLLM(json_responses=[{
        "category": "Máy tính để bàn", "is_chitchat": False,
        "unsupported_product": None,
        "needs_clarification": False,
    }])
    intent = extract_intent("tôi muốn mua máy tính để bàn để code", [], llm, db)
    assert intent["is_chitchat"] is False
    assert intent["category"] == "Máy tính để bàn"
