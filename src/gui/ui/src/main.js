import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import { store } from "./store.js";

const app = createApp(App);
app.use(router);
app.provide("store", store);
app.mount("#app");
