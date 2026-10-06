import { Link } from "react-router-dom";
import Button from "../../components/ui/Button";
import Logo from "../../components/brand/Logo";
import { useAuth } from "../../auth/AuthContext";
import "./NotFound.css";

export default function NotFound() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  return (
    <div className="not-found">
      <Link to="/" className="not-found__brand" aria-label="LectureMind home">
        <Logo />
      </Link>
      <div className="not-found__body">
        <p className="not-found__code mono">404</p>
        <h1>Page not found</h1>
        <p className="not-found__text">The page you’re looking for doesn’t exist or has moved.</p>
        <div className="not-found__actions">
          {signedIn ? (
            <>
              <Button as={Link} to="/dashboard">
                Go to Dashboard
              </Button>
              <Button as={Link} to="/library" variant="secondary">
                Open Library
              </Button>
            </>
          ) : (
            <>
              <Button as={Link} to="/">
                Back to Home
              </Button>
              <Button as={Link} to="/login" variant="secondary">
                Log In
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
