/* ===== 龙虎榜接口封装 ===== */
import { api } from "../api/client";

export const fetchLhbDates = () => api("/api/lhb/dates");
export const fetchLhbDaily = (date) =>
  api("/api/lhb/daily?" + new URLSearchParams({ date }));
export const fetchLhbStockSeats = (code, date) =>
  api(`/api/lhb/stock/${code}/seats?` + new URLSearchParams({ date }));
export const fetchLhbSeats = ({ kw = "", sort = "win_rate", minApps = 3 } = {}) =>
  api("/api/lhb/seats?" + new URLSearchParams({ kw, sort, min_apps: minApps }));
export const fetchLhbSeat = (name) =>
  api("/api/lhb/seat/" + encodeURIComponent(name));
