import { loadOrders } from "../services/orderService";
import type { Order } from "../types/order";

export function OrdersPage() {
  const orders: Order[] = loadOrders();
  return <main>{orders.length}</main>;
}
