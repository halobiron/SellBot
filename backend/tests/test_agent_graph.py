from app.llm.client import FakeLLM
from app.agent_core.engine import AgentCoreEngine
from tests.agent_helpers import make_db


class BoomLLM:
    def complete_json(self, system, user, schema_hint=""):
        raise RuntimeError("llm down")


def _db(tmp_path):
    db = str(tmp_path / "g.db")
    make_db(db, [
        {"category": "Tủ Lạnh", "brand": "Toshiba", "model_code": "TL1", "price_clean": 12_400_000,
         "specs": {"Dung tích tổng": "300 lít", "Điện năng tiêu thụ": "350 kWh/năm"}},
        {"category": "Tủ Lạnh", "brand": "LG", "model_code": "TL2", "price_clean": 11_000_000,
         "specs": {"Dung tích tổng": "250 lít", "Điện năng tiêu thụ": "300 kWh/năm"}},
        {"category": "Màn hình máy tính", "brand": "Xiaomi", "model_code": "171303", "price_clean": 6_690_000,
         "specs": {"Kích thước màn hình": "34 inch", "Độ phân giải": "2K+ (3440 x 1440)",
                   "Tiện ích": "AMD FreeSync Premium | Điều chỉnh được độ nghiêng"}},
    ])
    return db


def _digital_db(tmp_path):
    db = str(tmp_path / "digital.db")
    make_db(db, [
        {"category": "Máy tính để bàn", "brand": "Dell", "price_clean": 15_000_000, "specs": {}},
        {"category": "Màn hình máy tính", "brand": "LG", "price_clean": 5_000_000, "specs": {}},
        {"category": "Máy tính bảng", "brand": "Samsung", "price_clean": 8_000_000, "specs": {}},
    ])
    return db


def _reco_llm():
    return FakeLLM(
        json_responses=[{"category": "Tủ Lạnh", "budget_max": 20000000, "priority_features": ["tiết kiệm điện"],
                         "needs_clarification": False, "is_meta_inquiry": False,
                         "clarification_questions": [], "brand": None},
                        {}, {}, {}, {},  # SQL tool thử tối đa 4 lần trước khi fallback
                        {"rules": [{"field": "Điện năng tiêu thụ", "direction": "lower_better",
                                    "kind": "number"}]}],
        text_responses=["Máy Toshiba giá 12.400.000đ và LG giá 11.000.000đ, cả hai tiết kiệm điện tốt."])


def test_recommend_turn_shape(tmp_path):
    eng = AgentCoreEngine(llm=_reco_llm(), db_path=_db(tmp_path))
    out = eng.handle("s1", "mua tủ lạnh dưới 20tr tiết kiệm điện")
    assert out["stage"] == "recommended"
    assert out["recommendation"] is not None
    assert len(out["recommendation"]["cards"]) >= 2
    assert out["recommendation"]["comparison"] is not None
    assert "12.400.000" in out["reply"]
    energy = next(row for row in out["recommendation"]["comparison"]["rows"]
                  if row["label"] == "Điện năng tiêu thụ")
    assert energy["cells"][0]["is_best"] is True


def test_clarify_turn(tmp_path):
    llm = FakeLLM(json_responses=[{"category": None, "budget_max": None, "brand": None,
                                   "priority_features": [], "needs_clarification": True,
                                   "is_meta_inquiry": False,
                                   "clarification_questions": ["Bạn cần nhóm sản phẩm nào ạ?"]}])
    eng = AgentCoreEngine(llm=llm, db_path=_db(tmp_path))
    out = eng.handle("s2", "tư vấn giúp em")
    assert out["stage"] == "collecting"
    assert out["recommendation"] is None
    assert "?" in out["reply"]


def test_intent_service_error_returns_a_generic_unavailable_reply(tmp_path):
    out = AgentCoreEngine(llm=BoomLLM(), db_path=_db(tmp_path)).handle(
        "intent-unavailable", "mua tủ lạnh dưới 20 triệu")
    assert out["stage"] == "unavailable"
    assert out["recommendation"] is None
    assert "dịch vụ tư vấn đang bận" in out["reply"]


def test_general_household_request_asks_for_budget_before_recommending(tmp_path):
    llm = FakeLLM(json_responses=[{
        "category": "Tủ Lạnh", "budget_max": None, "brand": None,
        "priority_features": ["gia đình 4 người"], "needs_clarification": True,
        "is_meta_inquiry": False, "clarification_questions": [],
    }])
    out = AgentCoreEngine(llm=llm, db_path=_db(tmp_path)).handle(
        "household-size", "tôi muốn mua tủ lạnh cho nhà 4 người")
    assert out["stage"] == "collecting"
    assert out["recommendation"] is None
def test_detail_followup_uses_memory(tmp_path):
    db = _db(tmp_path)
    eng = AgentCoreEngine(llm=_reco_llm(), db_path=db)
    eng.handle("s3", "mua tủ lạnh dưới 20tr tiết kiệm điện")   # tạo last_products
    eng.llm = FakeLLM(json_responses=[{"category": "Tủ Lạnh", "needs_clarification": False,
                                       "is_meta_inquiry": False, "priority_features": [],
                                       "clarification_questions": [], "brand": None, "budget_max": None,
                                       "is_product_detail_question": True, "selected_product_id": "TL1"}],
                      text_responses=["Dạ máy Toshiba dung tích 300 lít ạ."])
    out = eng.handle("s3", "máy 1 dung tích bao nhiêu")
    assert "300" in out["reply"]
    assert out["recommendation"]["cards"][0]["title"].startswith("Thông tin chi tiết")


def test_exact_model_code_bypasses_llm_intent_inference(tmp_path):
    out = AgentCoreEngine(llm=BoomLLM(), db_path=_db(tmp_path)).handle(
        "exact-model", "cho tôi xem chi tiết thông số và tính năng của Xiaomi 171303")
    assert out["stage"] == "recommended"
    assert "171303" in out["reply"]
    assert out["recommendation"]["cards"][0]["title"].startswith("Thông tin chi tiết")


def test_reset_clears_memory(tmp_path):
    eng = AgentCoreEngine(llm=_reco_llm(), db_path=_db(tmp_path))
    eng.handle("s4", "mua tủ lạnh dưới 20tr tiết kiệm điện")
    eng.reset("s4")
    eng.llm = FakeLLM(json_responses=[{"category": None, "needs_clarification": True,
                                       "is_meta_inquiry": False, "priority_features": [],
                                       "clarification_questions": ["Bạn cần gì ạ?"],
                                       "brand": None, "budget_max": None}])
    out = eng.handle("s4", "máy 1 thế nào")
    assert out["stage"] == "collecting"


def test_code_request_is_briefly_redirected_without_extra_llm_call(tmp_path):
    db = _digital_db(tmp_path)
    llm = FakeLLM(
        json_responses=[{"category": None, "unsupported_product": None,
                         "is_chitchat": True, "needs_clarification": False,
                         "smalltalk_reply": "Dạ, em không hỗ trợ viết code chi tiết ạ. Nếu anh/chị cần thiết bị để lập trình, em có thể tư vấn Máy tính để bàn hoặc Màn hình máy tính."}])
    eng = AgentCoreEngine(llm=llm, db_path=db)
    out = eng.handle("code-off-topic", "hãy code cho tôi file C++ ra dòng Hello World")
    assert "chưa kinh doanh code" not in out["reply"].lower()
    assert "không hỗ trợ viết code chi tiết" in out["reply"]
    assert "Hello World" not in out["reply"]
    assert "#include" not in out["reply"]
    assert "Máy tính để bàn" in out["reply"]
    assert len(llm.calls) == 1  # chỉ intent JSON, không gọi LLM lần hai để sinh code


def test_general_knowledge_uses_short_reply_from_same_intent_call(tmp_path):
    db = _digital_db(tmp_path)
    cases = [
        ("kinh tế chính trị là gì", "Kinh tế chính trị nghiên cứu quan hệ giữa kinh tế và quyền lực.",
         "nghiên cứu quan hệ"),
        ("HTML là gì", "HTML là ngôn ngữ đánh dấu dùng để tạo cấu trúc trang web.",
         "ngôn ngữ đánh dấu"),
        ("Việt Nam nằm ở châu lục nào", "Việt Nam nằm ở châu Á, thuộc khu vực Đông Nam Á.",
         "châu Á"),
    ]
    for index, (query, reply, expected) in enumerate(cases):
        llm = FakeLLM(json_responses=[{
            "category": None, "unsupported_product": None, "is_chitchat": True,
            "smalltalk_reply": reply, "needs_clarification": False,
        }])
        out = AgentCoreEngine(llm=llm, db_path=db).handle(
            f"general-knowledge-{index}", query)
        assert expected in out["reply"]
        assert "chưa trả lời tốt" not in out["reply"]
        assert out["reply"] == reply
        assert len(llm.calls) == 1


def test_general_knowledge_does_not_duplicate_existing_pivot(tmp_path):
    reply = ("HTML là ngôn ngữ đánh dấu dùng để tạo cấu trúc trang web. "
             "Nếu cần tư vấn thiết bị học tập, em sẵn sàng hỗ trợ ạ.")
    llm = FakeLLM(json_responses=[{
        "category": None, "is_chitchat": True, "smalltalk_reply": reply,
        "needs_clarification": False,
    }])
    out = AgentCoreEngine(llm=llm, db_path=_db(tmp_path)).handle("pivot-once", "HTML là gì")
    assert out["reply"] == reply
    assert len(llm.calls) == 1
