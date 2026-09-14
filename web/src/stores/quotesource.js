/* ===== 当前生效的行情源(轻量 reactive store,不引 pinia)=====
   own: 自己启用中的行情源名;shared: 其他人公开的源名列表。
   全站数据来源标注共用:顶栏/home 刊头/flow 状态条/个股详情角标。 */
import { ref } from "vue";
import { api } from "../api/client";
import { getToken } from "../utils/token";

export const quoteSource = ref({ own: "", shared: [] });
let loaded = false;

export async function loadQuoteSource() {
  if (loaded || !getToken()) return;
  loaded = true;
  try {
    const d = await api("/api/quotesettings");
    const own = (d.rows || []).find((r) => r.enabled);
    quoteSource.value = { own: own ? own.name : "", shared: d.public || [] };
  } catch { /* 取不到就当没有,页面标注回落到默认数据源 */ }
}

// 登出时清掉,防止换账号后残留上一账号的来源标注
export function resetQuoteSource() {
  loaded = false;
  quoteSource.value = { own: "", shared: [] };
}

// 当前对「个股实时」生效的源描述(自己的优先,否则公共),没有则空串
export function activePersonalSource() {
  const s = quoteSource.value;
  if (s.own) return s.own;
  return s.shared.length ? s.shared[0] + "（公共）" : "";
}
