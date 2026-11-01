/** The six tabs from UI-01. */
export interface NavItem {
  to: string;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/chat", label: "Chat" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/market", label: "Market" },
  { to: "/goals", label: "Goals" },
  { to: "/learn", label: "Learn" },
  { to: "/profile", label: "Profile" },
];
