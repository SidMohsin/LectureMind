import { createBrowserRouter } from "react-router-dom";
import AppShell from "../components/layout/AppShell";
import ProtectedRoute from "../auth/ProtectedRoute";
import PublicOnlyRoute from "../auth/PublicOnlyRoute";

import Landing from "../pages/Landing";
import Login from "../pages/Login";
import Signup from "../pages/Signup";
import Verify from "../pages/Verify";
import ForgotPassword from "../pages/ForgotPassword";
import ResetPassword from "../pages/ResetPassword";
import Dashboard from "../pages/Dashboard";
import Library from "../pages/Library";
import Upload from "../pages/Upload";
import Processing from "../pages/Processing";
import Workspace from "../pages/Workspace";
import Search from "../pages/Search";
import History from "../pages/History";
import Profile from "../pages/Profile";
import Settings from "../pages/Settings";
import NotFound from "../pages/NotFound";

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  // Email links land on these while a session is being established, so they
  // must stay reachable whether or not the user is signed in.
  { path: "/verify", element: <Verify /> },
  { path: "/reset-password", element: <ResetPassword /> },
  {
    element: <PublicOnlyRoute />,
    children: [
      { path: "/login", element: <Login /> },
      { path: "/signup", element: <Signup /> },
      { path: "/forgot-password", element: <ForgotPassword /> },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/dashboard", element: <Dashboard /> },
          { path: "/library", element: <Library /> },
          { path: "/lectures/new", element: <Upload /> },
          { path: "/lectures/:id/processing", element: <Processing /> },
          { path: "/lectures/:id", element: <Workspace /> },
          { path: "/search", element: <Search /> },
          { path: "/history", element: <History /> },
          { path: "/profile", element: <Profile /> },
          { path: "/settings", element: <Settings /> },
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
