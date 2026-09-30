import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import AuthProvider from "./auth/AuthProvider";
import { isSupabaseConfigured } from "./lib/supabase";
import ConfigurationError from "./pages/ConfigurationError";

export default function App() {
  if (!isSupabaseConfigured) return <ConfigurationError />;

  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
