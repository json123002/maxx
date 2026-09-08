<template>
  <a-config-provider :locale="zhCN" :theme="antdTheme">
    <router-view />
  </a-config-provider>
</template>

<script setup>
import { computed } from "vue";
import { theme } from "ant-design-vue";
import zhCN from "ant-design-vue/es/locale/zh_CN";
import { themeMode } from "./utils/theme";

// antd 组件跟随全站明暗主题
const antdTheme = computed(() => ({
  algorithm: themeMode.value === "light" ? theme.defaultAlgorithm : theme.darkAlgorithm,
}));
</script>
