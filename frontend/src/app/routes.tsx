import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ChatPage } from "@/features/chat/ChatPage";
import { LandingPage } from "@/features/landing/LandingPage";
import { MarketPage } from "@/features/market/MarketPage";
import { ComingSoonPage } from "@/features/placeholders/ComingSoonPage";
import { ProfilePage } from "@/features/profile/ProfilePage";
import { RequireAuth } from "@/lib/auth/RequireAuth";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          {/* A layout route, so the page (and an answer mid-stream) survives /chat -> /chat/:id. */}
          <Route path="/chat" element={<ChatPage />}>
            <Route index element={null} />
            <Route path=":conversationId" element={null} />
          </Route>
          <Route
            path="/portfolio"
            element={<ComingSoonPage title="Portfolio" description="Enter or import holdings and see clear metrics." />}
          />
          <Route path="/market" element={<MarketPage />} />
          <Route
            path="/goals"
            element={<ComingSoonPage title="Goals" description="Project savings goals at your risk level." />}
          />
          <Route
            path="/learn"
            element={<ComingSoonPage title="Learn" description="Browse articles by topic and level." />}
          />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
