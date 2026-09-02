from app.agent_core.compare import build_comparison
from app.llm.client import FakeLLM


def _row(brand, price, dientnang):
    return {"model_code": brand, "brand": brand, "price_clean": price, "category": "Tủ Lạnh",
            "key_specs_summary": "", "full_specs_json":
            '{"Điện năng tiêu thụ": "%s kWh/năm"}' % dientnang}


def test_none_for_single():
    assert build_comparison([_row("A", 12_000_000, 350)], []) is None


def test_price_row_marks_cheapest_best():
    table = build_comparison([_row("A", 12_000_000, 350), _row("B", 11_000_000, 400)], [])
    price_row = next(r for r in table.rows if r.label == "Giá")
    assert price_row.cells[1].is_best is True   # B rẻ hơn
    assert price_row.cells[0].is_best is False
    assert len(table.products) == 2


def test_brand_row_present():
    table = build_comparison([_row("A", 12_000_000, 350), _row("B", 11_000_000, 400)], [])
    assert any(r.label == "Thương hiệu" for r in table.rows)


def test_energy_row_lower_is_best():
    table = build_comparison([_row("A", 12_000_000, 350), _row("B", 11_000_000, 400)],
                             ["tiết kiệm điện"], llm=FakeLLM(json_responses=[{"rules": [
                                 {"field": "Điện năng tiêu thụ", "direction": "min", "kind": "number"}
                             ]}]))
    erow = next((r for r in table.rows if "Điện năng" in r.label), None)
    assert erow is not None
    assert erow.cells[0].is_best is True        # A tiêu thụ 350 < 400


def test_missing_cell_marked_unavailable():
    rows = [{"model_code": "A", "brand": "A", "price_clean": 0, "category": "X",
             "full_specs_json": "{}", "key_specs_summary": ""},
            {"model_code": "B", "brand": "B", "price_clean": 11_000_000, "category": "X",
             "full_specs_json": "{}", "key_specs_summary": ""}]
    table = build_comparison(rows, [])
    price_row = next(r for r in table.rows if r.label == "Giá")
    assert price_row.cells[0].available is False
    assert price_row.cells[0].value == "chưa có dữ liệu"


def test_monitor_rules_rank_size_resolution_and_dimensions():
    def monitor(brand, size, resolution, width, depth):
        return {
            "model_code": brand, "brand": brand, "price_clean": 10_000_000,
            "category": "Màn hình máy tính", "key_specs_summary": "",
            "full_specs_json": (
                '{"Kích thước màn hình": "%s inch", "Độ phân giải": "%s", '
                '"Ngang": "%s mm", "Dày": "%s mm", "Tấm nền": "IPS"}'
                % (size, resolution, width, depth)
            ),
        }

    table = build_comparison([
        monitor("A", 23.8, "QHD", 611, 216),
        monitor("B", 27, "Full HD", 620, 180),
    ], [], llm=FakeLLM(json_responses=[{"rules": [
        {"field": "Kích thước màn hình", "direction": "max", "kind": "number"},
        {"field": "Độ phân giải", "direction": "max", "kind": "ranked", "scores": [3, 2]},
        {"field": "Ngang", "direction": "min", "kind": "number"},
        {"field": "Dày", "direction": "min", "kind": "number"},
        {"field": "Tấm nền", "direction": "none", "kind": "number"},
    ]}]))
    by_label = {row.label: row for row in table.rows}
    assert by_label["Kích thước màn hình"].cells[1].is_best is True
    assert by_label["Độ phân giải"].cells[0].is_best is True
    assert by_label["Ngang"].cells[0].is_best is True
    assert by_label["Dày"].cells[1].is_best is True
    assert by_label["Tấm nền"].better is None


def test_all_shared_fields_are_kept_not_limited_to_four():
    rows = [
        {"model_code": "A", "brand": "A", "price_clean": 1, "category": "X",
         "key_specs_summary": "", "full_specs_json":
         '{"A": "1", "B": "1", "C": "1", "D": "1", "E": "1"}'},
        {"model_code": "B", "brand": "B", "price_clean": 2, "category": "X",
         "key_specs_summary": "", "full_specs_json":
         '{"A": "2", "B": "2", "C": "2", "D": "2", "E": "2"}'},
    ]
    table = build_comparison(rows, [])
    assert {"A", "B", "C", "D", "E"}.issubset({row.label for row in table.rows})
