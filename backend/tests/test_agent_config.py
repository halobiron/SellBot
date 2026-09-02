from app.config import Settings
from app.agent_core.retriever import search_products, get_catalog_metadata, hydrate_rows
from tests.agent_helpers import make_db


def test_settings_defaults():
    s = Settings()
    assert s.agent_db_path.endswith("products.db")


def test_search_uses_explicit_db(tmp_path):
    db = str(tmp_path / "t.db")
    make_db(db, [{"category": "Tủ Lạnh", "brand": "Toshiba", "model_code": "TL1", "price_clean": 12_000_000,
                  "specs": {"Dung tích tổng": "300 lít"}}])
    res = search_products("tủ lạnh", category="Tủ Lạnh", db_path=db)
    assert res["status"] == "exact_match"
    assert res["total_matches_found"] == 1
    assert res["top_3_products"][0]["brand"] == "Toshiba"


def test_search_includes_and_labels_a_near_budget_option(tmp_path):
    db = str(tmp_path / "t.db")
    make_db(db, [
        {"category": "Tủ Lạnh", "brand": "A", "model_code": "UNDER", "price_clean": 10_000_000, "specs": {}},
        {"category": "Tủ Lạnh", "brand": "A", "model_code": "OVER", "price_clean": 10_200_000, "specs": {}},
    ])

    res = search_products("tủ lạnh", category="Tủ Lạnh", max_price=10_000_000, db_path=db)

    assert res["status"] == "exact_match"
    by_model = {row["model_code"]: row for row in res["all_top_k"]}
    assert set(by_model) == {"UNDER", "OVER"}
    assert by_model["UNDER"]["_over_budget"] is False
    assert by_model["OVER"]["_over_budget"] is True


def test_search_reports_no_match_instead_of_budget_fallback(tmp_path):
    db = str(tmp_path / "t.db")
    make_db(db, [
        {"category": "Tủ Lạnh", "brand": "A", "model_code": "OVER", "price_clean": 10_500_001, "specs": {}},
    ])

    res = search_products("tủ lạnh", category="Tủ Lạnh", max_price=10_000_000, db_path=db)

    assert res["status"] == "no_products_found"
    assert res["total_matches_found"] == 0
    assert res["top_3_products"] == []


def test_metadata_lists_categories(tmp_path):
    db = str(tmp_path / "t.db")
    make_db(db, [{"category": "Máy giặt", "brand": "LG", "price_clean": 9_000_000, "specs": {}}])
    meta = get_catalog_metadata(db)
    assert "Máy giặt" in meta["categories"]


def test_hydrate_prefers_model_code_over_foreign_category_table_id(tmp_path):
    db = str(tmp_path / "t.db")
    make_db(db, [
        {"category": "Tủ Lạnh", "brand": "A", "model_code": "wrong", "price_clean": 0, "specs": {}},
        {"category": "Tủ Lạnh", "brand": "B", "model_code": "right", "price_clean": 12_000_000, "specs": {}},
    ])
    # id=1 mô phỏng id của bảng ngành; nó không được dùng để hydrate model "right".
    rows = hydrate_rows([{"id": 1, "model_code": "right"}], db)
    assert rows[0]["model_code"] == "right"
    assert rows[0]["price_clean"] == 12_000_000
