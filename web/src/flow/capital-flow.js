/* ===== 板块资金雷达 数据层(移植自 capital-flow-pro.html)=====
   东方财富延迟行情 JSONP 直连;行情快照/异动判断在前端完成 */
import { jsonp } from "../utils/jsonp";

const API_HOST = "https://push2delay.eastmoney.com";

/* 概念板块默认剔除的统计类篮子关键词 */
const BASKET_WORDS = [
  "融资融券", "富时", "罗素", "MSCI", "标普", "道琼斯", "股通", "北向", "北上",
  "大盘", "中盘", "小盘", "沪深300", "上证50", "中证", "创业板综", "科创板",
  "含H股", "含B股", "重仓", "预盈", "预增", "预减", "预亏", "高送转", "破净",
  "国企改革", "央企", "标准普尔", "权重", "深成", "HS300", "沪深", "深证", "上证",
  "全指", "成份", "成分", "百元股", "热股", "振幅", "昨日", "涨停", "跌停",
  "连板", "近端次新", "次新股", "龙头", "白马股", "蓝筹", "风格", "趋势股",
  "茅指数", "组合", "微盘", "ST股", "低价", "举牌", "红利", "扭亏", "季报",
  "年报", "中报", "百日新高", "创新高", "新高", "高市净率", "低市净率",
  "高市盈率", "低市盈率", "价值股", "成长股", "高价股", "低价股",
];

/* 行业板块白名单(东财行业分类,原始名带 Ⅱ 后缀) */
export const INDUSTRY_ALLOW = new Set([
  "IT服务Ⅱ", "一般零售", "专业工程", "专业服务", "专业连锁Ⅱ", "专用设备", "个护用品",
  "中药Ⅱ", "乘用车", "互联网电商", "休闲食品", "体育Ⅱ", "保险Ⅱ", "元件", "光学光电子",
  "其他家电Ⅱ", "其他电子Ⅱ", "养殖业", "军工电子Ⅱ", "农业综合Ⅱ", "农产品加工",
  "农化制品", "冶钢原料", "出版", "动物保健Ⅱ", "包装印刷", "化妆品", "化学制品",
  "化学制药", "化学原料", "化学纤维", "医疗器械", "医疗服务", "医疗美容", "医药商业",
  "半导体", "厨卫电器", "商用车", "地面兵装Ⅱ", "基础建设", "塑料", "多元金融",
  "家居用品", "家电零部件Ⅱ", "小家电", "工程咨询服务Ⅱ", "工程机械", "广告营销",
  "影视院线", "房地产开发", "房地产服务", "房屋建设Ⅱ", "摩托车及其他", "教育",
  "数字媒体", "旅游及景区", "旅游零售Ⅱ", "普钢", "服装家纺", "林业Ⅱ", "橡胶",
  "水泥", "汽车服务", "汽车零部件", "油服工程", "油气开采Ⅱ", "消费电子", "渔业",
  "游戏Ⅱ", "炼化及贸易", "焦炭Ⅱ", "煤炭开采", "照明设备Ⅱ", "燃气Ⅱ", "物流",
  "特钢Ⅱ", "环保设备Ⅱ", "环境治理", "玻璃玻纤", "生物制品", "电力",
  "电子化学品Ⅱ", "电视广播Ⅱ", "白色家电", "白酒Ⅱ", "种植业", "纺织制造",
  "综合Ⅱ", "自动化设备", "航天装备Ⅱ", "航海装备Ⅱ", "航空机场", "航空装备Ⅱ",
  "航运港口", "装修建材", "装修装饰Ⅱ", "计算机设备", "证券Ⅱ", "调味发酵品Ⅱ",
  "贸易Ⅱ", "轨交设备Ⅱ", "软件开发", "通信服务", "通信设备", "通用设备", "造纸",
  "酒店餐饮", "铁路公路", "非白酒", "非金属材料Ⅱ", "食品加工", "饮料乳品",
  "饰品", "饲料", "黑色家电", "电力设备", "有色金属", "机器人", "银行",
]);

/* ===== 格式化 ===== */
export const cleanName = (name) => String(name || "").replace(/[ⅡⅢ]+$/g, "");
export const pad2 = (n) => (n < 10 ? "0" + n : String(n));
export const timeText = (d) => `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
export function fmtYi(v, digits = 1) {
  if (!Number.isFinite(v)) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(digits) + " 亿";
}
export function fmtYiShort(v) {
  if (!Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  const digits = abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
  return (v >= 0 ? "+" : "") + v.toFixed(digits) + "亿";
}

/* ===== 交易时段 ===== */
export function marketState(date = new Date()) {
  const day = date.getDay();
  const minutes = date.getHours() * 60 + date.getMinutes();
  const trading = (minutes >= 570 && minutes <= 690) || (minutes >= 780 && minutes <= 900);
  if (day === 0 || day === 6) return { text: "周末休市", cls: "pause" };
  if (trading) return { text: "交易时段", cls: "live" };
  if (minutes > 690 && minutes < 780) return { text: "午间休市", cls: "pause" };
  if (minutes < 570) return { text: "盘前时段", cls: "" };
  return { text: "已收盘", cls: "" };
}

/* ===== 过滤 ===== */
export const isBasket = (name) => BASKET_WORDS.some((w) => name.includes(w));

/* ===== 行情接口 ===== */
// 板块列表:主力净额(f62)降序,分页拉全,value 单位换算为亿
export async function fetchAllSectors(industry) {
  const fs = industry ? "m:90+t:2" : "m:90+t:3";
  const merged = new Map();
  for (let page = 1; page <= 8; page += 1) {
    const url = `${API_HOST}/api/qt/clist/get?fid=f62&po=1&pz=100&pn=${page}` +
      `&np=1&fltt=2&invt=2&fs=${encodeURIComponent(fs)}&fields=f12,f14,f62`;
    const result = await jsonp(url);
    const diff = result?.data?.diff;
    if (!Array.isArray(diff) || !diff.length) break;
    for (const row of diff) {
      const value = Number(row?.f62);
      if (row?.f12 && row?.f14 && Number.isFinite(value)) {
        merged.set(row.f12, {
          code: String(row.f12), name: cleanName(row.f14), rawName: String(row.f14), value: value / 1e8,
        });
      }
    }
    if (diff.length < 100) break;
  }
  return [...merged.values()].sort((a, b) => b.value - a.value);
}

// 板块分钟级累计资金流:[[hh:mm, 亿], ...]
export async function fetchIntraday(code) {
  const url = `${API_HOST}/api/qt/stock/fflow/kline/get?lmt=0&klt=1` +
    `&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65` +
    `&secid=90.${encodeURIComponent(code)}`;
  const result = await jsonp(url);
  const lines = result?.data?.klines;
  if (!Array.isArray(lines)) return [];
  return lines.map((line) => {
    const parts = String(line).split(",");
    const raw = parts[0] || "";
    const label = raw.includes(" ") ? raw.split(" ").pop().slice(0, 5) : raw.slice(-5);
    const value = Number(parts[1]);
    return Number.isFinite(value) ? [label, value / 1e8] : null;
  }).filter(Boolean);
}

// 批量拉分钟线,按最新累计值降序;单个失败不拖垮整体
export async function loadSeries(sectors) {
  const results = await Promise.all(sectors.map((sector) =>
    fetchIntraday(sector.code)
      .then((series) => ({ name: sector.name, code: sector.code, series, current: sector.value }))
      .catch(() => ({ name: sector.name, code: sector.code, series: [], current: sector.value }))
  ));
  return results
    .filter((item) => item.series.length)
    .sort((a, b) => {
      const av = a.series.length ? a.series[a.series.length - 1][1] : a.current;
      const bv = b.series.length ? b.series[b.series.length - 1][1] : b.current;
      return bv - av;
    });
}
