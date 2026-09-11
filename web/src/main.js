import { createApp } from "vue";
// 按需注册用到的组件（注册父组件会带上子组件，如 Layout→Sider/Header/Content）。
// 不再 .use(Antd) 全量注册——那会把整个组件库打进主包（1.5MB→按需后大幅缩小），
// 服务器带宽只有 1Mbps，首屏体积直接决定首页加载速度。
import {
  Button, Checkbox, ConfigProvider, Dropdown, Form, Input, Layout, Menu,
  Modal, Tooltip,
} from "ant-design-vue";
import "ant-design-vue/dist/reset.css";
import App from "./App.vue";
import router from "./router";
import { initTheme } from "./utils/theme";
import { initLayout } from "./utils/layout";
import "./assets/screener.css";

initTheme();
initLayout();

// 注:AdminView 的 Table/Select/Popconfirm/Radio 在该页面内按需引入,
// 管理页是懒加载路由,这样主包不背这些重组件。
const app = createApp(App);
for (const c of [Button, Checkbox, ConfigProvider, Dropdown, Form, Input,
                 Layout, Menu, Modal, Tooltip]) {
  app.use(c);
}
app.use(router).mount("#app");
