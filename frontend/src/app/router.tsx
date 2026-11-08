import { Navigate, createBrowserRouter } from "react-router-dom";
import { RootLayout } from "./layout/RootLayout";
import { GeneratePage } from "../pages/GeneratePage/GeneratePage";
import { HistoryPage } from "../pages/HistoryPage/HistoryPage";
import { ReferencePage } from "../pages/ReferencePage/ReferencePage";

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: "/", element: <Navigate to="/generate" replace /> },
      { path: "/generate", element: <GeneratePage /> },
      { path: "/history", element: <HistoryPage /> },
      { path: "/reference", element: <ReferencePage /> },
      { path: "/reference/:version", element: <ReferencePage /> },
    ],
  },
]);
