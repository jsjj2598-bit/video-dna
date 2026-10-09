// ── History ──
function getHistory() { try { return JSON.parse(localStorage.getItem('vdna_history'))||[]; } catch { return []; } }
function addHistory(name, result) {
  const h = getHistory();
  h.unshift({id:Date.now(), name, time:new Date().toLocaleString('zh-CN'), total_shots:result.meta?.total_shots||0, duration:result.meta?.duration||0, bpm:result.audio?.tempo_bpm||null, summary:result.summary||''});
  if (h.length > 30) h.length = 30;
  localStorage.setItem('vdna_history', JSON.stringify(h));
}
async function renderHistory() {
  const el = document.getElementById('historyList');
  let serverItems = [];
  try {
    const res = await fetch('/api/history');
    if (res.ok) serverItems = (await res.json()).items || [];
  } catch (_) {}
  let h = getHistory();
  if (!h.length && !serverItems.length) { el.innerHTML = '<div class="history-empty">暂无历史记录，去分析一支视频吧 🎬</div>'; return; }
  // 去重：本地记录若已被服务端记录（同名 + 同一分钟内），不再重复展示
  const serverKeys = new Set(serverItems.map(i => {
    const t = new Date(String(i.time).replace(' ', 'T'));
    return i.name + '|' + (isNaN(t.getTime()) ? i.time : Math.floor(t.getTime() / 60000));
  }));
  h = h.filter(i => {
    const t = new Date(i.time);
    const key = i.name + '|' + (isNaN(t.getTime()) ? i.time : Math.floor(t.getTime() / 60000));
    return !serverKeys.has(key);
  });
  const rows = [];
  serverItems.forEach(i => {
    rows.push(`
      <div class="history-item" onclick="openHistory('${i.session_id}')" title="点击回看完整分析结果">
        <span class="hi-ico">🎬</span>
        <span class="hi-name">${esc(i.name)}</span>
        <span class="hi-count">${i.total_shots} 镜头${i.has_video ? ' · 🎥' : ''}</span>
        <span class="hi-time">${i.time}</span>
        <span class="hi-del" onclick="event.stopPropagation();delServerHistory('${i.session_id}')">×</span>
      </div>
    `);
  });
  if (!serverItems.length && h.length) {
    rows.push('<div class="empty-state" style="margin:10px 0">本地旧记录仅含摘要，重新分析后可完整回看</div>');
  }
  h.forEach(i => {
    rows.push(`
      <div class="history-item" onclick="toast('⚠️ 该旧记录仅含摘要，请重新上传分析后可完整回看','info')">
        <span class="hi-ico">📋</span>
        <span class="hi-name">${esc(i.name)}</span>
        <span class="hi-count">${i.total_shots} 镜头</span>
        <span class="hi-time">${i.time}</span>
        <span class="hi-del" onclick="event.stopPropagation();delHistory(${i.id})">×</span>
      </div>
    `);
  });
  el.innerHTML = rows.join('');
}
function delHistory(id) {
  let h = getHistory();
  h = h.filter(i => i.id !== id);
  localStorage.setItem('vdna_history', JSON.stringify(h));
  renderHistory();
  toast('🗑️ 已删除', 'info');
}
async function delServerHistory(sid) {
  if (!confirm('删除该历史记录？')) return;
  try {
    const res = await fetch('/api/history/' + sid, { method: 'DELETE' });
    if (!res.ok) throw new Error(res.statusText);
    renderHistory();
    toast('🗑️ 已删除', 'info');
  } catch(e) { toast('❌ 删除失败: '+e.message, 'error'); }
}
async function clearHistory() {
  if (!confirm('清空全部历史记录？')) return;
  try { await fetch('/api/history', { method: 'DELETE' }); } catch (_) {}
  localStorage.removeItem('vdna_history');
  renderHistory();
  toast('🗑️ 全部清空', 'info');
}
async function openHistory(sid) {
  showP('正在加载历史记录...', '');
  try {
    const res = await fetch('/api/history/' + sid);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    hideP();
    currentResult = data;
    currentCuts = null; currentTemplateName = ''; appliedVideoFile = null;
    currentSessionId = data._session_id || sid;
    renderResult(data, null, { history: true });
    switchTab('analyze', document.querySelector('.nav-item'));
    toast('📋 已载入历史：' + (data._source_file || '视频'), 'success');
  } catch (err) {
    hideP();
    toast('❌ ' + err.message, 'error');
  }
}
function esc(s) { if (s === null || s === undefined) return ''; const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }

