import { useEffect, useState } from 'react'
import { api } from '../api'

export default function ClientConfigModal({
  repoName,
  onClose,
}: {
  repoName: string
  onClose: () => void
}) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api
      .clientConfig(repoName)
      .then(setText)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [repoName])

  async function copy() {
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setError('複製失敗,請手動選取')
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>用戶端設定 — {repoName}</h2>
        {error && <div className="banner banner-err">{error}</div>}
        {text ? <pre className="config-pre">{text}</pre> : !error && <div className="muted">載入中…</div>}
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>
            關閉
          </button>
          <button className="btn btn-primary" onClick={copy} disabled={!text}>
            {copied ? '已複製 ✓' : '複製'}
          </button>
        </div>
      </div>
    </div>
  )
}
