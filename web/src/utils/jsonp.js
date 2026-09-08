/* ===== JSONP(仅个股分析弹窗的K线/资金流直连东财/腾讯/新浪使用;行情列表走后端 API)===== */
let cbSeq = 0;

export function jsonp(url) {
  return new Promise((resolve, reject) => {
    const cb = "emCb" + cbSeq++;
    const s = document.createElement("script");
    const timer = setTimeout(() => { cleanup(); reject(new Error("timeout")); }, 12000);
    function cleanup() { clearTimeout(timer); delete window[cb]; s.remove(); }
    window[cb] = (d) => { cleanup(); resolve(d); };
    s.onerror = () => { cleanup(); reject(new Error("network")); };
    s.src = url + (url.includes("?") ? "&" : "?") + "cb=" + cb;
    document.head.appendChild(s);
  });
}

// 加载 "var NAME=(...)" 形式的接口(新浪 JSONP 变体):赋全局变量而非回调
// 安全说明:新浪被拦截时返回的 HTML/注释脚本不会执行跳转,仅解析失败 → reject
export function jsonpVar(url, varName) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    const timer = setTimeout(() => { cleanup(); reject(new Error("timeout")); }, 12000);
    function cleanup() {
      clearTimeout(timer);
      try { delete window[varName]; } catch (e) { window[varName] = undefined; }
      s.remove();
    }
    s.onerror = () => { cleanup(); reject(new Error("network")); };
    s.onload = () => {
      const d = window[varName];
      cleanup();
      d === undefined ? reject(new Error("empty")) : resolve(d);
    };
    s.src = url;
    document.head.appendChild(s);
  });
}
