<template>
  <!-- <script>fake tag</script> -->
  <main>{{ orders.length }}</main>
</template>

<script setup lang="ts">
import { loadOrders } from "../services/orderService";
import { useOrderStore } from "../stores/orderStore";
import type { Order } from "../types/order";

const store = useOrderStore();
const orders: Order[] = loadOrders(store);
</script>
