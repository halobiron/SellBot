import logging
import json
from typing import List, Dict, Any, Optional
import httpx
from pydantic import BaseModel, Field
from app.agent_core.retriever import get_catalog_metadata, get_schema_summary

log = logging.getLogger("agent_core")

# Intent opens every recommendation turn. Keep its Responses API request bounded.
_INTENT_LLM_TIMEOUT_SECONDS = 20.0
_INTENT_LLM_MAX_TOKENS = 2048


def normalize_intent_scope(intent: Dict[str, Any], categories: List[str]) -> Dict[str, Any]:
    """Ép category/unsupported về đúng catalog trước khi router ra quyết định."""
    out = dict(intent)
    by_lower = {cat.lower(): cat for cat in categories}
    category = str(out.get("category") or "").strip()
    unsupported = str(out.get("unsupported_product") or "").strip()
    if unsupported:
        # Schema quy định hai trường loại trừ nhau; hàng unsupported phải thắng
        # một category gần đúng mà LLM có thể đồng thời điền nhầm.
        out["category"] = None
        out["unsupported_product"] = unsupported
    elif category:
        canonical = by_lower.get(category.lower())
        if canonical:
            out["category"] = canonical
            out["unsupported_product"] = None
        else:
            # Category do LLM sinh nhưng không tồn tại trong DB cũng là unsupported.
            out["category"] = None
            out["unsupported_product"] = category
    else:
        out["category"] = None
        out["unsupported_product"] = None

    valid = set(categories)
    out["related_categories"] = [
        cat for cat in (out.get("related_categories") or []) if cat in valid
    ][:3]
    if out.get("unsupported_product"):
        out["needs_clarification"] = False
        out["is_meta_inquiry"] = False
        out["is_chitchat"] = False
        # This is authored by the model from the verified catalog context below,
        # rather than assembled from a fixed response template in the graph.
        reply = out.get("unsupported_reply")
        out["unsupported_reply"] = reply.strip() if isinstance(reply, str) and reply.strip() else None
    else:
        out["unsupported_reply"] = None
    return out


# Pydantic schema mô tả ý định tìm kiếm sản phẩm.
class IntentSchema(BaseModel):
    customer_address: Optional[str] = Field(
        default=None,
        description="Cách gọi khách (ông/bà/bác/cô/chú/anh/chị/em/cháu/con) chỉ khi câu mới hoặc lịch sử có bằng chứng rõ ràng. None nếu không chắc; tuyệt đối không đoán tuổi/giới tính."
    )
    bot_self_term: Optional[str] = Field(
        default=None,
        description="Cách bot tự xưng tương ứng, chỉ điền cùng customer_address khi bằng chứng xưng hô rõ ràng. None nếu không chắc."
    )
    addressing_confidence: str = Field(
        default="unknown",
        description="high chỉ khi khách nói rõ cách muốn được gọi/xưng hoặc tự xưng rõ; unknown trong mọi trường hợp còn lại."
    )
    addressing_explicit: bool = Field(
        default=False,
        description="True chỉ khi khách nói trực tiếp cách bot và khách cần xưng hô; False khi chỉ suy ra từ ngữ cảnh."
    )
    is_product_detail_question: bool = Field(
        default=False,
        description="True khi khách đang hỏi thêm thông tin về MỘT sản phẩm đã xuất hiện trong lịch sử, kể cả gọi là 'máy này', 'máy đầu tiên' hoặc nêu hãng/mẫu. False khi muốn xem thêm danh sách, so sánh, hay bắt đầu nhu cầu mua mới."
    )
    selected_product_id: Optional[str] = Field(
        default=None,
        description="Mã model của một candidate mà khách đang nói tới. Chỉ được chọn đúng model_code trong danh sách candidate; không tự tạo mã."
    )
    is_meta_inquiry: bool = Field(
        default=False,
        description="True khi khách hỏi khái niệm/thông số liên quan sản phẩm (OLED, Inverter, dung tích...) hoặc hỏi tổng quan catalog. Không dùng cho kiến thức phổ thông ngoài mua sắm."
    )
    meta_reply: Optional[str] = Field(
        default=None,
        description="Nếu is_meta_inquiry=true: 1-2 câu giải thích ngắn gọn, dân dã về khái niệm/thông số đó (kèm lợi ích thực tế nếu có), sau đó BẮT BUỘC đặt lại câu hỏi khéo léo để tiếp tục lấy thông tin (VD 'Dạ Inverter giúp tiết kiệm điện ạ. Nhà mình định mua máy tầm giá bao nhiêu?')."
    )
    is_policy_question: bool = Field(
        default=False,
        description="True nếu khách hỏi về CHÍNH SÁCH/VẬN HÀNH của cửa hàng: giờ mở cửa, tổng đài/cách liên hệ, địa chỉ, cách đặt hàng online, giao hàng, hình thức thanh toán/trả góp, hoàn tiền, chính sách bảo hành/đổi trả nói chung, khiếu nại, nội quy, hoặc về DỮ LIỆU CÁ NHÂN/quyền riêng tư (thu thập gì, lưu bao lâu, chia sẻ cho ai, cách xóa dữ liệu). KHÔNG bật nếu khách hỏi về thông số kỹ thuật (đó là is_meta_inquiry) hoặc hỏi bảo hành của MỘT sản phẩm cụ thể đang được tư vấn."
    )
    is_chitchat: bool = Field(
        default=False,
        description="True cho xã giao, câu hỏi kiến thức phổ thông hoặc yêu cầu ngoài mua sắm khi khách không có nhu cầu sản phẩm. Không coi các yêu cầu này là unsupported_product."
    )
    smalltalk_reply: Optional[str] = Field(
        default=None,
        description="Với xã giao, câu hỏi kiến thức ngắn hoặc yêu cầu ngoài mua sắm: trả lời tối đa 2 câu/60 từ và kết thúc bằng một câu chuyển nhẹ về nhu cầu mua sắm. Với yêu cầu tạo nội dung như viết code, từ chối ngắn và gợi ý 1-3 danh mục CÓ TRONG CSDL liên quan nhu cầu (nếu có)."
    )
    category: Optional[str] = Field(
        default=None,
        description="Tên danh mục sản phẩm trong CSDL phù hợp nhất, hoặc None nếu không xác định."
    )
    transition_message: Optional[str] = Field(
        default=None,
        description="Lời chuyển tiếp tự nhiên, giải thích khéo léo lý do chọn danh mục này khi khách chỉ nêu vấn đề chứ không gọi tên sản phẩm (VD: 'Dạ nếu cô giáo không cho mang điện thoại thì bé nhà mình mang đồng hồ thông minh có nghe gọi được không ạ?')."
    )
    unsupported_product: Optional[str] = Field(
        default=None,
        description="Loại sản phẩm khách muốn mua nhưng KHÔNG thuộc danh mục nào trong CSDL (VD 'điện thoại'). None nếu khách hỏi đúng mặt hàng có bán."
    )
    related_categories: List[str] = Field(
        default_factory=list,
        description="Khi unsupported_product khác None: 1-3 danh mục CÓ TRONG CSDL gần nhất với nhu cầu đó (VD điện thoại -> Máy tính bảng, Đồng hồ thông minh)."
    )
    unsupported_reply: Optional[str] = Field(
        default=None,
        description="Khi unsupported_product khác None: câu trả lời tự nhiên 1-2 câu cho khách. Nói rõ cửa hàng hiện không có mặt hàng đó và chỉ gợi ý related_categories có trong CSDL nếu thực sự liên quan. Không dùng lời văn mẫu, không tự gán tuổi/giới tính hay cách xưng hô; nếu chưa chắc thì tránh gọi trực tiếp khách."
    )
    budget_max: Optional[float] = Field(
        default=None,
        description="Ngân sách tối đa là số tiền VNĐ tuyệt đối, không phải đơn vị triệu: "
                    "5 củ/5tr/5 triệu -> 5000000; 5,5 triệu -> 5500000. None nếu chưa nhắc."
    )
    brand: Optional[str] = Field(
        default=None,
        description="Thương hiệu người dùng quan tâm. None nếu không nhắc đến."
    )
    priority_features: List[str] = Field(
        default_factory=list,
        description="Các tính năng hoặc thông số đặc thù người dùng ưu tiên (màn hình lớn, pin trâu, mỏng nhẹ...)."
    )
    wants_comparison: bool = Field(
        default=False,
        description="True nếu khách có ý định xem nhiều lựa chọn, so sánh, phân tích các mẫu khác nhau (VD: 'so sánh', 'có mấy loại', 'xem các option', 'mẫu nào tốt nhất'). False nếu khách chỉ hỏi một nhu cầu chung chung."
    )
    assumptions: List[str] = Field(
        default_factory=list,
        description="Các suy đoán bạn tự rút ra mà khách KHÔNG nói rõ (VD 'mua cho con' -> 'bé dùng để học tập'). Để [] nếu không suy đoán gì."
    )
    declines_more_info: bool = Field(
        default=False,
        description="True nếu khách né tránh/từ chối cung cấp thêm thông tin ('gợi ý đại đi', 'gì cũng được', 'em cứ chọn giúp anh')."
    )
    needs_custom_query: bool = Field(
        default=False,
        description="True nếu nhu cầu có ràng buộc THÔNG SỐ hoặc cách xếp hạng mà lọc cơ bản (ngành/giá trần/hãng) không làm được: VD 'trên 300 lít', 'màn 27 inch', 'tủ 2 cửa', 'ít tốn điện nhất', 'nhẹ nhất'."
    )
    needs_clarification: bool = Field(
        default=False,
        description="True nếu câu hỏi quá chung chung, chưa đủ dữ kiện để tư vấn chính xác."
    )
    clarification_questions: List[str] = Field(
        default_factory=list,
        description="1-2 câu hỏi làm rõ lịch sự nếu needs_clarification là True."
    )


class IntentServiceUnavailableError(RuntimeError):
    """The intent service could not process the request safely."""


_SCHEMA_HINT = (
    '{"customer_address": string|null, "bot_self_term": string|null, "addressing_confidence": "high"|"unknown", "addressing_explicit": bool, "is_product_detail_question": bool, "selected_product_id": string|null, "is_meta_inquiry": bool, "meta_reply": string|null, "is_policy_question": bool, '
    '"is_chitchat": bool, "smalltalk_reply": string|null, '
    '"category": string|null, "transition_message": string|null, "unsupported_product": string|null, '
    '"related_categories": string[], "unsupported_reply": string|null, "budget_max": number|null, '
    '"brand": string|null, "priority_features": string[], "wants_comparison": bool, "assumptions": string[], '
    '"declines_more_info": bool, "needs_custom_query": bool, "needs_clarification": bool, '
    '"clarification_questions": string[]}'
)


def extract_intent(query: str, history: Optional[List[Dict[str, str]]] = None,
                   llm=None, db_path: Optional[str] = None,
                   candidate_products: Optional[List[Dict[str, Any]]] = None, addr: str = "",
                   self_term: str = "") -> Dict[str, Any]:
    """Trích ý định qua DeepSeek; không suy đoán intent khi dịch vụ lỗi."""
    if llm is None:
        log.error("intent: không có LLM được cấu hình")
        raise IntentServiceUnavailableError("LLM is not configured")
    try:
        schema_info = get_schema_summary(db_path)
        system = (
            "Bạn là nhân viên tư vấn điện máy. Trích intent theo JSON schema, không thêm văn bản.\n"
            f"{schema_info}\n"
            "- category phải là đúng danh mục CSDL, suy luận theo ngữ nghĩa; nhu cầu mới thắng lịch sử. "
            "Nếu mô tả vấn đề, tự chọn danh mục CSDL giải quyết được và viết transition_message. Nếu không "
            "có sản phẩm thay thế, category=null, điền unsupported_product và 1-3 related_categories có thật. "
            "Khi unsupported_product có giá trị, BẮT BUỘC điền unsupported_reply: viết một câu trả lời tự nhiên "
            "theo đúng ngữ cảnh, nói thật là cửa hàng chưa có mặt hàng này và chỉ nhắc related_categories nếu hợp lý. "
            "Không được dùng một khuôn câu cố định hay lặp nguyên cụm 'Gần với nhu cầu đó'.\n"
            "- budget_max là VNĐ tuyệt đối: '5 củ', '5tr', '5 triệu' đều là 5000000; '5,5 triệu' là 5500000.\n"
            "- Detail chỉ là câu hỏi tiếp về một candidate lịch sử. Câu hỏi khái niệm/thông số/catalog là meta "
            "và có meta_reply ngắn; chính sách cửa hàng/dữ liệu cá nhân là policy; xã giao, kiến thức ngoài "
            "mua sắm hay yêu cầu tạo nội dung là chitchat. Với chitchat BẮT BUỘC điền smalltalk_reply, tối đa "
            "2 câu/60 từ và chuyển nhẹ về nhu cầu mua sắm.\n"
            "- Trích brand, ngân sách, ưu tiên; needs_custom_query=true cho ràng buộc thông số/xếp hạng, "
            "kể cả số người dùng. wants_comparison=true khi khách muốn nhiều lựa chọn. Chỉ needs_clarification "
            "khi thiếu dữ kiện thật sự, hỏi 1-2 câu ngắn không lặp lại lịch sử; declines_more_info=true khi khách từ chối.\n"
            "- Đồng thời trích customer_address, bot_self_term và addressing_confidence. Chỉ trả high khi khách tự "
            "xưng rõ ở ngôi thứ nhất (vd 'cô cần...', 'anh muốn...', 'ông cần...') hoặc nói thẳng cách muốn được gọi/xưng. "
            "Không suy tuổi, giới tính hay vai vế từ tên, sản phẩm, giọng văn, 'tôi/mình', hay khi khách gọi BOT "
            "(vd 'dạ cô ơi'). addressing_explicit=true chỉ khi khách yêu cầu trực tiếp cách xưng hô. Nếu không "
            "chắc, để hai trường null và confidence=unknown.\n"
            "- Giữ cách xưng hô mà khách đã nói rõ. Khi chưa có bằng chứng, không tự gán tuổi, giới tính hay "
            "vai vế; ưu tiên câu không cần gọi trực tiếp khách thay vì ép dùng một đại từ mặc định."
        )
        candidate_lines = []
        for row in candidate_products or []:
            product_id = str(row.get("model_code") or row.get("sku") or "")
            if product_id:
                candidate_lines.append(
                    f"- model_code={product_id}; tên={row.get('brand') or ''} {row.get('display_name') or ''}; "
                    f"giá={row.get('price_clean') or ''}"
                )
        candidate_context = ("\nCandidate đang được phép chọn (selected_product_id phải là đúng một model_code bên dưới):\n"
                             + "\n".join(candidate_lines)) if candidate_lines else ""
        hist_str = ""
        for m in (history or []):
            role = "User" if m.get("role") == "user" else "Assistant"
            hist_str += f"{role}: {m.get('content')}\n"
        user = f"Lịch sử:\n{hist_str or 'Không có'}{candidate_context}\n\nCâu hỏi mới: {query}"
        try:
            raw = llm.complete_json(
            system, user, _SCHEMA_HINT,
            timeout=_INTENT_LLM_TIMEOUT_SECONDS,
            max_tokens=_INTENT_LLM_MAX_TOKENS,
            )
        except (httpx.TimeoutException, json.JSONDecodeError) as first_error:
            # Transport and decoding failures are intermittent in practice.
            # Retry exactly once with the same bounded request; never fall back
            # to a heuristic intent classifier.
            log.warning("intent: LLM lần đầu lỗi (%s), thử lại một lần", first_error)
            raw = llm.complete_json(
                system, user, _SCHEMA_HINT,
                timeout=_INTENT_LLM_TIMEOUT_SECONDS,
                max_tokens=_INTENT_LLM_MAX_TOKENS,
            )
        log.info("intent: trích qua LLM thành công")
        intent = IntentSchema(**{
            k: raw[k] for k in IntentSchema.model_fields if k in raw
        }).model_dump()
        categories = get_catalog_metadata(db_path)["categories"]
        intent = normalize_intent_scope(intent, categories)
        valid_ids = {str(r.get("model_code") or r.get("sku") or "") for r in candidate_products or []}
        if intent.get("selected_product_id") not in valid_ids:
            intent["selected_product_id"] = None
        return intent
    except Exception as e:
        log.exception("intent: không thể trích intent")
        raise IntentServiceUnavailableError("Intent extraction failed") from e
