import { createBrowserRouter } from "react-router-dom";
import { OrdersPage } from "./pages/OrdersPage";

export const router = createBrowserRouter([
  { path: "/orders", element: <OrdersPage /> },
]);
