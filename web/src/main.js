import { createApp } from "vue";
import Antd from "ant-design-vue";
import "ant-design-vue/dist/reset.css";
import App from "./App.vue";
import router from "./router";
import { initTheme } from "./utils/theme";
import "./assets/screener.css";

initTheme();

createApp(App).use(Antd).use(router).mount("#app");
