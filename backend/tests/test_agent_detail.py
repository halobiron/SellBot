from app.llm.client import FakeLLM
from app.agent_core.detail import answer_detail


def _rows():
    return [{"model_code": "A", "brand": "Toshiba", "price_clean": 12_000_000, "category": "Tủ Lạnh",
             "key_specs_summary": "", "full_specs_json": '{"Dung tích tổng": "300 lít"}'},
            {"model_code": "B", "brand": "LG", "price_clean": 11_000_000, "category": "Tủ Lạnh",
             "key_specs_summary": "", "full_specs_json": '{"Dung tích tổng": "250 lít"}'}]


def test_answer_grounded_passthrough():
    llm = FakeLLM(text_responses=["Dạ máy Toshiba dung tích 300 lít ạ."])
    msg, card = answer_detail(_rows()[0], "dung tích bao nhiêu", llm)
    assert "300" in msg
    assert card.title.startswith("Thông tin chi tiết")


def test_answer_fail_closed_on_hallucination():
    # LLM bịa số 999 không có trong fact-sheet -> phải bị thay bằng safe summary.
    llm = FakeLLM(text_responses=["Máy này chỉ 999 lít và giá 5000000đ."])
    msg, card = answer_detail(_rows()[0], "thông số", llm)
    assert "999" not in msg
