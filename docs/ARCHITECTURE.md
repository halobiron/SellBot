# Kiến trúc hệ thống — Trợ lý AI tư vấn Điện Máy Xanh

## Pipeline phục vụ

Ứng dụng chỉ dùng một pipeline `agent_core`, chạy trên LangGraph và SQLite:

```
Khách nhắn
  → intent
  → router
  → clarify | chitchat | policy | detail | retrieve
  → advisor → compare → verify
  → API response / SSE
```

- `intent`: trích xuất ngành hàng, ngân sách, thương hiệu, ưu tiên và ngữ cảnh hội thoại.
- `router`: chọn nhánh xử lý, ưu tiên các trường hợp ngoài catalog, hậu mãi và câu hỏi chính sách.
- `retrieve`: truy vấn SQLite chỉ đọc theo dữ kiện đã trích xuất.
- `advisor` và `compare`: dựng fact card, lời tư vấn và bảng so sánh từ kết quả truy vấn.
- `verify`: kiểm tra số liệu trước khi gửi về client.

Trạng thái hội thoại được LangGraph `MemorySaver` lưu theo `session_id`. `POST /api/reset` tăng epoch của phiên, khiến lượt tiếp theo bắt đầu với ngữ cảnh mới.

## Dữ liệu

`app/agent_core/products.db` là nguồn dữ liệu runtime. Mô-đun `catalog/` và các script phục vụ làm sạch, chuẩn hoá hoặc nạp lại dữ liệu, không nằm trên luồng trả lời chat.

## Guardrail chống bịa số liệu

1. Agent chỉ đưa fact card đã gắn nguồn vào prompt.
2. Prompt yêu cầu không suy diễn giá hay thông số.
3. `app/advice/verify.py` đối chiếu mọi số trong phản hồi với fact card. Nếu phát hiện số không có nguồn, `advisor` trả bản tóm tắt an toàn dựng từ fact card thay vì phát nội dung của LLM.

Với SSE, nội dung được kiểm chứng trước khi hoàn tất phản hồi; khi cần fallback, client nhận payload `done` cùng câu trả lời an toàn.

## API

- `POST /api/chat`
- `POST /api/chat/stream`
- `POST /api/reset`
- `GET /api/health`

Mọi endpoint chat trả cùng contract: `reply`, `stage`, `question`, `need`, `recommendation`.
