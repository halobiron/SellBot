import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ComparisonTable from './ComparisonTable'
import ContextualSuggestions from './ContextualSuggestions'

export default function Message({ msg, isLast, onSuggest, disabled }) {
  const { role, text, recommendation } = msg
  const [activeCard, setActiveCard] = useState(null)
  const [activeTab, setActiveTab] = useState('specs')

  const isUser = role === 'user'

  return (
    <div className={`msg ${isUser ? 'user' : 'bot'}`}>
      <div className="bubble">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>

      {recommendation?.warnings?.length > 0 && (
        <div className="warn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
          <span>Một số thông số chưa rõ nguồn chính thức đã được ẩn để tránh sai lệch.</span>
        </div>
      )}

      {recommendation?.comparison && (
        <ComparisonTable table={recommendation.comparison} cards={recommendation.cards} />
      )}

      {recommendation?.cards && recommendation.cards.length > 0 && (
        <div className="product-cards-grid">
          {recommendation.cards.map((c, i) => {
            const titleText = c.title
              .replace('Vì sao em đề xuất ', '')
              .replace('Thông tin chi tiết: ', '')
              .replace('?', '')

            const priceLine = c.lines?.find((l) => l.label === 'Giá')
            const origPriceLine = c.lines?.find((l) => l.label === 'Giá gốc')
            const promoLine = c.lines?.find((l) => l.label === 'Khuyến mãi/quà kèm')

            const cardBadgeLabels = ['Giá', 'Giá gốc', 'Khuyến mãi/quà kèm', 'Tình trạng', 'Đánh giá', 'Trả góp']
            const specLines = c.lines?.filter((l) => !cardBadgeLabels.includes(l.label)) || []

            let promos = []
            if (promoLine && promoLine.value) {
              promos = promoLine.value.split('|').map((p) => p.trim()).filter(Boolean)
            }

            return (
              <div className="product-card" key={i}>
                <div className="product-card-img">
                  {c.image_url ? (
                    <img src={c.image_url} alt={titleText} loading="lazy" />
                  ) : (
                    <div className="img-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25" />
                      </svg>
                    </div>
                  )}
                  {c.installment && <span className="badge-inst">Trả góp 0%</span>}
                </div>

                <div className="product-card-info">
                  <h4 className="product-title" title={titleText}>
                    {titleText}
                  </h4>

                  <div className="product-price-row">
                    {priceLine && <span className="price-current">{priceLine.value}</span>}
                    {origPriceLine && <span className="price-orig">{origPriceLine.value}</span>}
                  </div>

                  {c.rating && (
                    <div className="product-rating">
                      <span className="star">★</span>
                      <span className="rating-val">{c.rating}</span>
                      {c.review_count && <span className="review-num">({c.review_count})</span>}
                    </div>
                  )}

                  <div className="product-card-buttons">
                    <button
                      className="btn-outline"
                      onClick={() => {
                        setActiveCard({
                          titleText,
                          specLines,
                          promos,
                          missing: c.missing,
                          product_link: c.product_link,
                          reviews: c.reviews || [],
                          rating: c.rating,
                          review_count: c.review_count,
                          price: priceLine?.value,
                        })
                        setActiveTab(specLines.length > 0 ? 'specs' : 'promos')
                      }}
                    >
                      Chi tiết
                    </button>

                    {c.product_link && (
                      <a
                        href={c.product_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-primary"
                      >
                        Mua ngay
                      </a>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {isLast && role === 'bot' && onSuggest && (
        <ContextualSuggestions cards={recommendation?.cards} onPick={onSuggest} disabled={disabled} />
      )}

      {recommendation?.assumptions?.length > 0 && (
        <div className="assume">Giả định: {recommendation.assumptions.join(' ')}</div>
      )}

      {/* Product Detail Modal */}
      {activeCard && (
        <div className="modal-backdrop" onClick={() => setActiveCard(null)}>
          <div className="modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h3 className="modal-heading">{activeCard.titleText}</h3>
                {activeCard.price && <div className="modal-price">{activeCard.price}</div>}
              </div>
              <button className="modal-close" onClick={() => setActiveCard(null)} aria-label="Đóng">
                ✕
              </button>
            </div>

            <div className="modal-nav">
              <button
                className={`modal-nav-btn ${activeTab === 'specs' ? 'active' : ''}`}
                onClick={() => setActiveTab('specs')}
              >
                Thông số ({activeCard.specLines.length})
              </button>
              <button
                className={`modal-nav-btn ${activeTab === 'promos' ? 'active' : ''}`}
                onClick={() => setActiveTab('promos')}
              >
                Khuyến mãi ({activeCard.promos.length})
              </button>
              {activeCard.reviews.length > 0 && (
                <button
                  className={`modal-nav-btn ${activeTab === 'reviews' ? 'active' : ''}`}
                  onClick={() => setActiveTab('reviews')}
                >
                  Đánh giá ({activeCard.reviews.length})
                </button>
              )}
            </div>

            <div className="modal-content-body">
              {activeTab === 'specs' ? (
                <div className="specs-table">
                  {activeCard.specLines.map((l, i) => (
                    <div className="spec-row" key={i}>
                      <span className="spec-name">{l.label}</span>
                      <span className="spec-data">{l.value}</span>
                    </div>
                  ))}
                  {activeCard.specLines.length === 0 && <p className="empty">Chưa có thông số chi tiết.</p>}
                  {activeCard.missing && activeCard.missing.length > 0 && (
                    <div className="missing-notice">
                      Chưa có dữ liệu chính thức: {activeCard.missing.join(', ')}
                    </div>
                  )}
                </div>
              ) : activeTab === 'reviews' ? (
                <div className="reviews-list">
                  {activeCard.rating != null && (
                    <div className="reviews-summary">
                      <span className="big-rating">{activeCard.rating} ★</span>
                      {activeCard.review_count != null && (
                        <span>({activeCard.review_count.toLocaleString('vi-VN')} đánh giá từ khách hàng)</span>
                      )}
                    </div>
                  )}
                  {activeCard.reviews.map((r, i) => (
                    <div className="review-box" key={i}>
                      <div className="review-top">
                        <strong>{r.author || 'Khách hàng'}</strong>
                        {r.rating != null && <span className="review-star">★ {r.rating}</span>}
                      </div>
                      <p>{r.content}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="promos-list">
                  {activeCard.promos.map((p, i) => (
                    <div className="promo-row" key={i}>
                      <span className="promo-gift-icon">🎁</span>
                      <span>{p}</span>
                    </div>
                  ))}
                  {activeCard.promos.length === 0 && <p className="empty">Không có khuyến mãi kèm theo.</p>}
                </div>
              )}
            </div>

            {activeCard.product_link && (
              <div className="modal-foot">
                <a
                  href={activeCard.product_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary full-width"
                >
                  Xem tại dienmayxanh.com &rarr;
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}


