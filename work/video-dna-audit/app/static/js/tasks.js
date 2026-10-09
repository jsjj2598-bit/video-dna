// Background task center. The backend keeps task progress in memory and the
// UI polls only while this tab is visible, keeping the normal workspace quiet.
let taskTimer = null;

function escAttr(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\r?\n/g, ' ');
}

function taskLabel(stage) {
  const labels = {uploaded:'已接收',queued:'排队中',probe:'读取媒体',detect:'检测镜头',frames:'提取关键帧',audio:'分析音频',asr:'语音转写',describe:'生成描述',save:'保存结果',done:'已完成',error:'失败',cancelled:'已取消'};
  return labels[stage] || stage || '处理中';
}

async function loadTasks() {
  const list = document.getElementById('taskList');
  if (!list) return;
  try {
    const res = await fetch('/api/tasks');
    if (!res.ok) throw new Error('任务服务返回 ' + res.status);
    const data = await res.json();
    renderTasks(data.items || []);
  } catch (error) {
    list.innerHTML = '<div class="empty-state">任务读取失败：' + esc(error.message) + '</div>';
  }
  if (!taskTimer) taskTimer = setTimeout(() => { taskTimer = null; if (document.getElementById('tab-tasks')?.classList.contains('active')) loadTasks(); }, 2000);
}

function renderTasks(items) {
  const list = document.getElementById('taskList');
  if (!list) return;
  if (!items.length) { list.innerHTML = '<div class="empty-state">暂无后台任务。开始分析后，任务会显示在这里。</div>'; return; }
  list.innerHTML = items.map(item => {
    const pct = Math.max(0, Math.min(100, Number(item.pct || 0)));
    const terminal = !!item.done;
    const last = item.logs?.length ? item.logs[item.logs.length - 1].msg : '';
    const action = terminal && item.stage === 'done'
      ? '<button class="btn btn-sm" type="button" onclick="openTaskResult(\'' + escAttr(item.session_id) + '\')">打开结果</button>'
      : (!terminal ? '<button class="btn btn-sm btn-danger" type="button" onclick="cancelTask(\'' + escAttr(item.session_id) + '\')">取消</button>' : '');
    return '<div class="task-item ' + (item.stage === 'error' ? 'task-error' : '') + '">' +
      '<div class="task-item-head"><div><strong>' + esc(item.session_id) + '</strong><span class="task-stage">' + esc(taskLabel(item.stage)) + '</span></div><span class="task-percent">' + pct + '%</span></div>' +
      '<div class="task-progress"><span style="width:' + pct + '%"></span></div>' +
      '<div class="task-item-foot"><span>' + esc(item.error || last || '等待引擎更新') + '</span><span class="task-actions">' + action + '</span></div></div>';
  }).join('');
}

async function cancelTask(sessionId) {
  try {
    const res = await fetch('/api/analysis/' + encodeURIComponent(sessionId), {method:'DELETE'});
    if (!res.ok) throw new Error('取消失败（' + res.status + '）');
    toast('已请求取消任务', 'info');
    loadTasks();
  } catch (error) { toast('取消任务失败：' + error.message, 'error'); }
}

async function openTaskResult(sessionId) {
  try {
    const res = await fetch('/api/result/' + encodeURIComponent(sessionId));
    if (!res.ok) throw new Error('结果暂不可用');
    const data = await res.json();
    currentSessionId = sessionId;
    currentResult = data;
    if (typeof renderResult === 'function') renderResult(data, null, {history:true});
    switchTab('analyze', document.querySelector('.nav-item'));
  } catch (error) { toast('打开结果失败：' + error.message, 'error'); }
}
