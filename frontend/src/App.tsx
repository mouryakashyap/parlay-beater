// App.tsx — root layout shell and route registry.
// All pages are lazy-loaded here; shared chrome (nav, max-width wrapper) lives here too.
import { Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Predictions from "./pages/Predictions";
import History from "./pages/History";

export default function App() {
  return (
    // Full-viewport dark background; all page content inherits text-gray-100
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 px-6 py-3 flex items-center gap-8">
        <span className="text-base font-bold text-green-400 shrink-0">⚽ Parlay Beater</span>
        <div className="flex gap-1">
          {[
            { to: '/',            label: 'Dashboard'   },
            { to: '/predictions', label: 'Predictions' },
            { to: '/history',     label: 'History'     },
          ].map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-gray-800 text-white font-medium'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-gray-900'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* max-w-5xl keeps content readable on wide screens */}
      <main className="max-w-5xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/predictions" element={<Predictions />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>
    </div>
  );
}
