// ── Analyze ──
async function uploadFile(f) {
  if (!f) return;
  lastOperationRetry = () => uploadFile(f);
  document.getElementById('resultArea').innerHTML = '';
  currentCuts = null; currentTemplateName = ''; appliedVideoFile = null;
  const maxSize = 2 * 1024 * 1024 * 1024;
  if (f.size > maxSize) { toast('❌ 文件过大，最大 2GB', 'error'); return; }

  // 生成会话 ID 用于轮询思考过程
  currentSessionId = 'sid-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);

  const thinkBox = document.getElementById('thinkLogs');
  if (thinkBox) { thinkBox.innerHTML = ''; thinkBox.style.display = 'none'; }
  const analyzeBtn = document.getElementById('analyzeBtn');
  if (analyzeBtn) analyzeBtn.disabled = true;

  showP('正在上传...', f.name);
  if (typeof markCurrentAsset === 'function') markCurrentAsset('analyzing');
  updateP(10);
  addThink('upload', 5, '上传视频：' + f.name);

  const fd = new FormData();
  fd.append('file', f);
  fd.append('session_id', currentSessionId);
  const s = getSettings();
  const keys = getSessionKeys();
  const params = new URLSearchParams();
  if (s.detector) params.set('detector', s.detector);
  if (s.backend) params.set('backend', s.backend);
  if (keys.openai_key) fd.append('openai_key', keys.openai_key);
  if (keys.qwen_key) fd.append('qwen_key', keys.qwen_key);

  try {
    const res = await fetch('/api/analyze?'+params.toString(), { method:'POST', body:fd });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || res.statusText); }
    await waitAnalysis();
    const data = await fetch('/api/result/' + currentSessionId).then(r => r.json());
    currentResult = data;
    data._session_id = currentSessionId;
    if (typeof saveProjectResultSnapshot === 'function') saveProjectResultSnapshot(data);
    addHistory(f.name, data);
    updateP(100, '分析完成！');
    setTimeout(hideP, 500);
    renderResult(data, f);
    if (typeof markCurrentAsset === 'function') markCurrentAsset('done');
    const activePanel = document.querySelector('.tab-panel.active');
    const onAnalyzeTab = activePanel && activePanel.id === 'tab-analyze';
    toast('✅ 分析完成！共 ' + (data.meta?.total_shots||0) + ' 个镜头' + (onAnalyzeTab ? '' : '，已可在「视频分析」页查看结果'), 'success', 5000);
    return true;
  } catch (err) {
    if (typeof markCurrentAsset === 'function') markCurrentAsset('failed');
    hideP();
    if (typeof showErrorPanel === 'function') showErrorPanel('分析失败', '请检查媒体文件、FFmpeg/Whisper 配置后重试。', err, '分析');
    toast('❌ ' + err.message, 'error');
    return false;
  } finally {
    if (analyzeBtn) analyzeBtn.disabled = false;
  }
}

async function analyzeDesktopPath(filePath) {
  if (!window.electronAPI || !window.electronAPI.analyzePath) return;
  lastOperationRetry = () => analyzeDesktopPath(filePath);
  const filename = String(filePath).split(/[\\/]/).pop() || 'video';
  if (typeof projectAddAssetPath === 'function') projectAddAssetPath(filePath);
  document.getElementById('resultArea').innerHTML = '';
  currentCuts = null; currentTemplateName = ''; appliedVideoFile = null;
  currentSessionId = 'sid-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  const thinkBox = document.getElementById('thinkLogs');
  if (thinkBox) { thinkBox.innerHTML = ''; thinkBox.style.display = 'none'; }
  const analyzeBtn = document.getElementById('analyzeBtn');
  if (analyzeBtn) analyzeBtn.disabled = true;
  showP('正在流式上传...', filename);
  if (typeof markCurrentAsset === 'function') markCurrentAsset('analyzing');
  addThink('upload', 5, '上传视频：' + filename);
  const settings = getSettings();
  const keys = getSessionKeys();
  try {
    const response = await window.electronAPI.analyzePath(filePath, {
      session_id: currentSessionId,
      detector: settings.detector || 'content',
      backend: settings.backend || 'auto',
      openai_key: keys.openai_key || '',
      qwen_key: keys.qwen_key || '',
    });
    currentSessionId = response.session_id || currentSessionId;
    await waitAnalysis();
    const resultResponse = await fetch('/api/result/' + currentSessionId);
    const data = await resultResponse.json();
    if (!resultResponse.ok) throw new Error(data.detail || resultResponse.statusText);
    currentResult = data;
    data._session_id = currentSessionId;
    if (typeof saveProjectResultSnapshot === 'function') saveProjectResultSnapshot(data);
    addHistory(filename, data);
    updateP(100, '分析完成！');
    setTimeout(hideP, 500);
    renderResult(data, null);
    if (typeof markCurrentAsset === 'function') markCurrentAsset('done');
    toast('✅ 分析完成！共 ' + (data.meta?.total_shots || 0) + ' 个镜头', 'success', 5000);
  } catch (error) {
    if (typeof markCurrentAsset === 'function') markCurrentAsset('failed');
    hideP();
    if (typeof showErrorPanel === 'function') showErrorPanel('分析失败', '原始素材和已有历史记录不会被删除，可以修复配置后重新运行。', error, '分析');
    toast('❌ ' + error.message, 'error');
  } finally {
    if (analyzeBtn) analyzeBtn.disabled = false;
  }
}

// ── 思考过程（任务3：分析时展示 AI 推理日志） ──
let _thinkTimer = null;
function addThink(stage, pct, msg, state) {
  const box = document.getElementById('thinkLogs');
  if (!box) return;
  box.style.display = 'block';
  const row = document.createElement('div');
  row.className = 'think-log ' + (state || '') + (stage === 'done' ? ' done' : '') + (stage === 'error' ? ' error' : '');
  row.innerHTML = '<span class="tl-time">' + new Date().toLocaleTimeString('zh-CN') + '</span><span class="tl-stage">' + esc(stage) + '</span><span class="tl-msg">' + esc(msg) + '</span>';
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}
function setCurrentThink(stage, msg) {
  const box = document.getElementById('thinkLogs');
  if (!box) return;
  const rows = box.querySelectorAll('.think-log');
  rows.forEach(r => { r.classList.remove('current'); if (r.dataset.stage === 'done') r.classList.remove('current'); });
  const row = document.createElement('div');
  row.className = 'think-log current';
  row.dataset.stage = stage;
  row.innerHTML = '<span class="tl-time">' + new Date().toLocaleTimeString('zh-CN') + '</span><span class="tl-stage">' + esc(stage) + '</span><span class="tl-msg">' + esc(msg) + '</span>';
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}
async function waitAnalysis() {
  return new Promise((resolve, reject) => {
    let lastPct = -1;
    let failStreak = 0;
    let elapsed = 0;
    const poll = async () => {
      elapsed += 800;
      if (elapsed > 45 * 60 * 1000) { reject(new Error('分析超时（45 分钟），请重试')); return; }
      try {
        const res = await fetch('/api/progress/' + currentSessionId);
        if (!res.ok) { if (++failStreak > 5) { reject(new Error('进度服务不可用，请刷新页面重试')); return; } setTimeout(poll, 800); return; }
        failStreak = 0;
        const p = await res.json();
        const pct = p.pct || 0;
        if (pct !== lastPct || p.stage === 'done' || p.stage === 'error') {
          lastPct = pct;
          updateP(pct, '正在分析...', p.logs && p.logs.length ? p.logs[p.logs.length - 1].msg : '');
          if (p.logs && p.logs.length) {
            const box = document.getElementById('thinkLogs');
            if (box) {
              // 按日志行数对齐渲染（每次分析前 thinkLogs 已清空）
              const existing = box.querySelectorAll('.think-log').length;
              const fresh = p.logs.slice(existing);
              fresh.forEach(l => {
                const row = document.createElement('div');
                row.className = 'think-log ' + (l.stage === 'done' ? 'done' : '') + (l.stage === 'error' ? 'error' : '');
                row.innerHTML = '<span class="tl-time">' + esc(l.t) + '</span><span class="tl-stage">' + esc(l.stage) + '</span><span class="tl-msg">' + esc(l.msg) + '</span>';
                box.appendChild(row);
              });
              box.scrollTop = box.scrollHeight;
            }
          }
        }
        if (p.done) {
          if (p.stage === 'error' || p.stage === 'cancelled') reject(new Error(p.stage === 'cancelled' ? '分析已取消' : (p.logs && p.logs.length ? p.logs[p.logs.length - 1].msg : '分析失败')));
          else resolve();
          return;
        }
        setTimeout(poll, 800);
      } catch (e) { if (++failStreak > 5) { reject(new Error('进度服务不可用，请刷新页面重试')); return; } setTimeout(poll, 800); }
    };
    poll();
  });
}

async function cancelCurrentAnalysis() {
  if (!currentSessionId) { toast('没有可取消的分析任务', 'info'); return; }
  try {
    const res = await fetch('/api/analysis/' + encodeURIComponent(currentSessionId), { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    toast('已取消分析，正在清理临时文件', 'info');
    hideP();
  } catch (error) {
    toast('取消失败：' + error.message, 'error');
  }
}

// ── 模板套用：自己的视频按示例视频的节奏生成剪辑方案 ──
function pickTemplateVideo() {
  document.getElementById('templateInput').click();
}
document.getElementById('templateInput').addEventListener('change', () => {
  const f = document.getElementById('templateInput').files[0];
  const tplId = document.getElementById('templateInput').dataset.tpl;
  document.getElementById('templateInput').dataset.tpl = '';
  document.getElementById('templateInput').value = '';
  if (f) {
    if (tplId) applyAiTemplate(f, tplId);
    else applyTemplate(f);
  }
});

async function applyAiTemplate(f, tplId) {
  showP('正在上传你的视频...', f.name);
  updateP(10);
  const fd = new FormData();
  fd.append('file', f);
  fd.append('template', tplId);
  const s = getSettings();
  const params = new URLSearchParams();
  if (s.detector) params.set('detector', s.detector);
  if (s.backend) params.set('backend', s.backend);
  try {
    updateP(20, '正在分析你的视频结构...');
    const res = await fetch('/api/ai/apply?' + params.toString(), { method: 'POST', body: fd });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
    const data = await res.json();
    updateP(90, '正在生成剪辑方案...');
    currentResult = data.analysis;
    currentSessionId = data.analysis._session_id || null;
    currentCuts = data.cut_plan.cuts;
    currentTemplateName = data.template ? data.template.name : '节奏模板';
    appliedVideoFile = f;
    updateP(100, '完成！');
    setTimeout(hideP, 500);
    renderResult(data.analysis, f, { cutPlan: data.cut_plan });
    toast('✅ 模板已套用：' + (data.template ? data.template.name : '') + ' · ' + data.cut_plan.total + ' 个镜头 · ' + data.cut_plan.beat_aligned_count + ' 个卡点', 'success');
  } catch (err) {
    hideP();
    toast('❌ ' + err.message, 'error');
  }
}

async function applyTemplate(f) {
  if (!currentResult || !currentResult.shots || !currentResult.shots.length) {
    toast('❌ 请先上传并分析一支示例视频', 'error');
    return;
  }
  showP('正在上传你的视频...', f.name);
  updateP(10);
  const fd = new FormData();
  fd.append('file', f);
  fd.append('template', JSON.stringify(currentResult));
  const s = getSettings();
  const params = new URLSearchParams();
  if (s.detector) params.set('detector', s.detector);
  if (s.backend) params.set('backend', s.backend);
  try {
    updateP(20, '正在分析你的视频结构...');
    const res = await fetch('/api/template/apply?' + params.toString(), { method: 'POST', body: fd });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
    const data = await res.json();
    updateP(90, '正在生成剪辑方案...');
    currentResult = data.analysis;
    currentSessionId = data.analysis._session_id || null;
    currentCuts = data.cut_plan.cuts;
    currentTemplateName = currentResult.meta?.source_file || '示例视频';
    appliedVideoFile = f;
    updateP(100, '完成！');
    setTimeout(hideP, 500);
    renderResult(data.analysis, f, { cutPlan: data.cut_plan });
    toast('✅ 剪辑方案已生成：' + data.cut_plan.total + ' 个镜头 · ' + data.cut_plan.beat_aligned_count + ' 个卡点', 'success');
  } catch (err) {
    hideP();
    toast('❌ ' + err.message, 'error');
  }
}

// ── 下载剪映草稿（任务5/7：剪映工程文件夹格式，含视频；任务6：自定义下载目录） ──
async function downloadDraft() {
  if (!currentCuts || !currentCuts.length) { toast('❌ 请先套用模板生成剪辑方案', 'error'); return; }
  try {
    toast('⏳ 正在生成剪映草稿...', 'info');
    const s = getSettings();
    const body = { project_name: 'VideoDNA剪辑方案', cuts: currentCuts };
    if (currentSessionId) body.session_id = currentSessionId;
    if (s.download_dir) body.download_dir = s.download_dir;
    const res = await fetch('/api/draft/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
    const data = await res.json();
    showDraftHelp(data.path);
  } catch (err) {
    toast('❌ ' + err.message, 'error');
  }
}

function showDraftHelp(folderPath) {
  const path = folderPath || '（下载目录）';
  const help = [
    '📦 剪映草稿已生成（剪映工程文件格式，非压缩包）：',
    '',
    '保存位置：',
    path,
    '',
    '草稿文件夹内已包含：draft_content.json（时间线）、draft_meta_info.json（元信息）、draft_cover.jpg（封面）以及视频素材副本，可直接打开。',
    '',
    '使用步骤：',
    '1. 打开剪映专业版 → 设置 → 全局设置 → 查看「草稿位置」',
    '   默认：%LOCALAPPDATA%\\JianyingPro\\User Data\\Projects\\com.lveditor.draft\\',
    '2. 把整个「VideoDNA剪辑方案」文件夹复制到该目录',
    '3. 重启剪映（或刷新草稿列表），即可打开草稿查看剪辑方案',
  ].join('\n');
  const modal = document.getElementById('draftHelpModal') || (() => {
    const div = document.createElement('div');
    div.id = 'draftHelpModal';
    div.className = 'modal-overlay active';
    div.innerHTML = '<div class="modal"><div class="modal-head"><h3>📦 剪映草稿已生成</h3><button class="modal-x" onclick="this.closest(\'.modal-overlay\').remove()">×</button></div><div class="modal-body"><pre id="draftHelpText" style="white-space:pre-wrap;line-height:1.9;color:var(--fg-2);font-size:13px;margin:0"></pre></div><div class="modal-foot"><button class="btn" data-folder="' + encodeURIComponent(folderPath || '') + '" id="draftOpenBtn">📁 打开文件夹</button><button class="btn btn-primary" onclick="this.closest(\'.modal-overlay\').remove()">知道了</button></div></div>';
    document.body.appendChild(div);
    const openBtn = div.querySelector('#draftOpenBtn');
    if (openBtn) openBtn.addEventListener('click', () => {
      try { openDraftFolder(decodeURIComponent(openBtn.dataset.folder)); } catch (_) { toast('⚠️ 请手动打开目录', 'info'); }
    });
    return div;
  })();
  modal.classList.add('active');
  modal.querySelector('#draftHelpText').textContent = help;
}

function openDraftFolder(path) {
  if (!path) return;
  if (window.electronAPI && window.electronAPI.showInFolder) {
    window.electronAPI.showInFolder(path);
  } else {
    toast('⚠️ 请手动打开目录：' + path, 'info', 6000);
  }
}

// ── Render ──
function renderResult(d, file, opts) {
  opts = opts || {};
  let cutPlan = opts.cutPlan || null;
  const m = d.meta || {};
  const a = d.audio || {};
  const shots = d.shots || [];
  const sr = a.speech_regions || [];
  const palette = ['#6d5df6','#4f7dff','#38bdf8','#34d399','#fbbf24','#f472b6','#22d3ee','#a78bfa'];
  const total = m.duration || 1;
  const frameBase = d._frame_base || (d._session_id ? '/api/sessions/' + d._session_id + '/frames/' : '/api/frames/');

  const sceneTypes = {}; let faceTotal=0, emotions={}, described=0;
  shots.forEach(s => {
    if (s.scene_type) sceneTypes[s.scene_type] = (sceneTypes[s.scene_type]||0)+1;
    faceTotal += s.face_count||0;
    if (s.emotion) emotions[s.emotion] = (emotions[s.emotion]||0)+1;
    if (s.content) described++;
  });
  const sceneLabels = {dialogue:'对话',action:'动作',establishing:'交代',closeup:'特写',emotional:'情绪',transition:'过渡'};
  const sceneIcons = {dialogue:'💬',action:'💥',establishing:'🌄',closeup:'🔍',emotional:'❤️',transition:'🌀'};
  let topEmotion = '';
  if (Object.keys(emotions).length) topEmotion = Object.entries(emotions).sort((a,b)=>b[1]-a[1])[0][0];

  let sceneHtml = '';
  ['dialogue','action','establishing','closeup','emotional','transition'].forEach(st => {
    if (sceneTypes[st]) sceneHtml += `<div class="scene-card"><span class="icon">${sceneIcons[st]||'🎬'}</span><div class="cnt">${sceneTypes[st]}</div><div class="lbl">${sceneLabels[st]||st}</div></div>`;
  });

  let videoUrl = '';
  if (file) videoUrl = URL.createObjectURL(file);
  else if (d._video_url) videoUrl = d._video_url;
  // 历史记录：恢复保存的剪辑方案（任务4 完整回看）
  if (!cutPlan && d._cut_plan && d._cut_plan.cuts && d._cut_plan.cuts.length) {
    cutPlan = d._cut_plan;
  }

  document.getElementById('resultArea').innerHTML = `
    ${videoUrl ? `<div class="video-mini video-card"><video id="videoEl" src="${encodeURI(videoUrl)}" controls preload="metadata" poster="${frameBase}${encodeURIComponent(shots[0]?.keyframe||'')}"></video><div class="vm-bar"><span class="vm-title">🎬 ${esc(d._source_file || '视频')}</span><span>${m.duration ? m.duration.toFixed(1)+'s' : ''} · ${esc(m.resolution||'')}</span></div></div>` : ''}

    <div class="stats-row">
      <div class="stat-tile"><div class="num">${m.total_shots||0}</div><div class="lbl">🎬 镜头总数</div></div>
      <div class="stat-tile"><div class="num green">${m.avg_shot_duration?(m.avg_shot_duration).toFixed(2)+'s':'-'}</div><div class="lbl">📏 平均时长</div></div>
      <div class="stat-tile"><div class="num orange">${a.tempo_bpm??'-'}</div><div class="lbl">🎵 BPM</div></div>
      <div class="stat-tile"><div class="num">${a.beat_count||0}</div><div class="lbl">🥁 节拍点</div></div>
      <div class="stat-tile"><div class="num pink">${((m.beat_alignment_ratio||0)*100).toFixed(0)}%</div><div class="lbl">🎯 卡点率</div></div>
      <div class="stat-tile"><div class="num green">${sr.length}</div><div class="lbl">🎤 语音段落</div></div>
      <div class="stat-tile"><div class="num ${faceTotal>0?'orange':''}">${faceTotal||0}</div><div class="lbl">👤 人脸</div></div>
      ${topEmotion?`<div class="stat-tile"><div class="num pink" style="font-size:16px">${esc(topEmotion)}</div><div class="lbl">💭 主导情绪</div></div>`:''}
    </div>

    ${sceneHtml?`<div class="scene-grid">${sceneHtml}</div>`:''}

    ${d.summary?`<div class="summary-card"><strong>📝 摘要${d.summary_method==='llm'?' · AI 生成':''}</strong><div style="margin-top:4px;color:var(--fg-2)">${esc(d.summary)}</div></div>`:''}

    <div class="timeline-card">
      <h3>🎞️ 时间轴 <small>${m.duration?m.duration.toFixed(1)+'s':''}</small><span class="tml-time" id="tmlTime">0.0s</span></h3>
      <div class="fs-wrap">
        <div class="fs-timerow"><span id="fsStart">0.0s</span><span id="fsEnd">${m.duration?m.duration.toFixed(1)+'s':''}</span></div>
        <div class="fs" id="fs">
          <div class="fs-playhead" id="fsPlayhead" style="left:0"></div>
          <div class="fs-preview" id="fsPreview"><img alt=""><div class="pv-body"><span class="pv-title"></span><div class="pv-desc"></div></div></div>
        </div>
      </div>
      <div class="tml-legend">
        <span><span class="sw" style="background:var(--orange)"></span> 节拍</span>
        <span><span class="sw" style="background:var(--red)"></span> 音效</span>
        <span><span class="sw" style="background:var(--cyan)"></span> 语音</span>
        <span style="margin-left:auto">鼠标悬停预览 · 点击跳转</span>
      </div>
    </div>

    ${cutPlan ? `
    <div class="cutplan-card">
      <h3>✂️ 剪辑方案 <small>套用「${esc(cutPlan.source || '示例视频')}」节奏 · ${cutPlan.total} 个镜头 · ${cutPlan.beat_aligned_count} 个卡点 · 共 ${cutPlan.target_duration.toFixed(1)}s</small></h3>
      <div class="cut-table-wrap">
        <table class="cut-table">
          <thead><tr><th>#</th><th>起点</th><th>终点</th><th>时长</th><th>卡点</th><th></th></tr></thead>
          <tbody>
            ${cutPlan.cuts.map((c, i) => `<tr onclick="window.__seek(${c.start})" title="点击预览该切点"><td>${i}</td><td>${c.start.toFixed(2)}s</td><td>${c.end.toFixed(2)}s</td><td>${c.duration.toFixed(2)}s</td><td>${c.aligned_to_beat ? '🎯' : '—'}</td><td class="cut-play">▶</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
      <div class="cut-actions">
        <button class="btn btn-sm btn-primary" onclick="downloadDraft()">📦 下载剪映草稿</button>
        <span class="cut-hint">点击任意行可预览该切点</span>
      </div>
    </div>` : ''}

    <div class="review-toolbar"><div><strong>分析结果复核</strong><span>${shots.length} 个镜头 · ${shots.filter(s => s.reviewed).length} 个已人工确认</span></div><span class="review-hint">低置信度或异常镜头建议先复核，再导出</span></div>
    <div class="section-header"><h3>🎞️ 分镜 <small>${shots.length} 个镜头 · ${described} 个已描述</small></h3><button class="btn btn-sm" onclick="reviewLowConfidence()">筛选待复核</button></div>
    <div class="shot-grid" id="shotGrid"></div>

    <div class="export-section">
      <div class="title">📥 导出</div>
      <div class="export-btns">
        <button class="btn btn-sm" onclick="dlExp('edl')">📋 EDL</button>
        <button class="btn btn-sm" onclick="dlExp('fcp7xml')">📋 FCP7 XML</button>
        <button class="btn btn-sm" onclick="dlExp('cutmark')">📋 Cutmark</button>
        <button class="btn btn-sm" onclick="dlExp('srt')">📜 SRT</button>
        <button class="btn btn-sm btn-primary" onclick="dlExp('all')">📦 全部 ZIP</button>
        <button class="btn btn-sm" onclick="pickTemplateVideo()" title="用自己的视频套用当前视频的镜头节奏">🎯 套用模板到我的视频</button>
      </div>
    </div>

    <div class="json-card">
      <div class="section-header"><h3>📄 剪辑 DNA <small>完整 JSON</small></h3><button class="btn btn-sm" onclick="copyJson()">📋 复制</button></div>
      <pre id="jsonPre">${esc(JSON.stringify(d,null,2))}</pre>
    </div>
  `;

  // ── Film Strip Timeline（任务1：时间轴与原视频时长对齐） ──
  const fs = document.getElementById('fs');
  const preview = document.getElementById('fsPreview');
  const pvImg = preview.querySelector('img');
  const pvTitle = preview.querySelector('.pv-title');
  const pvDesc = preview.querySelector('.pv-desc');
  const PX = 46; // 每秒像素宽度
  // 时间轴总长 = 视频实际时长（而非镜头时长之和），保证分镜与原视频时间轴对齐
  const totalDur = m.duration || 1;
  const fsW = Math.max(totalDur * PX, fs.clientWidth || 800);
  fs.style.width = fsW + 'px';

  shots.forEach((s, i) => {
    const el = document.createElement('div');
    el.className = 'fs-shot';
    el.dataset.idx = i;
    el.style.left = (s.start * PX) + 'px';
    el.style.width = Math.max(s.duration * PX - 2, 10) + 'px';
    const img = document.createElement('img');
    img.src = frameBase + encodeURIComponent(s.keyframe || '');
    img.onerror = () => img.style.display = 'none';
    const lbl = document.createElement('span');
    lbl.className = 'fs-label';
    lbl.textContent = i;
    el.appendChild(img); el.appendChild(lbl);
    el.title = '镜头 ' + i + ': ' + s.start.toFixed(1) + 's → ' + s.end.toFixed(1) + 's (' + s.duration.toFixed(1) + 's)' + (s.transition ? '\n切换: ' + s.transition : '') + (s.content ? '\n' + s.content : '') + (s.transcript ? '\n🎤 ' + s.transcript : '') + '\n点击跳转到该镜头';
    el.addEventListener('click', () => seekTo(s.start, i));
    el.addEventListener('mouseenter', (e) => showPreview(s, e, el));
    el.addEventListener('mousemove', (e) => showPreview(s, e, el));
    el.addEventListener('mouseleave', () => preview.style.opacity = 0);
    fs.appendChild(el);
  });
  (a.beats || []).forEach(b => { const el = document.createElement('div'); el.className = 'fs-beat'; el.style.left = (b * PX) + 'px'; fs.appendChild(el); });
  (a.sfx_candidates || []).forEach(sf => { const el = document.createElement('div'); el.className = 'fs-sfx'; el.style.left = (sf.time * PX) + 'px'; el.title = '音效: ' + sf.time.toFixed(2) + 's'; fs.appendChild(el); });
  sr.forEach(r => { const el = document.createElement('div'); el.className = 'fs-speech'; el.style.left = (r.start * PX) + 'px'; el.style.width = Math.max((r.end - r.start) * PX - 1, 6) + 'px'; el.title = (r.text || '语音') + ' [' + r.start.toFixed(1) + 's→' + r.end.toFixed(1) + 's]'; fs.appendChild(el); });

  function showPreview(s, e, el) {
    pvImg.src = frameBase + encodeURIComponent(s.keyframe || '');
    pvTitle.textContent = '镜头 ' + (el ? el.dataset.idx : '') + ' · ' + s.start.toFixed(1) + 's→' + s.end.toFixed(1) + 's · ' + s.duration.toFixed(1) + 's' + (s.transition ? ' · ' + s.transition : '');
    pvDesc.textContent = (s.content || '') + (s.transcript ? ' 🎤' + s.transcript : '');
    const fsRect = fs.getBoundingClientRect();
    let x = e.clientX - fsRect.left + fs.scrollLeft;
    preview.style.left = (e.clientX + 14) + 'px';
    preview.style.top = (fsRect.top - 130) + 'px';
    preview.style.opacity = 1;
  }
  fs.addEventListener('click', (e) => {
    if (e.target === fs) {
      const rect = fs.getBoundingClientRect();
      const t = Math.max(0, Math.min(1, (e.clientX - rect.left + fs.scrollLeft) / fsW)) * totalDur;
      const idx = shots.findIndex(s => t >= s.start && t < s.end);
      seekTo(t, idx);
    }
  });
  fs.addEventListener('mouseleave', () => preview.style.opacity = 0);

  // ── 分镜卡片 ──
  const sg = document.getElementById('shotGrid');
  window.__lastShots = shots;
  shots.forEach((s, i) => {
    const card = document.createElement('div');
    card.className = 'shot-card';
    let tags = '<span class="tag">' + esc(s.transition || '硬切') + '</span>';
    if (s.beat_aligned) tags += '<span class="tag tag-green">🎯 卡点</span>';
    if (s.scene_type) tags += '<span class="tag tag-blue">' + esc(sceneLabels[s.scene_type] || s.scene_type) + '</span>';
    if (s.face_count > 0) tags += '<span class="tag tag-orange">👤 ×' + esc(s.face_count) + '</span>';
    if (s.emotion) tags += '<span class="tag tag-pink">' + esc(s.emotion) + '</span>';
    if (s.color_tone) tags += '<span class="tag">🎨 ' + esc(s.color_tone) + '</span>';
    card.title = '点击跳转到该镜头 (' + s.start.toFixed(1) + 's)';
    card.innerHTML = `
      <img src="${frameBase}${encodeURIComponent(s.keyframe || '')}" alt="" loading="lazy" onerror="this.style.display='none'">
      <div class="shot-body">
        <div><span class="sn">镜头 ${i}</span><span class="sd">${s.duration.toFixed(1)}s</span></div>
        <div class="shot-tags">${tags}</div>
        ${s.transcript ? '<div class="transcript">🎤 ' + esc(s.transcript) + '</div>' : ''}
        ${s.content ? '<div class="desc">' + esc(s.content) + (s.shot_scale ? ' [' + esc(s.shot_scale) + ']' : '') + (s.camera_motion ? ' · ' + esc(s.camera_motion) : '') + '</div>' : ''}
        <div class="shot-card-foot"><span class="confidence ${Number(s.confidence || 1) < .7 ? 'low' : ''}">${Number(s.confidence || 1) < .7 ? '待复核' : '置信度 ' + Math.round(Number(s.confidence || 1) * 100) + '%'}</span><button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();editShot(${i})">编辑</button></div>
      </div>`;
    sg.appendChild(card);
  });

  // ── 时间轴 / 分镜 双向联动 ──
  const videoEl = document.getElementById('videoEl');
  const playhead = document.getElementById('fsPlayhead');
  const tmlTime = document.getElementById('tmlTime');
  const fsStart = document.getElementById('fsStart');
  const segEls = Array.from(fs.querySelectorAll('.fs-shot'));
  const cardEls = Array.from(sg.querySelectorAll('.shot-card'));
  const clamp = (t) => Math.max(0, Math.min(t, totalDur));
  function setActive(i) {
    segEls.forEach((el, idx) => el.classList.toggle('active', idx === i));
    cardEls.forEach((el, idx) => el.classList.toggle('active', idx === i));
  }
  function movePlayhead(t) {
    if (playhead) playhead.style.left = (clamp(t) * PX) + 'px';
    if (tmlTime) tmlTime.textContent = t.toFixed(1) + 's';
    if (fsStart) fsStart.textContent = t.toFixed(1) + 's';
  }
  function scrollFsTo(t) {
    const x = t * PX;
    fs.scrollTo({ left: Math.max(0, Math.min(x - fs.clientWidth / 2, fs.scrollWidth - fs.clientWidth)), behavior: 'smooth' });
  }
  function seekTo(t, i) {
    if (videoEl) { videoEl.currentTime = clamp(t); videoEl.play().catch(() => {}); }
    setActive(i);
    movePlayhead(t);
    scrollFsTo(t);
    if (cardEls[i] && cardEls[i].scrollIntoView) cardEls[i].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
  }
  segEls.forEach((el, i) => el.addEventListener('click', () => seekTo(shots[i].start, i)));
  cardEls.forEach((el, i) => el.addEventListener('click', () => seekTo(shots[i].start, i)));
  window.__seek = (t) => { if (videoEl) { videoEl.currentTime = clamp(t); videoEl.play().catch(() => {}); } movePlayhead(t); scrollFsTo(t); };
  if (videoEl) {
    videoEl.addEventListener('timeupdate', () => {
      const t = videoEl.currentTime;
      movePlayhead(t);
      const last = shots[shots.length - 1];
      let idx = shots.findIndex(s => t >= s.start && t < s.end);
      if (idx === -1 && last && t >= last.end) idx = shots.length - 1;
      if (idx >= 0) setActive(idx);
    });
    videoEl.addEventListener('loadedmetadata', () => movePlayhead(0));
  }
  movePlayhead(0);
}

function reviewLowConfidence() {
  const cards = document.querySelectorAll('#shotGrid .shot-card');
  let count = 0;
  cards.forEach((card, index) => {
    const shot = window.__lastShots?.[index];
    const low = shot && Number(shot.confidence || 1) < .7 && !shot.reviewed;
    card.classList.toggle('review-needed', !!low);
    if (low) count++;
  });
  toast(count ? `已标出 ${count} 个待复核镜头` : '没有发现低置信度镜头', count ? 'info' : 'success');
}

// ── Export ──
function exportPreflight(result, format) {
  const errors = [], warnings = [];
  const shots = Array.isArray(result?.shots) ? result.shots : [];
  const duration = Number(result?.meta?.duration || 0);
  const fps = Number(result?.meta?.fps || 0);
  if (!shots.length) errors.push('没有可导出的镜头');
  if (!Number.isFinite(duration) || duration <= 0) errors.push('视频时长无效');
  if (!Number.isFinite(fps) || fps <= 0) warnings.push('源视频帧率缺失，导出器将使用默认帧率');
  let previousEnd = 0;
  shots.forEach((shot, index) => {
    const start = Number(shot.start), end = Number(shot.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) { errors.push('镜头 ' + index + ' 的时间范围无效'); return; }
    if (start < 0 || end > duration + 0.02) errors.push('镜头 ' + index + ' 超出源视频时长');
    if (index > 0 && start + 0.01 < previousEnd) errors.push('镜头 ' + index + ' 与前一个镜头重叠');
    if (index > 0 && start - previousEnd > 0.05) warnings.push('镜头 ' + index + ' 前存在 ' + (start - previousEnd).toFixed(2) + ' 秒空洞');
    if (fps > 0 && Math.round((end - start) * fps) < 1) errors.push('镜头 ' + index + ' 小于一帧，无法稳定导出');
    previousEnd = Math.max(previousEnd, end);
  });
  const source = window.__currentAssetPath || currentFile?.name || result?._source_file;
  if (!source) warnings.push('未绑定源素材路径，导入剪辑软件后可能需要手动重链接');
  else if (window.__currentAssetPath) warnings.push('导出将引用本机素材路径：' + window.__currentAssetPath);
  if (format === 'edl' && fps > 0 && Math.abs(fps - Math.round(fps)) > 0.01) warnings.push('EDL 将把非整数帧率转换为整数 timebase，请在 NLE 中核对时间码');
  return { errors, warnings };
}

async function showExportPreflight(result, format) {
  const report = exportPreflight(result, format);
  const sourcePath = window.__currentAssetPath;
  if (!report.errors.length && sourcePath && window.electronAPI?.fileExists) {
    const source = await window.electronAPI.fileExists(sourcePath);
    if (!source.exists || !source.isFile) report.errors.push('源素材不存在或不是文件：' + sourcePath);
  }
  if (report.errors.length) {
    toast('❌ 导出预检失败：' + report.errors.slice(0, 2).join('；') + (report.errors.length > 2 ? '；还有 ' + (report.errors.length - 2) + ' 项' : ''), 'error', 7000);
    return false;
  }
  if (report.warnings.length) toast('⚠️ 导出预检提示：' + report.warnings.slice(0, 2).join('；'), 'info', 6000);
  return true;
}

async function dlExp(fmt) {
  if (!currentResult) { toast('❌ 无分析结果', 'error'); return; }
  lastOperationRetry = () => dlExp(fmt);
  if (!await showExportPreflight(currentResult, fmt)) return;
  try {
    const s = getSettings();
    const body = currentResult;
    if (s.download_dir) body._download_dir = s.download_dir;
    const res = await fetch('/api/export?fmt='+fmt, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
    if (!res.ok) throw new Error(res.statusText);
    const cd = res.headers.get('content-disposition') || '';
    if (!cd.includes('attachment')) {
      // 服务端已保存到下载目录
      const data = await res.json();
      if (data.path) { toast('✅ 已导出到：' + data.path, 'success', 6000); return; }
    }
    const names = {edl:'videodna.edl',fcp7xml:'videodna.xml',cutmark:'videodna_cuts.json',srt:'videodna_subtitles.srt',all:'videodna_export.zip'};
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = names[fmt]||'videodna.'+fmt;
    a.click();
    URL.revokeObjectURL(a.href);
    toast('✅ 已导出 '+(names[fmt]||fmt), 'success');
  } catch(err) { showErrorPanel('导出失败', '分析结果仍保留在当前项目中，修复问题后可以重新导出。', err, '导出'); toast('❌ 导出失败: '+err.message, 'error'); }
}

// ── Copy JSON ──
function copyJson() {
  const pre = document.getElementById('jsonPre');
  if (!pre) return;
  navigator.clipboard.writeText(pre.textContent).then(() => toast('📋 已复制', 'success')).catch(() => toast('📋 复制失败', 'error'));
}
