from app.catalog.loader import load_catalog
from app.config import get_settings


def test_catalog_loads_all_six_categories():
    products = load_catalog(get_settings().catalog_path)
    codes = {p.category_code for p in products}
    assert codes == {"tu_lanh", "may_say", "may_rua_chen", "tu_mat", "dong_ho", "man_hinh"}
    assert sum(p.category_code == "tu_lanh" for p in products) > 1000
