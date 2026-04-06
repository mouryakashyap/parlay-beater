import { Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="border-b border-gray-800 px-6 py-4">
        <span className="text-lg font-bold text-green-400">⚽ Parlay Beater</span>
      </nav>
      <main className="max-w-5xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          {/* Phase 6: add Predictions, History, Teams routes */}
        </Routes>
      </main>
    </div>
  );
}
