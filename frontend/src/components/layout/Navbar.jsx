import { useState, useRef, useEffect } from "react";
import { NavLink, Link } from "react-router-dom";
import Button from "../ui/Button";
import { useAuth } from "../../auth/AuthContext";
import { displayNameFor, initialsFor } from "../../auth/identity";
import "./Navbar.css";

const NAV_LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/library", label: "Lecture Library" },
  { to: "/search", label: "Search" },
  { to: "/history", label: "Question History" },
];

export default function Navbar() {
  const { user, profile, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const menuRef = useRef(null);
  const triggerRef = useRef(null);

  const name = displayNameFor(user, profile);

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    function handleEscape(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    // The route guard sends the user to /login once the session is gone.
    await signOut();
  }

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <Link to="/" className="navbar__brand">
          <span className="navbar__logo-mark">T.</span>
          <span className="navbar__logo-text">LectureMind</span>
        </Link>

        <nav className="navbar__links" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => `navbar__link ${isActive ? "navbar__link--active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="navbar__actions">
          <Button as={Link} to="/lectures/new" variant="primary" className="navbar__upload">
            Upload Lecture
          </Button>

          <button
            className="navbar__icon-btn"
            aria-label="Notifications (available in a later phase)"
            title="Notifications are not available yet"
            type="button"
            disabled
          >
            <BellIcon />
          </button>

          <div className="navbar__user" ref={menuRef}>
            <button
              ref={triggerRef}
              className="navbar__user-trigger"
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-label={`Account menu for ${name}`}
              type="button"
            >
              <span className="navbar__avatar" aria-hidden="true">
                {initialsFor(name)}
              </span>
              <span className="navbar__user-meta" aria-hidden="true">
                <span className="navbar__user-name">{name}</span>
                <span className="navbar__user-email">{user?.email}</span>
              </span>
              <ChevronIcon />
            </button>

            {menuOpen && (
              <div className="navbar__menu" role="menu">
                <Link to="/profile" role="menuitem" className="navbar__menu-item" onClick={() => setMenuOpen(false)}>
                  Profile
                </Link>
                <Link to="/settings" role="menuitem" className="navbar__menu-item" onClick={() => setMenuOpen(false)}>
                  Settings
                </Link>
                <div className="navbar__menu-divider" role="separator" />
                <button
                  type="button"
                  role="menuitem"
                  className="navbar__menu-item navbar__menu-item--button"
                  onClick={handleSignOut}
                  disabled={signingOut}
                >
                  {signingOut ? "Logging out…" : "Log out"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
