import { Navigate, Outlet, useLocation } from "react-router-dom";
import FullPageLoader from "../components/feedback/FullPageLoader";
import { useAuth } from "./AuthContext";

/**
 * For login / sign-up / forgot-password: once a session exists, send the user
 * on to where they were going (or the dashboard).
 */
export default function PublicOnlyRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") return <FullPageLoader />;

  if (status === "authenticated") {
    const from = location.state?.from;
    const target = from ? `${from.pathname}${from.search ?? ""}` : "/dashboard";
    return <Navigate to={target} replace />;
  }

  return <Outlet />;
}
