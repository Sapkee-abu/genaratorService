import type { ReactNode } from "react";
import { Header } from "../../components/layout/Header";
import { Navigation } from "../../components/layout/Navigation";
import "./AppLayout.css";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-layout">
      <Header />
      <Navigation />
      <main className="app-layout__content">{children}</main>
    </div>
  );
}
