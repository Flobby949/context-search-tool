import { createRouter } from "vue-router";
import ShadowView from "../views/ShadowView.vue";

{
  const createRouter = <T>(value: T): T => value;
  createRouter({ routes: [{ path: "/shadow", component: ShadowView }] });
}
