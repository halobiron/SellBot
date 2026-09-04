from app.agent_core.agent_engine import unsupported_node
from app.agent_core.intent import normalize_intent_scope


def test_unsupported_response_is_authored_by_the_model_not_a_template():
    intent = normalize_intent_scope({
        "unsupported_product": "tivi",
        "related_categories": ["Màn hình máy tính"],
        "unsupported_reply": "Ông đang tìm tivi thì tiếc là cửa hàng chưa có. Nếu mục đích là xem nội dung từ máy tính, cháu có thể giới thiệu màn hình phù hợp.",
    }, ["Màn hình máy tính"])

    out = unsupported_node({"intent": intent, "history": []}, {"configurable": {}})

    assert out["response"] == intent["unsupported_reply"]
    assert "anh/chị" not in out["response"]


def test_unsupported_reply_is_discarded_when_there_is_no_unsupported_product():
    intent = normalize_intent_scope({
        "category": "Màn hình máy tính",
        "unsupported_reply": "Câu trả lời không được phép phát ở nhánh này.",
    }, ["Màn hình máy tính"])
    assert intent["unsupported_reply"] is None
