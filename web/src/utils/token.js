/* ===== 会话令牌存取(localStorage)===== */
const TOKEN_KEY = "ts-token";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
}
export function setToken(t) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch (e) {}
}
export function removeToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
}
