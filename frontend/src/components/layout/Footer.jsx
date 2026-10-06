import { Link } from "react-router-dom";
import { LogoMark } from "../brand/Logo";
import "./Footer.css";

/** Site footer. `links`: [{ to | href, label }] - optional page links. */
export default function Footer({ links = [] }) {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__brand">
          <LogoMark size={22} />
          <strong>LectureMind</strong>
          <span className="footer__tagline">Lecture Intelligence Platform</span>
        </div>
        {links.length > 0 && (
          <nav className="footer__links" aria-label="Footer">
            {links.map((link) =>
              link.to ? (
                <Link key={link.label} to={link.to}>
                  {link.label}
                </Link>
              ) : (
                <a key={link.label} href={link.href}>
                  {link.label}
                </a>
              ),
            )}
          </nav>
        )}
        <p className="footer__note">© {new Date().getFullYear()} LectureMind</p>
      </div>
    </footer>
  );
}
