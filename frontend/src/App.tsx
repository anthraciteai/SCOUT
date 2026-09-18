import { NavLink, Route, Routes } from "react-router-dom";
import { useSelection } from "./selection";
import { useAuth } from "./auth";
import Inbox from "./pages/Inbox";
import Browse from "./pages/Browse";
import TopicDetail from "./pages/TopicDetail";
import Analysis from "./pages/Analysis";
import Tracker from "./pages/Tracker";
import GroupDesk from "./pages/GroupDesk";
import Proposals from "./pages/Proposals";
import Debriefs from "./pages/Debriefs";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import Org from "./pages/Org";
import Login from "./pages/Login";

function Sidebar() {
  const { ids } = useSelection();
  const { user, logout } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) => (isActive ? "active" : "");
  return (
    <aside className="sidebar">
      <div className="brand">SCOUT</div>
      <div className="tagline">Drop your resume. Qualified work comes to you.</div>
      <nav className="nav">
        <NavLink to="/" end className={link}>
          Inbox
        </NavLink>
        <NavLink to="/org" className={link}>
          Org
        </NavLink>
        <NavLink to="/browse" className={link}>
          Browse
        </NavLink>
        <NavLink to="/analysis" className={link}>
          <span>Council</span>
          {ids.length > 0 && <span className="badge">{ids.length}</span>}
        </NavLink>
        <NavLink to="/tracker" className={link}>
          Pipeline
        </NavLink>
        <NavLink to="/desk" className={link}>
          Group desk
        </NavLink>
        <NavLink to="/proposals" className={link}>
          Proposals
        </NavLink>
        <NavLink to="/debriefs" className={link}>
          Debriefs
        </NavLink>
        <NavLink to="/profile" className={link}>
          Profile
        </NavLink>
        <NavLink to="/settings" className={link}>
          Settings
        </NavLink>
      </nav>
      {user && (
        <div className="whoami">
          <div>
            <strong>{user.display_name || user.user_id}</strong>
            <div className="meta">{user.company_id}</div>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <NavLink to="/login" className="meta">
              switch
            </NavLink>
            <button className="ghost small" onClick={logout}>
              sign out
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}

export default function App() {
  const { ready, user, status } = useAuth();
  if (!ready) return <div className="spinner">Loading SCOUT…</div>;
  if (!user && status && !status.auth_disabled) {
    return <Login />;
  }
  return (
    <div className="layout">
      <Sidebar />
      <main className="content">
        <Routes>
          <Route path="/" element={<Inbox />} />
          <Route path="/org" element={<Org />} />
          <Route path="/login" element={<Login />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/topic/:id" element={<TopicDetail />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/tracker" element={<Tracker />} />
          <Route path="/desk" element={<GroupDesk />} />
          <Route path="/desk/:topicId" element={<GroupDesk />} />
          <Route path="/proposals" element={<Proposals />} />
          <Route path="/debriefs" element={<Debriefs />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
