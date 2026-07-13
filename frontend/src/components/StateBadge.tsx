const COLORS: Record<string, string> = {
  completed: 'badge-ok',
  running: 'badge-run',
  waiting: 'badge-wait',
  failed: 'badge-err',
  canceled: 'badge-err',
  canceling: 'badge-err',
}

export default function StateBadge({ state }: { state: string }) {
  return <span className={`badge ${COLORS[state] ?? 'badge-wait'}`}>{state}</span>
}
