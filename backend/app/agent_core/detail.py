from __future__ import annotations
import logging
from typing import Any, Dict, List, Tuple
from app.schemas import AdviceResult, FactCard
from app.agent_core.presenters import product_display_name, build_detail_card
from app.agent_core.sales import closing_hook
from app.advice.provenance import facts_for_llm
from app.advice.verify import verify_advice, is_grounded

log = logging.getLogger("agent_core")

def _detail_system(addr: str, self_term: str) -> str:
    return (
        "Bạn là nhân viên tư vấn điện máy thân thiện, nói tiếng Việt bình dân. Khách đang hỏi kỹ về MỘT "
        "sản phẩm. Bạn CHỈ được dùng dữ kiện trong phần FACTS; TUYỆT ĐỐI không bịa thông số, giá, khuyến mãi. "
        "TRÌNH BÀY NGẮN GỌN (chỉ nêu 2-3 điểm nổi bật thực sự quan trọng với ngữ cảnh của khách). "
        "KHÔNG liệt kê toàn bộ thông số dài dòng như một cái sớ, trừ khi khách chủ động hỏi chi tiết từng cái. "
        f"Nếu thông tin khách hỏi không có trong FACTS, nói thẳng 'dạ {self_term} chưa có dữ liệu về ... ạ'. "
        f"Xưng '{self_term}' và gọi khách là '{addr}' (không dùng 'bạn'). "
        "Trả lời thẳng vào câu hỏi, mạch lạc, tự nhiên."
    )


def _safe_summary(row: Dict[str, Any], card: FactCard, addr: str) -> str:
    keep = [l for l in card.lines if l.label in ("Giá", "Thương hiệu")]
    head = "; ".join(f"{l.label} {l.value}" for l in keep) if keep else "thông tin cơ bản"
    return (f"Dạ về {product_display_name(row)}: {head}. "
            f"{addr.capitalize()} muốn biết thêm thông số cụ thể nào ạ?")


def answer_detail(row: Dict[str, Any], question: str, llm, addr: str = "anh/chị",
                  self_term: str = "em") -> Tuple[str, FactCard]:
    """Trả lời sâu 1 sản phẩm, grounded trong fact-sheet; fail-closed nếu LLM bịa số."""
    card = build_detail_card(row)
    facts = facts_for_llm([card])
    user = (f'Khách hỏi về "{product_display_name(row)}": "{question}"\n\n'
            f"FACTS:\n{facts}\n\nTrả lời khách theo đúng quy tắc.")
    try:
        message = llm.complete_text(_detail_system(addr, self_term), user)
    except Exception as e:
        log.warning("detail: LLM lỗi (%s) -> safe summary", e)
        message = ""
    result = verify_advice(AdviceResult(message=message or "", cards=[card], assumptions=[], warnings=[]))
    if not message or not is_grounded(result):
        if message:
            log.warning("detail: FAIL-CLOSED — số không truy được nguồn -> safe summary (warnings=%s)",
                        list(result.warnings))
        return _safe_summary(row, card, addr), card
    log.info("detail: câu trả lời LLM grounded")
    return message, card
