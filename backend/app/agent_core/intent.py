import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.agent_core.retriever import get_catalog_metadata, get_schema_summary

log = logging.getLogger("agent_core")


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
    return out


# Pydantic schema mô tả ý định tìm kiếm sản phẩm.
class IntentSchema(BaseModel):
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
    budget_max: Optional[float] = Field(
        default=None,
        description="Ngân sách tối đa tính bằng VNĐ (15 triệu -> 15000000.0). None nếu chưa nhắc."
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
    '{"is_meta_inquiry": bool, "meta_reply": string|null, "is_policy_question": bool, '
    '"is_chitchat": bool, "smalltalk_reply": string|null, '
    '"category": string|null, "transition_message": string|null, "unsupported_product": string|null, '
    '"related_categories": string[], "budget_max": number|null, '
    '"brand": string|null, "priority_features": string[], "wants_comparison": bool, "assumptions": string[], '
    '"declines_more_info": bool, "needs_custom_query": bool, "needs_clarification": bool, '
    '"clarification_questions": string[]}'
)


def extract_intent(query: str, history: Optional[List[Dict[str, str]]] = None,
                   llm=None, db_path: Optional[str] = None, addr: str = "anh/chị",
                   self_term: str = "em") -> Dict[str, Any]:
    """Trích ý định qua DeepSeek; không suy đoán intent khi dịch vụ lỗi."""
    if llm is None:
        log.error("intent: không có LLM được cấu hình")
        raise IntentServiceUnavailableError("LLM is not configured")
    try:
        schema_info = get_schema_summary(db_path)
        system = (
            "Bạn là nhân viên tư vấn điện máy đang lắng nghe khách. "
            f"{schema_info}\n"
            "Ánh xạ danh mục theo ngữ nghĩa (VD: laptop/macbook/pc/desktop -> 'Máy tính để bàn'; "
            "ipad/tablet -> 'Máy tính bảng', ...). Nếu câu hỏi mới đổi loại sản phẩm so với lịch sử, "
            "BẮT BUỘC theo danh mục mới.\n"
            "- Nếu khách mô tả một BÀI TOÁN/VẤN ĐỀ thay vì gọi tên sản phẩm (VD: 'bé đi học không được dùng điện thoại nhưng cần liên lạc', 'mùa mưa phơi đồ không khô'), HÃY TỰ SUY LUẬN xem trong các danh mục có sẵn có loại nào giải quyết được không (VD: Đồng hồ thông minh có nghe gọi, Máy sấy quần áo). Nếu có, gán luôn `category` là danh mục đó và BẮT BUỘC viết `transition_message` để giải thích gợi mở khéo léo (VD: 'Dạ nếu cô giáo không cho mang điện thoại thì bé dùng đồng hồ thông minh có nghe gọi được không ạ?').\n"
            "- Nếu khách muốn mua loại sản phẩm KHÔNG thuộc danh mục nào trong CSDL (VD điện thoại, "
            "tivi, nồi cơm điện) và cũng KHÔNG thể dùng sản phẩm nào trong CSDL để thay thế: TUYỆT ĐỐI không gán bừa category gần đúng — để category=null, điền "
            "unsupported_product=<tên loại đó>, và chọn related_categories là 1-3 danh mục CÓ THẬT "
            "trong CSDL gần với nhu cầu đó nhất.\n"
            "- unsupported_product CHỈ dùng cho MẶT HÀNG hữu hình khách muốn mua nhưng catalog không có.\n"
            "- Yêu cầu tạo nội dung/thực hiện tác vụ ngoài mua sắm (viết code, dịch, giải bài tập): "
            "is_chitchat=true, unsupported_product=null; BẮT BUỘC điền smalltalk_reply từ chối ngắn "
            "và gợi ý 1-3 danh mục CÓ TRONG CSDL liên quan nếu có.\n"
            "- Câu hỏi kiến thức ngắn ngoài mua sắm (VD 'kinh tế chính trị là gì?'): "
            "is_chitchat=true và BẮT BUỘC điền smalltalk_reply trả lời đúng trọng tâm, tối đa 2 câu/60 từ; "
            "không gọi đó là sản phẩm, không giảng giải dài và BẮT BUỘC kết bằng một câu chuyển nhẹ "
            "sang nhu cầu mua thiết bị học tập/làm việc.\n"
            "- is_meta_inquiry=true khi khách hỏi khái niệm/thông số LIÊN QUAN SẢN PHẨM "
            "(OLED, Inverter, dung tích...) hoặc hỏi tổng quan catalog. BẮT BUỘC điền meta_reply ngắn gọn.\n"
            "- wants_comparison=true khi khách chủ động yêu cầu đưa ra nhiều sự lựa chọn hoặc so sánh (VD 'so sánh', 'có những option nào', 'các dòng máy'). False nếu khách chỉ nhờ tư vấn chung.\n"
            "- needs_clarification=true khi KHÁCH TRẢ LỜI QUÁ CHUNG CHUNG và bạn cần hỏi thêm để lọc sản phẩm (mục đích, bối cảnh người dùng, ngân sách). TUYỆT ĐỐI KHÔNG bật cờ này nếu khách đang hỏi ngược lại bạn (đó là is_meta_inquiry). False nếu khách vừa trả lời đủ hoặc từ chối bổ sung.\n"
            "- clarification_questions: 1-2 câu hỏi NGẮN, tự nhiên như người bán hàng thật, bám đúng bối cảnh "
            "khách vừa kể. TUYỆT ĐỐI không hỏi lại điều khách đã nói hoặc điều trợ lý đã hỏi trong lịch sử.\n"
            "- assumptions: các suy đoán bạn tự rút ra mà khách không nói rõ, ghi ngắn gọn.\n"
            "- declines_more_info=true nếu khách né/từ chối cung cấp thêm ('gợi ý đại', 'gì cũng được', "
            "'chọn giúp anh/chị',...).\n"
            "- needs_custom_query=true khi khách ràng buộc theo THÔNG SỐ hoặc cách xếp hạng đặc biệt "
            "(dung tích/kích thước/số cửa/'ít tốn điện nhất'/'nhẹ nhất'...) — lọc cơ bản ngành+giá+hãng "
            "không đáp ứng được.\n"
            "- Số người sử dụng là một ràng buộc thông số: khi khách nói 'nhà 4 người' hoặc tương tự, "
            "BẮT BUỘC ghi vào priority_features và đặt needs_custom_query=true, kể cả khi khách nói "
            "'khác gì cũng được'. Câu đó chỉ có nghĩa là không chốt thêm tiêu chí/ngân sách, không được "
            "bỏ qua số người đã nêu.\n"
            "- Nếu khách mới nêu ngành hàng và số người sử dụng nhưng CHƯA nêu ngân sách, và không nói "
            "'khác gì cũng được'/'chọn đại': đặt needs_clarification=true và hỏi ngân sách. Không tự chọn "
            "sản phẩm chỉ từ số người sử dụng.\n"
            "- is_policy_question=true khi khách hỏi về CHÍNH SÁCH/VẬN HÀNH cửa hàng: giờ mở/đóng cửa, "
            "tổng đài/cách liên hệ, địa chỉ, cách đặt hàng online, thời gian/phí giao hàng, phí lắp đặt "
            "và vật tư, dịch vụ vệ sinh/sửa chữa, hình thức thanh toán/trả góp, hoàn tiền, phí đổi trả "
            "(hư gì đổi nấy, 1 đổi 1), chính sách bảo hành/đổi trả, khiếu nại, nội quy, hoặc về DỮ LIỆU "
            "CÁ NHÂN/quyền riêng tư (shop thu thập gì, lưu bao lâu, chia sẻ cho ai, cách xóa "
            "dữ liệu/tài khoản, bảo mật thông tin). KHÔNG nhầm với "
            "is_meta_inquiry (giải thích thông số/khái niệm) và KHÔNG nhầm với chitchat. Nếu khách hỏi "
            "bảo hành/giá của MỘT sản phẩm cụ thể đang tư vấn thì KHÔNG bật cờ này.\n"
            "- Nếu câu vừa chào vừa nêu nhu cầu ('chào em, cần mua tủ lạnh') thì KHÔNG phải chitchat. "
            "Nếu khách hỏi về MỘT nhóm sản phẩm cụ thể, gán trực tiếp category tương ứng.\n"
            f"- Trong mọi câu chữ hướng tới khách (clarification_questions, transition_message, "
            f"smalltalk_reply, meta_reply): xưng '{self_term}' và gọi khách là '{addr}' (không dùng 'bạn')."
        )
        hist_str = ""
        for m in (history or []):
            role = "User" if m.get("role") == "user" else "Assistant"
            hist_str += f"{role}: {m.get('content')}\n"
        user = f"Lịch sử:\n{hist_str or 'Không có'}\n\nCâu hỏi mới: {query}"
        raw = llm.complete_json(system, user, _SCHEMA_HINT)
        log.info("intent: trích qua LLM thành công")
        intent = IntentSchema(**{
            k: raw[k] for k in IntentSchema.model_fields if k in raw
        }).model_dump()
        categories = get_catalog_metadata(db_path)["categories"]
        return normalize_intent_scope(intent, categories)
    except Exception as e:
        log.exception("intent: không thể trích intent")
        raise IntentServiceUnavailableError("Intent extraction failed") from e
