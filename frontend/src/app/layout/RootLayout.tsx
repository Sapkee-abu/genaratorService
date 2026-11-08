import { Outlet } from "react-router-dom";
import { AppLayout } from "./AppLayout";

export function RootLayout() {
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  );
}
