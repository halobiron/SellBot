"""Hồ sơ xưng hô theo phiên.

Việc suy cách xưng hô là bài toán ngữ cảnh, không phải bài toán keyword. LLM
đang trích intent mỗi lượt sẽ trả về hồ sơ này; module chỉ lưu, kiểm tra dữ liệu
đầu ra và cung cấp fallback trung tính khi mô hình không chắc chắn.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

# Unknown identity is represented by no term at all.  Callers must write a
# neutral sentence rather than falling back to a guessed relationship.
DEFAULT_ADDRESS = ""
DEFAULT_SELF = ""
_SAFE_TERM = re.compile(r"^[^\W\d_][^\n\r]{0,30}$", re.UNICODE)


@dataclass(frozen=True)
class AddressProfile:
    customer_addr: str = DEFAULT_ADDRESS
    self_term: str = DEFAULT_SELF
    confidence: str = "fallback"  # fallback | inferred | explicit
    source: str = "default"       # default | llm | customer


def _valid_term(value: Any) -> Optional[str]:
    """Chấp nhận cách gọi ngắn, bất kể từ vựng hay vùng miền."""
    value = str(value or "").strip().lower()
    return value if _SAFE_TERM.fullmatch(value) else None


def resolve_profile(previous: Optional[Mapping[str, Any]] = None) -> AddressProfile:
    """Lấy hồ sơ của phiên, hoặc fallback khi chưa có tín hiệu đáng tin cậy."""
    if not previous:
        return AddressProfile()
    addr = _valid_term(previous.get("customer_addr"))
    self_term = _valid_term(previous.get("bot_self_term"))
    if not addr or not self_term:
        return AddressProfile()
    return AddressProfile(addr, self_term,
                          str(previous.get("address_confidence") or "inferred"),
                          str(previous.get("address_source") or "llm"))


def apply_llm_addressing(profile: AddressProfile, intent: Mapping[str, Any]) -> AddressProfile:
    """Cập nhật khi mô hình có bằng chứng rõ; còn lại giữ nguyên hồ sơ phiên."""
    if str(intent.get("addressing_confidence") or "").lower() != "high":
        return profile
    # Một lựa chọn khách đã nói rõ chỉ có thể bị thay bởi một lựa chọn rõ ràng mới.
    if profile.confidence == "explicit" and not intent.get("addressing_explicit"):
        return profile
    addr = _valid_term(intent.get("customer_address"))
    self_term = _valid_term(intent.get("bot_self_term"))
    if not addr or not self_term:
        return profile
    if intent.get("addressing_explicit"):
        return AddressProfile(addr, self_term, "explicit", "customer")
    return AddressProfile(addr, self_term, "inferred", "llm")


def resolve_address(query: str, previous: Optional[str] = None) -> str:
    """Legacy helper; query is intentionally not parsed by rules anymore."""
    del query
    return resolve_profile({"customer_addr": previous, "bot_self_term": DEFAULT_SELF}).customer_addr


def resolve_self_term(addr: str) -> str:
    """Legacy fallback. Reciprocal terms are now inferred by the LLM."""
    del addr
    return DEFAULT_SELF
