import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, type ReactNode } from "react";

import { ApiError } from "@/api/client";
import { GOOGLE_LOGIN_URL, getAuthConfig, guestLogin, logout } from "@/api/endpoints/auth";
import { getMe } from "@/api/endpoints/me";
import { queryKeys } from "@/api/queryKeys";

import { AuthContext, type AuthState } from "./AuthContext";
import { redirectTo } from "./navigation";

/**
 * Session state comes from GET /me: the HttpOnly cookie is invisible to JavaScript,
 * so "am I signed in?" is answered by the backend (AU-02).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: getMe,
    retry: (count, error) => !(error instanceof ApiError && error.isUnauthenticated) && count < 2,
    staleTime: 5 * 60_000,
  });
  const authConfig = useQuery({
    queryKey: queryKeys.authConfig,
    queryFn: getAuthConfig,
    staleTime: Infinity,
  });
  const config = authConfig.data ?? null;

  const signIn = useCallback(async () => {
    if (config?.guest_enabled) {
      await guestLogin();
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
      return;
    }
    redirectTo(GOOGLE_LOGIN_URL);
  }, [config, queryClient]);

  const signOut = useCallback(async () => {
    try {
      await logout();
    } finally {
      // Drop every other user's-data query, then mark the session as signed out.
      const keep = new Set<unknown>([queryKeys.me[0], queryKeys.authConfig[0]]);
      queryClient.removeQueries({ predicate: (query) => !keep.has(query.queryKey[0]) });
      queryClient.setQueryData(queryKeys.me, null);
    }
  }, [queryClient]);

  const value = useMemo<AuthState>(() => {
    if (me.isPending) return { status: "loading", user: null, config, signIn, signOut };
    const user = me.data ?? null;
    return { status: user ? "signedIn" : "signedOut", user, config, signIn, signOut };
  }, [me.isPending, me.data, config, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
