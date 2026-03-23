import "./globals.css";
import type { ReactNode } from "react";
import MainNav from "@/components/main-nav";

export const metadata = {
  title: "MentorSeeker",
  description: "Mentor discovery and tracking MVP",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="bg-shapes" aria-hidden="true">
          <span className="shape shape-a" />
          <span className="shape shape-b" />
          <span className="shape shape-c" />
          <span className="shape shape-d" />
          <span className="shape shape-e" />
          <span className="shape shape-f" />
        </div>

        <main className="app-shell">
          <header className="app-topbar">
            <div className="app-brand">
              <div>
                <h1 className="brand-title">MentorSeeker</h1>
                <p className="brand-sub">导师探索、收藏管理与套磁进度一体化工作台</p>
              </div>
              <span className="brand-badge">MVP</span>
            </div>
            <MainNav />
          </header>
          {children}
        </main>
      </body>
    </html>
  );
}
