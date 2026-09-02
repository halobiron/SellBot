from __future__ import annotations
from dataclasses import dataclass
import json
import logging
from typing import Any, Dict, List
from app.schemas import ComparisonTable, ComparisonRow, ComparisonCell
from app.agent_core.presenters import product_display_name, load_specs, parse_leading_number
from app.advice.provenance import format_vnd

log = logging.getLogger("agent_core")

_MISSING = "chưa có dữ liệu"
_GOOD_LABEL_2 = "Vượt trội"
_BAD_LABEL_2 = "Kém hơn"
_GOOD_LABEL_3 = "Vượt trội"
_WARN_LABEL_3 = "Ở mức khá"
_BAD_LABEL_3 = "Thấp nhất nhóm"


@dataclass(frozen=True)
class ComparisonRule:
    """Rule ngắn hạn do LLM suy ra từ tên và giá trị thực của field."""
    field: str
    direction: str
    kind: str = "number"
    scores: tuple[float | None, ...] | None = None


def _values_for_rule(rule: ComparisonRule, specs_per: List[Dict[str, str]]) -> List[float | None]:
    if rule.kind == "ranked" and rule.scores is not None:
        return list(rule.scores)
    return [parse_leading_number(specs.get(rule.field)) for specs in specs_per]


def _best_indices(nums: List[float | None], direction: str) -> set[int]:
    present = [(i, n) for i, n in enumerate(nums) if n is not None]
    if not present:
        return set()
    target = (min if direction == "min" else max)(n for _, n in present)
    return {i for i, n in present if n == target}


def _worst_indices(nums: List[float | None], direction: str) -> set[int]:
    other = "max" if direction == "min" else "min"
    return _best_indices(nums, other)


def _price_val(row: Dict[str, Any]) -> float | None:
    try:
        v = float(row.get("price_clean") or 0)
    except (ValueError, TypeError):
        return None
    return v if v > 0 else None


def _rank_statuses(nums: List[float | None], direction: str) -> List[str | None]:
    """Trả về status good/warn/bad/None theo thứ hạng thật của từng sản phẩm trong nums."""
    n = len(nums)
    best = _best_indices(nums, direction)
    worst = _worst_indices(nums, direction)
    out: List[str | None] = []
    for i, v in enumerate(nums):
        if v is None:
            out.append(None)
        elif i in best and i in worst:
            out.append(None)  # tất cả bằng nhau -> không có tín hiệu phân biệt
        elif i in best:
            out.append("good")
        elif i in worst:
            out.append("bad")
        else:
            out.append("warn")
    return out


def _need_cells_for_field(rule: ComparisonRule,
                          specs_per: List[Dict[str, str]]) -> List[ComparisonCell]:
    nums = _values_for_rule(rule, specs_per)
    field, direction = rule.field, rule.direction
    statuses = _rank_statuses(nums, direction)
    n_present = sum(1 for v in nums if v is not None)
    cells: List[ComparisonCell] = []
    for sp, status in zip(specs_per, statuses):
        raw = sp.get(field)
        if raw is None:
            cells.append(ComparisonCell(value=_MISSING, available=False, detail=_MISSING))
            continue
        if status == "good":
            verdict = _GOOD_LABEL_2 if n_present <= 2 else _GOOD_LABEL_3
        elif status == "bad":
            verdict = _BAD_LABEL_2 if n_present <= 2 else _BAD_LABEL_3
        elif status == "warn":
            verdict = _WARN_LABEL_3
        else:
            verdict = None
        cells.append(ComparisonCell(value=raw, available=True, is_best=(status == "good"),
                                     status=status, verdict=verdict, detail=raw))
    return cells


def _comparison_rules(fields: List[str], specs_per: List[Dict[str, str]], llm: Any) -> Dict[str, ComparisonRule]:
    """Nhờ AI nhận diện hướng so sánh từ dữ liệu thực, không dùng danh sách field cứng.

    Chỉ chấp nhận hướng khi model khẳng định được một chiều khách quan. Nếu tiêu
    chí phụ thuộc gu/mục đích sử dụng hoặc model lỗi, field được hiển thị trung tính.
    """
    if llm is None or not fields:
        return {}
    samples = [{"field": field, "values": [sp.get(field) for sp in specs_per]}
               for field in fields]
    system = (
        "Bạn là bộ phân tích ngữ nghĩa thông số sản phẩm. Với từng field và các giá trị "
        "catalog được cung cấp, quyết định liệu có một hướng so sánh KHÁCH QUAN cho đa số "
        "người mua hay không. Chỉ dùng dữ liệu đã cho; không suy diễn tính năng không có. "
        "direction=min khi số nhỏ hơn tốt hơn, max khi số lớn hơn tốt hơn, none khi phụ thuộc "
        "nhu cầu/không thể xếp hạng. kind=number nếu giá trị có số và dùng chính số đó. "
        "kind=ranked khi cần hiểu giá trị dạng chữ (ví dụ chuẩn/độ phân giải); khi đó scores "
        "phải là một số cho từng giá trị theo cùng thứ tự đầu vào, số lớn biểu thị mức cao hơn."
    )
    schema = ('{"rules":[{"field":"tên field đúng nguyên văn","direction":"min|max|none",'
              '"kind":"number|ranked","scores":[number|null]}]}')
    try:
        result = llm.complete_json(system, json.dumps(samples, ensure_ascii=False), schema)
    except Exception as exc:
        log.warning("compare: không suy ra được thang so sánh (%s)", exc)
        return {}
    rules: Dict[str, ComparisonRule] = {}
    allowed = set(fields)
    for item in result.get("rules", []) if isinstance(result, dict) else []:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        raw_direction = str(item.get("direction") or "").strip().lower()
        direction = {
            "min": "min", "lower": "min", "lower_better": "min", "thấp": "min",
            "max": "max", "higher": "max", "higher_better": "max", "cao": "max",
        }.get(raw_direction)
        if field not in allowed or direction is None:
            continue
        kind = item.get("kind")
        scores = item.get("scores")
        if kind == "ranked":
            if not isinstance(scores, list) or len(scores) != len(specs_per):
                continue
            try:
                normalized_scores = tuple(float(score) if score is not None else None for score in scores)
            except (TypeError, ValueError):
                continue
            rules[field] = ComparisonRule(field, direction, "ranked", normalized_scores)
        else:
            rules[field] = ComparisonRule(field, direction)
    log.info("compare: AI đã suy ra %d/%d thang so sánh", len(rules), len(fields))
    return rules


def _budget_row(rows: List[Dict[str, Any]], prices: List[float | None], budget_max: float) -> ComparisonRow:
    cells: List[ComparisonCell] = []
    for p in prices:
        if p is None:
            cells.append(ComparisonCell(value=_MISSING, available=False, detail=_MISSING))
            continue
        diff = budget_max - p
        if diff >= 0:
            status, verdict = "good", "Dư sức mua"
            detail = f"Tiết kiệm được {format_vnd(int(diff))}." if diff > 0 else "Vừa đúng ngân sách."
        elif p <= budget_max * 1.15:
            status, verdict = "warn", "Hơi lố ngân sách"
            detail = f"Cố thêm {format_vnd(int(-diff))}."
        else:
            status, verdict = "bad", "Vượt ngân sách"
            detail = f"Cố thêm {format_vnd(int(-diff))}."
        cells.append(ComparisonCell(value=format_vnd(int(p)), available=True, is_best=(status == "good"),
                                     status=status, verdict=verdict, detail=detail))
    return ComparisonRow(label=f"Độ khớp với ví tiền (dưới {format_vnd(int(budget_max))})",
                          unit=None, source="catalog", cells=cells,
                          better="giá thấp hơn ngân sách càng tốt", is_need_row=True)


def _plain_price_row(prices: List[float | None]) -> ComparisonRow:
    cells = [ComparisonCell(value=format_vnd(int(p)) if p is not None else _MISSING,
                             available=p is not None) for p in prices]
    for i in _best_indices(prices, "min"):
        cells[i].is_best = True
    return ComparisonRow(label="Giá", unit=None, source="catalog", cells=cells,
                          better="giá thấp hơn tốt hơn")


def _tradeoff_sentences(rows: List[ComparisonRow], n: int) -> List[str]:
    need_rows = [r for r in rows if r.is_need_row]
    sentences: List[str] = []
    for i in range(n):
        bad = next((r for r in need_rows if r.cells[i].status == "bad"), None)
        warn = next((r for r in need_rows if r.cells[i].status == "warn"), None)
        good = next((r for r in need_rows if r.cells[i].status == "good"), None)
        weak = bad or warn
        if weak and good:
            sentences.append(
                f"Chấp nhận {weak.cells[i].verdict.lower()} ở \"{weak.label}\" "
                f"để đổi lấy {good.cells[i].verdict.lower()} ở \"{good.label}\"."
            )
        elif weak:
            sentences.append(f"Điểm cần cân nhắc: {weak.cells[i].verdict.lower()} ở \"{weak.label}\".")
        elif good:
            sentences.append(f"Lựa chọn cân bằng, nổi bật ở \"{good.label}\".")
        else:
            sentences.append("Chưa đủ dữ liệu để chỉ ra điểm đánh đổi rõ rệt.")
    return sentences


def build_comparison(rows: List[Dict[str, Any]], priority_features: List[str],
                     budget_max: float | None = None, llm: Any = None) -> ComparisonTable | None:
    """Bảng so sánh theo nhu cầu khách, mọi ô lấy trực tiếp từ DB (không qua LLM)."""
    unique_rows = []
    seen = set()
    for r in rows:
        key = r.get("model_code") or r.get("sku") or product_display_name(r)
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)

    rows = unique_rows[:3]
    if len(rows) < 2:
        return None
    products = [product_display_name(r) for r in rows]
    out_rows: List[ComparisonRow] = []

    # 1) Giá / độ khớp ngân sách
    prices = [_price_val(r) for r in rows]
    if budget_max:
        out_rows.append(_budget_row(rows, prices, budget_max))
    else:
        out_rows.append(_plain_price_row(prices))

    # 2) Mọi thông số dùng chung. AI quyết định thang tốt hơn/kém hơn từ tên và
    # giá trị thực; field không có kết luận chắc chắn vẫn được đặt cạnh nhau.
    specs_per = [load_specs(r) for r in rows]
    field_count: Dict[str, int] = {}
    for sp in specs_per:
        for k, v in sp.items():
            if v is not None and str(v).strip():
                field_count[k] = field_count.get(k, 0) + 1
    prefs_low = [p.lower() for p in (priority_features or [])]
    common_fields = [f for f, count in field_count.items() if count >= 2]
    rules = _comparison_rules(common_fields, specs_per, llm)

    def rank(field: str):
        pref_hit = any(p in field.lower() for p in prefs_low)
        configured = field in rules
        return (0 if pref_hit else 1, 0 if configured else 1, -field_count[field], field)

    shared_fields = sorted(common_fields, key=rank)

    for field in shared_fields:
        rule = rules.get(field)
        if rule is not None:
            need_cells = _need_cells_for_field(rule, specs_per)
            out_rows.append(ComparisonRow(label=field, unit=None, source="thông số nhà sản xuất",
                                          cells=need_cells,
                                          better=("chỉ số thấp hơn tốt hơn" if rule.direction == "min"
                                                  else "chỉ số cao hơn tốt hơn"),
                                          is_need_row=True))
        else:
            cells = [ComparisonCell(value=(sp.get(field) if sp.get(field) else _MISSING),
                                    available=sp.get(field) is not None) for sp in specs_per]
            out_rows.append(ComparisonRow(label=field, unit=None, source="thông số nhà sản xuất",
                                          cells=cells, better=None))

    # 3) Thương hiệu (tham khảo, không đèn tín hiệu)
    out_rows.append(ComparisonRow(label="Thương hiệu", unit=None, source="catalog",
                                  cells=[ComparisonCell(value=r.get("brand") or "N/A") for r in rows],
                                  better=None))

    tradeoff = _tradeoff_sentences(out_rows, len(products))
    return ComparisonTable(products=products, rows=out_rows, tradeoff=tradeoff)
