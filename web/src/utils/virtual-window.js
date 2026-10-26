// 固定行高虚拟列表，边界统一夹紧；筛选后即使停留在旧滚动位置也不会越界。
export function virtualWindow(count, scrollTop, rowHeight = 34, viewport = 386, overscan = 6) {
  const visible = Math.ceil(viewport / rowHeight);
  const first = Math.min(Math.max(0, count - visible), Math.max(0, Math.floor(scrollTop / rowHeight)));
  const start = Math.max(0, first - overscan);
  const end = Math.min(count, first + visible + overscan);
  return { start, end, top: start * rowHeight, bottom: (count - end) * rowHeight };
}
