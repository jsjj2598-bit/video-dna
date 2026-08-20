// ── AI 创作中心（任务8：AI 视频生成平台通用功能） ──
async function loadStudio() {
  try {
    const res = await fetch('/api/ai/templates');
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    const tpls = data.templates || [];
    document.getElementById('studioTpls').innerHTML = tpls.map(t => `
      <div class="studio-tpl" onclick="applyStudioTemplate('${t.id}')" title="点击套用到自己的视频">
        <span class="st-icon">${t.icon||'🎬'}</span>
        <div class="st-name">${esc(t.name)}</div>
        <div class="st-desc">${esc(t.desc)}</div>
        <div class="st-meta">
          <span class="badge badge-model">🎵 ${t.bpm} BPM</span>
          <span class="badge badge-local">⏱ ${t.shot}s/镜</span>
          <span class="badge badge-chat">点击套用</span>
        </div>
      </div>
    `).join('');
    if (!tpls.length) document.getElementById('studioTpls').innerHTML = '<div class="empty-state">暂无模板</div>';
  } catch(e) { document.getElementById('studioTpls').innerHTML = '<div class="empty-state">加载模板失败: '+esc(e.message)+'</div>'; }
}

function applyStudioTemplate(tplId) {
  if (!confirm('将模板节奏套用到你的视频？请选择要分析的视频文件。')) return;
  document.getElementById('templateInput').dataset.tpl = tplId;
  document.getElementById('templateInput').click();
}

async function genStoryboard() {
  const topic = document.getElementById('sbTopic').value.trim();
  const count = parseInt(document.getElementById('sbCount').value || '6', 10);
  if (!topic) { toast('❌ 请输入主题或文案', 'error'); return; }
  const el = document.getElementById('sbResult');
  el.innerHTML = '<span style="color:var(--accent-3)">⏳ 正在生成分镜脚本…</span>';
  try {
    const res = await fetch('/api/ai/storyboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, length: count }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const shots = data.shots || [];
    const rows = shots.map((s, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${esc(s.scene || '')}</td>
        <td>${esc(s.camera || '')}</td>
        <td>${s.duration ? s.duration + 's' : '-'}</td>
        <td>${esc(s.voiceover || s.vo || '')}</td>
        <td>${esc(s.transition || '-')}</td>
      </tr>
    `).join('');
    el.innerHTML = `
      <div style="font-size:11px;color:var(--fg-3);margin-bottom:6px">${data.method === 'llm' ? '✨ AI 生成（' + esc(data.model || '') + '）' : '🧩 内置框架生成'} · 主题：${esc(topic)}</div>
      <table class="sb-table"><thead><tr><th>#</th><th>画面</th><th>景别/运镜</th><th>时长</th><th>台词/旁白</th><th>转场</th></tr></thead><tbody>${rows}</tbody></table>
    `;
  } catch(e) { el.innerHTML = '<span style="color:var(--red)">❌ ' + esc(e.message) + '</span>'; }
}

async function recommendBgm() {
  if (!currentResult) { toast('⚠️ 请先分析一个视频', 'error'); return; }
  const el = document.getElementById('bgmResult');
  el.innerHTML = '<span style="color:var(--accent-3)">⏳ 正在分析…</span>';
  try {
    const res = await fetch('/api/ai/bgm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dna: currentResult }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    el.innerHTML = `
      <div class="bgm-box">
        <div><span style="font-size:11px;color:var(--fg-3)">检测 BPM</span><div class="bgm-mood">${data.bpm} BPM</div></div>
        <div><span style="font-size:11px;color:var(--fg-3)">情绪风格</span><div class="bgm-mood">${esc(data.mood)}</div></div>
        <div><span style="font-size:11px;color:var(--fg-3)">推荐曲风</span><div style="font-size:13px;font-weight:600">${esc((data.recommend||[]).join(' / '))}</div></div>
      </div>
      <div style="margin-top:10px;font-size:12px;color:var(--fg-2);line-height:1.7">
        <div>💡 ${esc(data.hint)}</div>
        <div>🔍 ${esc(data.search_hint)}</div>
      </div>
    `;
  } catch(e) { el.innerHTML = '<span style="color:var(--red)">❌ ' + esc(e.message) + '</span>'; }
}

// ── Modal helpers ──
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.querySelectorAll('.modal-overlay').forEach(m => m.addEventListener('mousedown', e => { if (e.target === m) m.classList.remove('active'); }));

// ── Init ──
loadSettings();
renderHistory();
