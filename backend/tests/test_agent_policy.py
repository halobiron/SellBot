from app.agent_core.policy import (load_policy_chunks, search_policy, answer_policy,
                                   _numbers_grounded)
from tests.agent_helpers import make_db


class EchoLLM:
    """LLM giả trả về đúng câu đã cài sẵn."""

    def __init__(self, reply):
        self.reply = reply

    def complete_text(self, system, user):
        return self.reply


class BoomLLM:
    def complete_text(self, system, user):
        raise RuntimeError("llm down")


class CaptureLLM:
    """Ghi lại prompt để kiểm tra ngữ cảnh được truyền vào."""

    def __init__(self, reply):
        self.reply = reply
        self.seen_system = None
        self.seen_user = None

    def complete_text(self, system, user):
        self.seen_system = system
        self.seen_user = user
        return self.reply


def _db(tmp_path):
    db = str(tmp_path / "p.db")
    make_db(db, [{"category": "Tủ Lạnh", "brand": "Toshiba", "price_clean": 12_000_000, "specs": {}}])
    return db


# --- Nạp & tìm kiếm chunk -------------------------------------------------

def test_load_policy_chunks_from_real_dir():
    chunks = load_policy_chunks()
    assert len(chunks) >= 10
    titles = [c["title"] for c in chunks]
    assert any("Giờ hoạt động" in t for t in titles)
    assert any("Hoàn tiền" in t for t in titles)


def test_search_policy_finds_opening_hours():
    hits = search_policy("cửa hàng mấy giờ mở cửa vậy?")
    assert hits and "Giờ hoạt động" in hits[0]["title"]
    assert "8h" in hits[0]["text"]


def test_search_policy_finds_refund():
    hits = search_policy("thanh toán online rồi muốn hoàn tiền thì bao lâu nhận được")
    assert any("Hoàn tiền" in h["title"] for h in hits)


def test_search_policy_finds_personal_data():
    hits = search_policy("shop thu thập dữ liệu cá nhân gì của tôi?")
    assert hits and any("Dữ liệu cá nhân được thu thập" in h["title"] for h in hits)


def test_search_policy_finds_data_deletion():
    hits = search_policy("tôi muốn yêu cầu xóa dữ liệu cá nhân thì làm sao")
    assert hits and any("Quyền của khách hàng" in h["title"]
                        or "Thời gian lưu trữ" in h["title"] for h in hits)


def test_search_policy_finds_return_fee():
    hits = search_policy("đổi trả sản phẩm thì mất phí bao nhiêu?")
    assert hits and any("Hoàn tiền khi đổi trả" in h["title"]
                        or "Hư gì đổi nấy" in h["title"] for h in hits)


def test_search_policy_finds_delivery_time():
    hits = search_policy("đặt hàng lắp đặt thì bao lâu nhận được hàng?")
    assert hits and any("Thời gian giao hàng lắp đặt" in h["title"] for h in hits)


def test_search_policy_finds_shipping_fee():
    hits = search_policy("phí giao hàng tính thế nào vậy shop")
    assert hits and any("Phí giao hàng" in h["title"] for h in hits)


def test_search_policy_finds_ac_cleaning():
    hits = search_policy("vệ sinh máy lạnh giá bao nhiêu")
    assert hits and any("vệ sinh" in h["title"].lower() for h in hits)


def test_search_policy_no_match_returns_empty():
    assert search_policy("xyzabc") == []


# --- Grounding số liệu ----------------------------------------------------

def test_numbers_grounded_accepts_doc_numbers():
    docs = "Tổng đài 1900.232.461, hoàn tiền 7 - 10 ngày."
    assert _numbers_grounded("Dạ anh gọi 1900.232.461, tiền hoàn trong 7 - 10 ngày ạ.", docs)


def test_numbers_grounded_rejects_foreign_numbers():
    docs = "Tổng đài 1900.232.461."
    assert not _numbers_grounded("Dạ anh gọi 1800.1234 nhé.", docs)


# --- answer_policy --------------------------------------------------------

def test_answer_policy_uses_llm_when_grounded():
    llm = EchoLLM("Dạ cửa hàng mở cửa từ 8h đến 22h hàng ngày ạ.")
    out = answer_policy("mấy giờ mở cửa", llm)
    assert "8h" in out and "22h" in out


def test_answer_policy_fallback_on_llm_error():
    out = answer_policy("mấy giờ mở cửa", BoomLLM())
    assert "8h" in out and "22h" in out  # nguyên văn chunk


def test_answer_policy_fallback_on_hallucinated_numbers():
    llm = EchoLLM("Dạ mở cửa từ 6h sáng, hotline 0909.999.999 ạ.")
    out = answer_policy("mấy giờ mở cửa", llm)
    assert "0909" not in out and "8h" in out


def test_answer_policy_no_hit_invites_hotline():
    out = answer_policy("qwerty zzz", None)
    assert "1900.232.461" in out


# --- Ngữ cảnh hội thoại (bug: hỏi phí lắp đặt giữa cuộc tư vấn tủ lạnh) ---

def test_search_policy_with_category_ranks_relevant_chunks():
    hits = search_policy("phí lắp đặt như nào", category="Tủ Lạnh")
    # Chunk nhắc tới tủ lạnh/nhóm hàng lắp đặt phải có mặt trong top thay vì chỉ bảng vật tư.
    assert hits and any("tủ lạnh" in h["text"].lower() for h in hits)


def test_answer_policy_passes_context_to_llm():
    llm = CaptureLLM("Dạ tủ lạnh thuộc nhóm hàng lắp đặt ạ.")
    history = [{"role": "user", "content": "tư vấn tủ lạnh 15 triệu"},
               {"role": "assistant", "content": "Dạ em gợi ý mẫu Toshiba ạ."}]
    answer_policy("phí lắp đặt như nào", llm, history=history, category="Tủ Lạnh")
    assert "Tủ Lạnh" in llm.seen_user            # bối cảnh nhóm hàng
    assert "tư vấn tủ lạnh 15 triệu" in llm.seen_user  # lịch sử hội thoại
    assert "không lấy ví dụ" in llm.seen_system or "nhóm sản phẩm" in llm.seen_system


def test_answer_policy_followup_reuses_previous_policy_topic():
    llm = CaptureLLM("Dạ tủ lạnh thuộc nhóm hàng lắp đặt ạ.")
    history = [{"role": "user", "content": "có chính sách giao hàng lắp đặt không"},
               {"role": "assistant", "content": "Dạ bên em có chính sách giao hàng ạ."}]
    answer_policy("tủ lạnh thì sao", llm, history=history, category="Tủ Lạnh")
    assert "[Thời gian giao hàng lắp đặt]" in llm.seen_user
    assert "[Phí vật tư lắp đặt máy lạnh tham khảo]" not in llm.seen_user


def test_policy_node_uses_category_from_conversation():
    from app.agent_core.agent_engine import policy_node
    llm = CaptureLLM("Dạ tủ lạnh thuộc nhóm hàng lắp đặt ạ.")
    state = {"query": "phí lắp đặt như nào",
             "intent": {"is_policy_question": True, "category": None},
             "last_products": [{"category": "Tủ Lạnh", "brand": "Toshiba"}],
             "history": [{"role": "user", "content": "tư vấn tủ lạnh"},
                         {"role": "assistant", "content": "Dạ em gợi ý mẫu Toshiba."},
                         {"role": "user", "content": "phí lắp đặt như nào"}]}
    out = policy_node(state, {"configurable": {"llm": llm}})
    assert "Tủ Lạnh" in llm.seen_user
    assert out["response"]


def test_router_policy_flag_beats_detail_followup():
    from app.agent_core.agent_engine import router_edge
    state = {"query": "phí lắp đặt thế nào",
             "intent": {"is_policy_question": True, "category": "Tủ Lạnh"},
             "last_products": [{"category": "Tủ Lạnh", "model_code": "X1"}],
             "focused_sku": "X1"}
    assert router_edge(state) == "policy"


def test_router_uses_llm_detail_intent_for_implicit_followup():
    from app.agent_core.agent_engine import router_edge
    base = {
        "query": "bảo hành thế nào",
        "last_products": [{"category": "Tủ Lạnh", "model_code": "X1"}],
        "focused_sku": "X1",
    }
    assert router_edge({**base, "intent": {"is_product_detail_question": True}}) == "detail"
    assert router_edge({**base, "intent": {"is_product_detail_question": False}}) == "clarify"


def test_router_unsupported_product_beats_policy_flag():
    from app.agent_core.agent_engine import router_edge
    state = {"query": "tivi thì sao",
             "intent": {"is_policy_question": True, "unsupported_product": "tivi"},
             "last_products": []}
    assert router_edge(state) == "unsupported"


def test_policy_node_defends_against_unsupported_product(tmp_path):
    from app.agent_core.agent_engine import policy_node
    db = _db(tmp_path)
    state = {"query": "tivi thì sao",
             "intent": {"is_policy_question": True, "unsupported_product": "tivi",
                        "related_categories": []},
             "history": [{"role": "user", "content": "tivi thì sao"}]}
    out = policy_node(state, {"configurable": {"db_path": db}})
    assert "chưa kinh doanh tivi" in out["response"]
    assert "xe đạp" not in out["response"].lower()

