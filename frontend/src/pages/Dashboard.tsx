import { api } from '../api'
import { formatBytes, usePolling } from '../hooks'

export default function Dashboard() {
  const { data, error } = usePolling(() => api.overview(), 10_000)

  if (error) return <div className="banner banner-err">無法取得系統狀態:{error}</div>
  if (!data) return <div className="muted">載入中…</div>

  const storagePct =
    data.storage_total && data.storage_used != null
      ? Math.round((data.storage_used / data.storage_total) * 100)
      : null

  return (
    <>
      <h1>Dashboard</h1>
      <div className="cards">
        <div className="card">
          <div className="card-title">Repositories</div>
          <div className="card-value">
            {data.repo_counts.rpm + data.repo_counts.deb + data.repo_counts.container}
          </div>
          <div className="muted">
            rpm {data.repo_counts.rpm} · deb {data.repo_counts.deb} · container{' '}
            {data.repo_counts.container}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Running tasks</div>
          <div className="card-value">{data.running_tasks}</div>
        </div>
        <div className={`card ${data.failed_tasks > 0 ? 'card-warn' : ''}`}>
          <div className="card-title">Failed tasks</div>
          <div className="card-value">{data.failed_tasks}</div>
        </div>
        <div className="card">
          <div className="card-title">Workers / Content apps</div>
          <div className="card-value">
            {data.online_workers} / {data.online_content_apps}
          </div>
        </div>
        <div className="card">
          <div className="card-title">Storage</div>
          <div className="card-value">
            {storagePct != null ? `${storagePct}%` : '—'}
          </div>
          <div className="muted">
            {formatBytes(data.storage_used)} / {formatBytes(data.storage_total)}
          </div>
          {storagePct != null && (
            <div className="meter">
              <div
                className={`meter-fill ${storagePct >= 80 ? 'meter-hot' : ''}`}
                style={{ width: `${Math.min(storagePct, 100)}%` }}
              />
            </div>
          )}
        </div>
      </div>
      <h2>元件版本</h2>
      <table className="table">
        <tbody>
          {Object.entries(data.versions).map(([component, version]) => (
            <tr key={component}>
              <td>{component}</td>
              <td>{version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
