import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ChatPage } from "@/features/chat/ChatPage";
import { LandingPage } from "@/features/landing/LandingPage";
import { MarketPage } from "@/features/market/MarketPage";
import { GoalsPage } from "@/features/goals/GoalsPage";
import { ArticlePage } from "@/features/learn/ArticlePage";
import { LearnPage } from "@/features/learn/LearnPage";
import { PortfolioPage } from "@/features/portfolio/PortfolioPage";
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
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/goals" element={<GoalsPage />} />
          <Route path="/learn" element={<LearnPage />} />
          <Route path="/learn/:articleId" element={<ArticlePage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
