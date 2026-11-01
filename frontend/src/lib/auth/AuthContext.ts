import { createContext } from "react";

import type { AuthConfig, Me } from "@/api/types";

export type AuthStatus = "loading" | "signedIn" | "signedOut";

export interface AuthState {
  status: AuthStatus;
  user: Me | null;
  /** Server sign-in options; null while loading or if the config call failed. */
  config: AuthConfig | null;
  /** Google redirect, or a new guest session when the server runs in guest mode. */
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);
