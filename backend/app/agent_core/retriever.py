import sqlite3
import re
from typing import List, Dict, Any, Optional
from app.config import get_settings


def _resolve_db(db_path: Optional[str]) -> str:
    return db_path or get_settings().agent_db_path


def get_catalog_metadata(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Dynamically fetches distinct categories, sample brands, and price ranges
    directly from the SQLite database without hardcoding.
    """
    db_path = _resolve_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get distinct categories
    cursor.execute("SELECT DISTINCT category FROM all_products WHERE category IS NOT NULL")
    categories = [row[0] for row in cursor.fetchall() if row[0]]
    
    # Get distinct brands
    cursor.execute("SELECT DISTINCT brand FROM all_products WHERE brand IS NOT NULL AND brand != 'Unknown'")
    brands = [row[0] for row in cursor.fetchall() if row[0]]

    cursor.execute("SELECT COUNT(*) FROM all_products")
    product_count = cursor.fetchone()[0]
    
    conn.close()
    return {
        "categories": categories,
        "brands": brands,
        "product_count": product_count,
    }

def get_schema_summary(db_path: Optional[str] = None) -> str:
    """
    Returns a clean summary of the database schema for LangChain prompt injection.
    """
    db_path = _resolve_db(db_path)
    meta = get_catalog_metadata(db_path)
    cats_str = ", ".join(f"'{c}'" for c in meta["categories"])
    return f"Danh mục sản phẩm hiện có trong CSDL ({len(meta['categories'])} danh mục): [{cats_str}]"


def find_product_by_identifier(query: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Trả về sản phẩm khi khách nêu đúng model code hoặc SKU trong catalog.

    Mã là định danh dữ liệu, không phải điều kiện ngữ nghĩa để LLM suy luận. Chỉ
    nhận chuỗi số từ 5 chữ số để không nhầm ngân sách ngắn với mã sản phẩm; nếu
    một mã trỏ đến nhiều dòng thì không tự ý chọn biến thể.
    """
    identifiers = re.findall(r"(?<!\d)\d{5,}(?!\d)", query)
    if not identifiers:
        return None
    conn = sqlite3.connect(_resolve_db(db_path))
    conn.row_factory = sqlite3.Row
    try:
        matches: List[sqlite3.Row] = []
        for identifier in identifiers:
            matches.extend(conn.execute(
                "SELECT * FROM all_products WHERE CAST(model_code AS TEXT) = ? "
                "OR CAST(sku AS TEXT) = ?",
                (identifier, identifier),
            ).fetchall())
    finally:
        conn.close()
    unique = {row["id"]: dict(row) for row in matches}
    return next(iter(unique.values())) if len(unique) == 1 else None

def score_product(prod: Dict[str, Any], query: str, priority_features: Optional[List[str]] = None) -> float:
    """
    Dynamic relevance scoring combining query token overlap, priority feature matches, and spec richness.
    """
    score = 0.0
    name = str(prod.get("key_specs_summary", "") or prod.get("sku", "") or prod.get("model_code", ""))
    specs = str(prod.get("full_specs_json", ""))
    cat = str(prod.get("category", ""))
    brand = str(prod.get("brand", ""))
    
    text_pool = f"{name} {specs} {cat} {brand}".lower()
    query_lower = query.lower()
    
    # 1. Query token matching
    tokens = [t for t in re.findall(r'\w+', query_lower) if len(t) > 1]
    for token in tokens:
        if token in text_pool:
            score += 2.0
            if token in name.lower():
                score += 3.0
                
    # 2. Priority features matching
    if priority_features:
        for feat in priority_features:
            feat_lower = feat.lower()
            if feat_lower in text_pool:
                score += 5.0
            # Check capacity or numeric matches
            nums = re.findall(r'\d+(?:\.\d+)?', feat_lower)
            for n in nums:
                if n in name or n in specs:
                    score += 2.0
                    
    # 3. Prefer items with valid listed prices
    price_val = prod.get("price_clean")
    if not price_val or float(price_val) <= 0:
        score -= 3.0
    else:
        score += 2.0
        
    return score

def category_table_for(category: str, db_path: Optional[str] = None) -> Optional[str]:
    """Tên bảng thông số riêng của một danh mục (vd 'Tủ Lạnh' -> 'tu_lanh')."""
    conn = sqlite3.connect(_resolve_db(db_path))
    try:
        row = conn.execute("SELECT DISTINCT category_table FROM all_products WHERE category = ?",
                           (category,)).fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] else None


def hydrate_rows(rows: List[Dict[str, Any]], db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Đổi kết quả tool SQL về dòng all_products chuẩn (có price_clean/full_specs_json cho
    fact card), giữ nguyên thứ tự. Nối bằng cột id (duy nhất) khi có; model_code KHÔNG duy
    nhất (biến thể chung mã) nên chỉ là đường lui khi truy từ bảng ngành."""
    codes = [str(r.get("model_code") or "").strip() for r in rows]
    ids = [r.get("id") for r in rows if r.get("id") is not None]
    conn = sqlite3.connect(_resolve_db(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Kết quả từ bảng chuyên ngành cũng có cột ``id``, nhưng đó KHÔNG phải id
        # của all_products. model_code là khoá liên kết an toàn đã được SQL tool yêu
        # cầu trả về, nên luôn ưu tiên nó; chỉ dùng id khi truy vấn thực sự không có mã.
        codes = [c for c in codes if c]
        if codes:
            marks = ",".join("?" * len(codes))
            got = {}
            for r in conn.execute(f"SELECT * FROM all_products WHERE model_code IN ({marks})", codes):
                got.setdefault(str(r["model_code"]), dict(r))
            seen: set = set()
            ordered = []
            for c in codes:
                if c in got and c not in seen:
                    ordered.append(got[c])
                    seen.add(c)
        elif ids:
            marks = ",".join("?" * len(ids))
            got = {r["id"]: dict(r) for r in conn.execute(
                f"SELECT * FROM all_products WHERE id IN ({marks})", ids)}
            ordered = [got[i] for i in ids if i in got]
        else:
            return []
    finally:
        conn.close()
    out = []
    for p in ordered:
        p["_score"] = 0.0
        p["name"] = (f"Model {p.get('model_code') or p.get('sku', 'N/A')} - {p.get('brand', '')}"
                     if p.get("model_code") or p.get("sku")
                     else str(p.get("key_specs_summary", "Sản phẩm")))
        p["price"] = p.get("price_clean") or 0
        out.append(p)
    return out


def price_spread_products(category: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Khách từ chối chốt ngân sách -> chọn 3 đại diện rẻ / tầm trung / cao cấp của ngành
    (thay vì top theo điểm, để khách định hình mặt bằng giá)."""
    db_path = _resolve_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM all_products WHERE category = ? AND price_clean > 0 ORDER BY price_clean ASC"
    rows = conn.execute(sql, (category,)).fetchall()
    conn.close()
    prods = []
    for r in rows:
        p = dict(r)
        p["_score"] = 0.0
        p["name"] = (f"Model {p.get('model_code') or p.get('sku', 'N/A')} - {p.get('brand', '')}"
                     if p.get("model_code") or p.get("sku") else str(p.get("key_specs_summary", "Sản phẩm")))
        p["price"] = p.get("price_clean") or 0
        prods.append(p)
    if not prods:
        return {"status": "no_products_found", "sql_query": sql, "total_matches_found": 0,
                "top_3_products": [], "all_top_k": []}
    idx = sorted({0, len(prods) // 2, len(prods) - 1})
    picks = [prods[i] for i in idx]
    return {"status": "price_spread", "sql_query": sql.replace("?", f"'{category}'"),
            "total_matches_found": len(prods), "top_3_products": picks, "all_top_k": picks}


def search_products(
    query: str, 
    category: Optional[str] = None, 
    max_price: Optional[float] = None, 
    brand: Optional[str] = None,
    priority_features: Optional[List[str]] = None,
    top_k: int = 5,
    db_path: Optional[str] = None,
    is_meta_inquiry: bool = False
) -> Dict[str, Any]:
    """
    Retrieve catalog products using only the customer constraints.

    Budget may include a small, explicit consideration band (+5%) so a markedly
    better near-budget option is not hidden. This is still one constrained query,
    never a fallback query: items above the stated budget are flagged for the
    advisor/UI and brand/category constraints are never relaxed.
    """
    db_path = _resolve_db(db_path)
    query_lower = query.lower()
    if is_meta_inquiry or ((not category and not max_price and not brand and not priority_features) and any(w in query_lower for w in ["bao nhiêu", "loại", "danh mục", "dòng", "sản phẩm nào", "hiện có", "những gì"])):
        meta = get_catalog_metadata(db_path)
        return {
            "status": "meta_inquiry",
            "sql_query": "SELECT DISTINCT category FROM all_products",
            "total_matches_found": len(meta["categories"]),
            "top_3_products": [],
            "all_top_k": [],
            "categories_list": meta["categories"]
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    # Dynamic category filter
    if category and category.strip():
        conditions.append("category = ?")
        params.append(category.strip())
        
    # Keep a small consideration band for a potentially much better option just
    # above budget. It is labelled below, never presented as in-budget.
    if max_price and max_price > 0:
        conditions.append("price_clean > 0 AND price_clean <= ?")
        params.append(max_price * 1.05)
        
    # Dynamic brand filter
    if brand and brand.strip():
        conditions.append("LOWER(brand) = LOWER(?)")
        params.append(brand.strip())
        
    sql = "SELECT * FROM all_products"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
        
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    
    status = "exact_match"
    sql_used = sql

    conn.close()
    
    if not rows:
        status = "no_products_found"
        
    # Convert and score
    results = []
    for r in rows:
        prod = dict(r)
        prod["_over_budget"] = bool(
            max_price and max_price > 0 and float(prod.get("price_clean") or 0) > max_price
        )
        prod["_score"] = score_product(prod, query, priority_features)
        # Normalize fields for UI transparency table
        prod["name"] = f"Model {prod.get('model_code') or prod.get('sku', 'N/A')} - {prod.get('brand', '')}" if prod.get('model_code') or prod.get('sku') else str(prod.get('key_specs_summary', 'Sản phẩm'))
        prod["price"] = prod.get("price_clean") or 0
        results.append(prod)
        
    # Deterministic tie-breaker keeps equally relevant products reproducible.
    results.sort(key=lambda x: (-x["_score"], float(x.get("price_clean") or 0)))
        
    top_items = results[:top_k]
    
    # Format sql query string for UI display
    display_sql = sql_used
    display_params = params
    for p in display_params:
        if isinstance(p, str):
            display_sql = display_sql.replace("?", f"'{p}'", 1)
        else:
            display_sql = display_sql.replace("?", str(p), 1)
            
    return {
        "status": status,
        "sql_query": display_sql,
        "total_matches_found": len(results),
        "top_3_products": top_items[:3],
        "all_top_k": top_items
    }
