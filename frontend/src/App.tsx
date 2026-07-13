import { NavLink, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="layout">
      <header className="topbar">
        <span className="brand">Lab Mirror</span>
        <nav>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/repos">Repositories</NavLink>
          <NavLink to="/tasks">Tasks</NavLink>
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
