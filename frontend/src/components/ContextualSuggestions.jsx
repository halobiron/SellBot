function shortName(title) {
  return title
    .replace('Vì sao em đề xuất ', '')
    .replace('Thông tin chi tiết: ', '')
    .replace('?', '')
    .trim()
}

export default function ContextualSuggestions({ cards, onPick, disabled }) {
  if (!cards || cards.length === 0) return null
  const names = cards.slice(0, 3).map((c) => shortName(c.title)).filter(Boolean)
  if (names.length === 0) return null

  const chips = []
  if (names.length >= 2) {
    chips.push({
      label: `So sánh ${names[0]} và ${names[1]}`,
      message: `So sánh ${names[0]} và ${names[1]} giúp tôi`,
    })
  }
  chips.push({
    label: `Xem chi tiết ${names[0]}`,
    message: `Cho tôi xem chi tiết thông số và tính năng của ${names[0]}`,
  })
  chips.push({
    label: `${names[0]} có trả góp không?`,
    message: `${names[0]} có hỗ trợ mua trả góp 0% không?`,
  })

  return (
    <div className="contextual-chips">
      {chips.map((c, idx) => (
        <button
          key={idx}
          className="context-chip-btn"
          disabled={disabled}
          onClick={() => onPick(c.message)}
        >
          {c.label}
        </button>
      ))}
    </div>
  )
}


