import { Link } from "react-router-dom";
import Logo from "../brand/Logo";
import "./AuthLayout.css";

/**
 * Focused, distraction-free layout shared by authentication screens
 * (login, sign up, verification, password reset).
 */
export default function AuthLayout({ title, description, children, footer }) {
  return (
    <div className="auth-layout">
      <Link to="/" className="auth-layout__brand" aria-label="LectureMind home">
        <Logo size={30} />
      </Link>
      <div className="auth-layout__card">
        <h1 className="auth-layout__title">{title}</h1>
        {description && <p className="auth-layout__description">{description}</p>}
        <div className="auth-layout__body">{children}</div>
      </div>
      {footer && <p className="auth-layout__footer">{footer}</p>}
    </div>
  );
}
