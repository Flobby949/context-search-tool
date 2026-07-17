import type { Order } from "../types/order";

export function loadOrders(source: { orders: Order[] }): Order[] {
  return source.orders;
}
