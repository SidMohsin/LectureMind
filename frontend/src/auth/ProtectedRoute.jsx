import { Navigate, Outlet, useLocation } from "react-router-dom";
import FullPageLoader from "../components/feedback/FullPageLoader";
import { useAuth } from "./AuthContext";

/**
 * Renders child routes only for a signed-in user. This is a UX guard; the
 * backend and database enforce access independently.
 */
export default function ProtectedRoute() {
  const { status, signOutReason } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageLoader />;

  if (status === "unauthenticated") {
    const from = signOutReason === "signed_out" ? undefined : location;
    return <Navigate to="/login" replace state={{ from, reason: signOutReason }} />;
  }

  return <Outlet />;
}
