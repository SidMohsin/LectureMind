import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Footer from "./Footer";
import "./AppShell.css";

/**
 * Shared authenticated application shell (navbar + footer) used by every
 * product page. Public/auth pages render without this shell.
 */
export default function AppShell() {
  return (
    <div className="app-shell">
      <Navbar />
      <main className="app-shell__main">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
