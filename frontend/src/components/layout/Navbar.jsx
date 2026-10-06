import { useState, useRef, useEffect } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import Button from "../ui/Button";
import Logo from "../brand/Logo";
import { CloseIcon, MenuIcon } from "../ui/icons";
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
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const menuRef = useRef(null);

  // Close the mobile panel after navigating.
  useEffect(() => setMobileOpen(false), [location.pathname]);
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
        <Link to="/" className="navbar__brand" aria-label="LectureMind home">
          <Logo />
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

        <button
          type="button"
          className="navbar__icon-btn navbar__mobile-toggle"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
        </button>

        <div className="navbar__actions">
          <Button as={Link} to="/lectures/new" variant="primary" className="navbar__upload">
            Add Lecture
          </Button>

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
              <span className="navbar__user-name" aria-hidden="true">
                {name}
              </span>
              <ChevronIcon />
            </button>

            {menuOpen && (
              <div className="navbar__menu" role="menu">
                <div className="navbar__menu-header" role="presentation">
                  <span className="navbar__menu-name">{name}</span>
                  <span className="navbar__menu-email">{user?.email}</span>
                </div>
                <div className="navbar__menu-divider" role="separator" />
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

      {mobileOpen && (
        <nav id="mobile-nav" className="navbar__mobile" aria-label="Primary">
          {NAV_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) => `navbar__mobile-link ${isActive ? "navbar__mobile-link--active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
          <Button as={Link} to="/lectures/new" className="navbar__mobile-upload">
            Add Lecture
          </Button>
        </nav>
      )}
    </header>
  );
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}
