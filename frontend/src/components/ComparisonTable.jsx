function findCardForProduct(p, cards) {
  if (!cards || !cards.length) return null
  const clean = (s) => {
    if (!s) return ''
    return s
      .toLowerCase()
      .replace(/vì sao em đề xuất /g, '')
      .replace(/thông tin chi tiết: /g, '')
      .replace(/\?/g, '')
      .trim()
  }
  const target = clean(p)

  let match = cards.find((c) => clean(c.title) === target)
  if (match) return match

  match = cards.find((c) => clean(c.title).includes(target) || target.includes(clean(c.title)))
  if (match) return match

  return null
}

function CellBody({ cell }) {
  if (cell.status && cell.verdict) {
    return (
      <div className="verdict-box">
        <span className={`verdict-text status-${cell.status}`}>{cell.verdict}</span>
        {cell.detail ? <div className="verdict-detail">{cell.detail}</div> : null}
      </div>
    )
  }
  return (
    <div className="spec-box">
      <span className="spec-text">{cell.value != null ? cell.value : '—'}</span>
      {cell.is_best ? <span className="best-tag">Tốt nhất</span> : null}
    </div>
  )
}

export default function ComparisonTable({ table, cards }) {
  if (!table || !table.products?.length || !table.rows?.length) return null
  const hasTradeoff = table.tradeoff?.length === table.products.length

  return (
    <div className="compare-container">
      <div className="compare-top">
        <h4 className="compare-title">Bảng so sánh ({table.products.length} sản phẩm)</h4>
      </div>

      <div className="compare-table-wrapper">
        <table className="clean-table">
          <thead>
            <tr>
              <th className="th-sticky">Tiêu chí</th>
              {table.products.map((p, i) => {
                const card = findCardForProduct(p, cards)
                const priceLine = card?.lines?.find((l) => l.label === 'Giá')

                return (
                  <th key={i} className="th-product">
                    <div className="product-head">
                      {card?.image_url && (
                        <img src={card.image_url} alt={p} className="product-head-thumb" />
                      )}
                      <div className="product-head-title" title={p}>{p}</div>
                      {priceLine && <div className="product-head-price">{priceLine.value}</div>}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, ri) => (
              <tr key={ri}>
                <td className="td-sticky">
                  <div className="crit-name">{row.label}</div>
                  {row.better ? <div className="crit-hint">{row.better}</div> : null}
                </td>
                {row.cells.map((c, ci) => (
                  <td
                    key={ci}
                    className={
                      c.status
                        ? `cell-status-${c.status}`
                        : c.is_best
                        ? 'cell-best'
                        : ''
                    }
                  >
                    <CellBody cell={c} />
                  </td>
                ))}
              </tr>
            ))}

            {hasTradeoff && (
              <tr className="tradeoff-tr">
                <td className="td-sticky">
                  <strong>Đánh đổi</strong>
                </td>
                {table.tradeoff.map((t, i) => (
                  <td key={i} className="tradeoff-desc">{t}</td>
                ))}
              </tr>
            )}

            <tr className="cta-tr">
              <td className="td-sticky"></td>
              {table.products.map((p, i) => {
                const card = findCardForProduct(p, cards)
                return (
                  <td key={i}>
                    {card && card.product_link ? (
                      <a
                        href={card.product_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="table-buy-btn"
                      >
                        Đặt mua
                      </a>
                    ) : null}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

