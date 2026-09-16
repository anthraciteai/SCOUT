import { NavLink, Route, Routes } from "react-router-dom";
import { useSelection } from "./selection";
import Browse from "./pages/Browse";
import TopicDetail from "./pages/TopicDetail";
import Analysis from "./pages/Analysis";
import Tracker from "./pages/Tracker";
import Proposals from "./pages/Proposals";
import Debriefs from "./pages/Debriefs";
import Settings from "./pages/Settings";

function Sidebar() {
  const { ids } = useSelection();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  return (
    <aside className="sidebar">
      <div className="brand">
        SBIR <span>Scout</span>
      </div>
      <div className="tagline">DoD SBIR/STTR topic intelligence</div>
      <nav className="nav">
        <NavLink to="/" end className={link}>
          Browse Topics
        </NavLink>
        <NavLink to="/analysis" className={link}>
          <span>Analysis</span>
          {ids.length > 0 && <span className="badge">{ids.length}</span>}
        </NavLink>
        <NavLink to="/tracker" className={link}>
          Tracker
        </NavLink>
        <NavLink to="/proposals" className={link}>
          Proposals
        </NavLink>
        <NavLink to="/debriefs" className={link}>
          Debriefs
        </NavLink>
        <NavLink to="/settings" className={link}>
          Settings
        </NavLink>
      </nav>
    </aside>
  );
}

export default function App() {
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<Browse />} />
          <Route path="/topic/:id" element={<TopicDetail />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/tracker" element={<Tracker />} />
          <Route path="/proposals" element={<Proposals />} />
          <Route path="/debriefs" element={<Debriefs />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
