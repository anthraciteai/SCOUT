import { NavLink, Route, Routes } from "react-router-dom";
import { useSelection } from "./selection";
import { useAuth } from "./auth";
import Inbox from "./pages/Inbox";
import Browse from "./pages/Browse";
import TopicDetail from "./pages/TopicDetail";
import Workspace from "./pages/Workspace";
import Analysis from "./pages/Analysis";
import Tracker from "./pages/Tracker";
import GroupDesk from "./pages/GroupDesk";
import Proposals from "./pages/Proposals";
import Debriefs from "./pages/Debriefs";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import Org from "./pages/Org";
import Login from "./pages/Login";

const NAV_ITEM_BASE =
  "flex items-center justify-between gap-2 px-3 py-2.5 rounded-[10px] text-sm font-medium transition-colors no-underline";
const NAV_ITEM_IDLE = "text-muted hover:text-ink hover:bg-white/5";
const NAV_ITEM_ACTIVE =
  "text-ink bg-ember/10 shadow-[inset_3px_0_0_#ff7a1a]";

function NavItem({
  to,
  end,
  label,
  hint,
  badge,
}: {
  to: string;
  end?: boolean;
  label: string;
  hint?: string;
  badge?: number;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `${NAV_ITEM_BASE} ${isActive ? NAV_ITEM_ACTIVE : NAV_ITEM_IDLE}`
      }
    >
      <span className="flex flex-col leading-tight">
        <span>{label}</span>
        {hint && <span className="text-[11px] text-faint font-normal">{hint}</span>}
      </span>
      {badge != null && badge > 0 && <span className="badge">{badge}</span>}
    </NavLink>
  );
}

function NavSection({ title }: { title: string }) {
  return (
    <div className="text-[10px] text-faint font-extrabold uppercase tracking-[0.14em] mx-3 mt-4 mb-1 first:mt-1.5">
      {title}
    </div>
  );
}

function Sidebar() {
  const { ids } = useSelection();
  const { user, logout } = useAuth();
  return (
    <aside className="sidebar">
      <div className="brand">SCOUT</div>
      <div className="tagline">Drop your resume. Qualified gov work comes to you.</div>
      <nav className="flex flex-col gap-0.5">
        <NavSection title="Find" />
        <NavItem to="/" end label="Inbox" hint="ranked for you" />
        <NavItem to="/browse" label="Browse" hint="search all topics" />

        <NavSection title="Pursue" />
        <NavItem to="/tracker" label="Pipeline" hint="bids you're tracking" />
        <NavItem to="/analysis" label="Council" hint="deep agent analysis" badge={ids.length} />
        <NavItem to="/proposals" label="Proposals" hint="drafts + reviews" />
        <NavItem to="/desk" label="Team room" hint="shared per-bid workspace" />
        <NavItem to="/debriefs" label="Debriefs" hint="win / loss lessons" />

        <NavSection title="Setup" />
        <NavItem to="/org" label="Company" hint="mission + products" />
        <NavItem to="/profile" label="Profile" hint="you + resume" />
        <NavItem to="/settings" label="Settings" />
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
          <Route path="/work/:id" element={<Workspace />} />
          {/* Vanity URL for a personal fit view. The actual fit identity comes
              from the JWT on the backend, never from this path segment. */}
          <Route path="/work/:id/ME/:userId" element={<Workspace />} />
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
