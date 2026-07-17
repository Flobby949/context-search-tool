import type { Order } from "../types/order";

export function useOrderStore(): { orders: Order[] } {
  return { orders: [] };
}
