import { createRouter } from "vue-router";
import OrdersView from "../views/OrdersView.vue";

const routes = [
  { path: "/orders", component: OrdersView },
];

export default createRouter({ routes });
