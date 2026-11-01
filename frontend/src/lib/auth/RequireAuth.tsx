import { Navigate, Outlet } from "react-router-dom";

import { LoadingState } from "@/components/feedback/LoadingState";

import { useAuth } from "./useAuth";

/** Route guard: signed-out visitors only ever see the landing page (AU-01). */
export function RequireAuth() {
  const { status } = useAuth();
  if (status === "loading") return <LoadingState label="Checking your session" />;
  if (status === "signedOut") return <Navigate to="/" replace />;
  return <Outlet />;
}
