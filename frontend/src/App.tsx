import { NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import SettingsPage from "./pages/Settings";
import Explorer from "./pages/Explorer";
import ExportPage from "./pages/Export";
import SearchPage from "./pages/Search";

const links = [
  ["/", "Dashboard"], ["/explorer", "Explorer"], ["/export", "Export"], ["/search", "Search"], ["/settings", "Settings"],
] as const;

export default function App() {
  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 pb-10">
      <header className="flex flex-wrap items-center justify-between gap-3 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600 font-bold text-white">F</div>
          <div><div className="font-semibold leading-tight">Frontify AI Exporter</div><div className="text-xs text-slate-500">Frontify → AI-ready knowledge base</div></div>
        </div>
        <nav className="flex gap-1 rounded-xl bg-white p-1 shadow-sm ring-1 ring-slate-200">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{label}</NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/explorer" element={<Explorer />} />
          <Route path="/export" element={<ExportPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
