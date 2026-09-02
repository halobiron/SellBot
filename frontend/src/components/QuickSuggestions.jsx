// Simple, elegant quick-start suggestion chips
const SUGGESTIONS = [
  'Tủ lạnh 4 người tiết kiệm điện dưới 18 triệu',
  'So sánh Tivi Samsung và Sony 55 inch',
  'Máy giặt sấy 2 trong 1 chạy êm cho chung cư',
  'Điều hòa Inverter làm lạnh nhanh phòng 20m²',
]

export default function QuickSuggestions({ onPick, disabled }) {
  return (
    <div className="quick-suggestions-minimal">
      <div className="suggestions-hint">Gợi ý câu hỏi nhanh:</div>
      <div className="suggestions-chips">
        {SUGGESTIONS.map((text, idx) => (
          <button
            key={idx}
            className="suggestion-chip"
            disabled={disabled}
            onClick={() => onPick(text)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}


