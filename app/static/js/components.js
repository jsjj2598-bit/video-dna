// ── Components: load & render ──
async function loadComponents() {
  try {
    const res = await fetch('/api/components');
    if (!res.ok) throw new Error(res.statusText);
    compState = await res.json();
    renderComponents();
    renderModels();
    renderPlugins();
    renderSkills();
  } catch(e) { toast('❌ 加载组件失败: '+e.message, 'error'); }
}

function renderComponents() {
  const kinds = {vision:'视觉模型', chat:'对话模型', local:'本地引擎'};
  document.getElementById('compGrid').innerHTML = (compState.components||[]).map(c => `
    <div class="comp-card">
      <div class="top">
        <div class="ico">${c.icon||'⚙️'}</div>
        <div>
          <div class="cname">${esc(c.name)}</div>
          <div class="ckind">${kinds[c.kind]||c.kind}</div>
        </div>
      </div>
      <div class="cdesc">${esc(c.desc)}</div>
      <div class="foot">
        <span class="badge ${c.enabled?'badge-on':'badge-off'}">${c.enabled?'运行中':'已停用'}</span>
        <button class="toggle ${c.enabled?'on':''}" onclick="toggleComponent('${c.id}')" title="启用/停用"></button>
      </div>
    </div>
  `).join('') || '<div class="empty-state">暂无组件</div>';
}

async function toggleComponent(cid) {
  const c = (compState.components||[]).find(x => x.id === cid);
  if (!c) return;
  const next = !c.enabled;
  try {
    const res = await fetch(`/api/components/${cid}/toggle`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled: next}) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    c.enabled = next;
    renderComponents();
    toast('⚙️ ' + c.name + ' 已' + (next?'启用':'停用'), 'success');
  } catch(e) { toast('❌ 切换失败: '+e.message, 'error'); }
}

// ── Models ──
function renderModels() {
  const list = compState.models || [];
  const el = document.getElementById('modelList');
  if (!list.length) { el.innerHTML = '<div class="empty-state" style="margin:14px 0">尚未添加模型，点击右上角「添加模型」接入你的 AI</div>'; return; }
  const kindLabel = {vision:'视觉', chat:'对话'};
  const provLabel = {openai:'OpenAI', dashscope:'通义', ollama:'Ollama', custom:'自定义'};
  el.innerHTML = list.map(m => `
    <div class="model-row">
      <div class="m-ico">${m.kind==='vision'?'👁️':'💬'}</div>
      <div>
        <div class="m-name">${esc(m.name)} <span class="badge ${m.kind==='vision'?'badge-vision':'badge-chat'}">${kindLabel[m.kind]||m.kind}</span> ${m.has_api_key?'<span class="badge badge-on">已配置 Key</span>':'<span class="badge badge-off">未配置 Key</span>'}</div>
        <div class="m-meta">${provLabel[m.provider]||m.provider} · ${esc(m.base_url)} · ${esc(m.model)}${m.builtin?' · 内置':''}</div>
      </div>
      <div class="actions">
        <button class="btn btn-sm" onclick="testModelById('${m.id}')">🔌 测试</button>
        <button class="btn btn-sm" onclick="editModel('${m.id}')">✏️ 编辑</button>
        <button class="btn btn-sm btn-danger" onclick="deleteModel('${m.id}')">🗑️</button>
      </div>
    </div>
  `).join('');
}

function openModelModal() {
  document.getElementById('modelModalTitle').textContent = '添加模型';
  document.getElementById('mId').value = '';
  document.getElementById('mName').value = '';
  document.getElementById('mKind').value = 'vision';
  document.getElementById('mProvider').value = 'openai';
  document.getElementById('mBaseUrl').value = 'https://api.openai.com/v1';
  document.getElementById('mModel').value = '';
  document.getElementById('mApiKey').value = '';
  document.getElementById('mApiKey').placeholder = '输入 API Key';
  openModal('modalModel');
}

function editModel(id) {
  const m = (compState.models||[]).find(x => x.id === id);
  if (!m) return;
  document.getElementById('modelModalTitle').textContent = '编辑模型';
  document.getElementById('mId').value = m.id;
  document.getElementById('mName').value = m.name;
  document.getElementById('mKind').value = m.kind;
  document.getElementById('mProvider').value = m.provider;
  document.getElementById('mBaseUrl').value = m.base_url;
  document.getElementById('mModel').value = m.model;
  document.getElementById('mApiKey').value = '';
  document.getElementById('mApiKey').placeholder = m.has_api_key ? '已配置；留空表示保留原 Key' : '输入 API Key';
  openModal('modalModel');
}

function providerChanged() {
  const p = document.getElementById('mProvider').value;
  const urls = {
    openai: 'https://api.openai.com/v1',
    dashscope: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    ollama: 'http://localhost:11434/v1',
    custom: ''
  };
  const models = {openai:'gpt-4o', dashscope:'qwen-max', ollama:'llama3', custom:''};
  document.getElementById('mBaseUrl').value = urls[p] || document.getElementById('mBaseUrl').value;
  document.getElementById('mModel').value = models[p] || document.getElementById('mModel').value;
}

async function saveModel() {
  const body = {
    name: document.getElementById('mName').value.trim(),
    kind: document.getElementById('mKind').value,
    provider: document.getElementById('mProvider').value,
    base_url: document.getElementById('mBaseUrl').value.trim(),
    model: document.getElementById('mModel').value.trim(),
    api_key: document.getElementById('mApiKey').value.trim(),
  };
  const id = document.getElementById('mId').value;
  if (!body.name || !body.base_url || !body.model) { toast('❌ 名称、接口地址与模型名不能为空', 'error'); return; }
  try {
    const url = id ? '/api/models/' + id : '/api/models';
    const res = await fetch(url, { method: id ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    closeModal('modalModel');
    toast('✅ 模型已保存', 'success');
    loadComponents();
  } catch(e) { toast('❌ 保存失败: '+e.message, 'error'); }
}

async function testModelById(id) {
  const m = (compState.models||[]).find(x => x.id === id);
  if (!m) return;
  if (!m.has_api_key) { toast('⚠️ 该模型未配置 API Key，无法测试', 'error'); return; }
  try {
    toast('🔌 正在测试连接...', 'info');
    const res = await fetch('/api/models/' + id + '/test', { method:'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    toast('✅ 连接成功：' + data.reply, 'success', 5000);
  } catch(e) { toast('❌ 测试失败: '+e.message, 'error', 6000); }
}

async function testModel() {
  const id = document.getElementById('mId').value;
  if (!id) { toast('⚠️ 请先保存模型再测试', 'error'); return; }
  testModelById(id);
}

async function deleteModel(id) {
  const m = (compState.models||[]).find(x => x.id === id);
  if (!m || m.builtin) { toast('⚠️ 内置模型不可删除，可通过编辑覆盖', 'error'); return; }
  if (!confirm('确定删除模型「'+m.name+'」？')) return;
  try {
    const res = await fetch('/api/models/' + id, { method:'DELETE' });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    toast('🗑️ 已删除', 'success');
    loadComponents();
  } catch(e) { toast('❌ 删除失败: '+e.message, 'error'); }
}

// ── Plugins ──
function renderPlugins() {
  const list = compState.plugins || [];
  const el = document.getElementById('pluginList');
  if (!list.length) { el.innerHTML = '<div class="empty-state" style="margin:14px 0">未安装插件。插件是包含 manifest.json 与各平台可执行文件的 ZIP，通过 JSON stdin/stdout 扩展分析结果。</div>'; return; }
  el.innerHTML = list.map(p => `
    <div class="model-row">
      <div class="m-ico">🔌</div>
      <div>
        <div class="m-name">${esc(p.name)} <span class="badge badge-model">v${esc(p.version)}</span></div>
        <div class="m-meta">hooks: ${(p.hooks||[]).join(', ') || '无'}</div>
      </div>
      <div style="font-size:11px;color:var(--fg-3)">${esc(p.desc||'')}</div>
      <div class="actions">
        <button class="btn btn-sm btn-danger" onclick="deletePlugin('${p.id}')">🗑️ 卸载</button>
      </div>
    </div>
  `).join('');
}

async function installPlugin() {
  const input = document.getElementById('pluginInput');
  const f = input.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  toast('📦 正在安装插件...', 'info');
  try {
    const res = await fetch('/api/plugins/install', { method:'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    toast('✅ 插件「'+data.plugin.name+'」安装成功', 'success');
    input.value = '';
    loadComponents();
  } catch(e) { toast('❌ 安装失败: '+e.message, 'error', 6000); }
}

async function deletePlugin(id) {
  if (!confirm('确定卸载该插件？')) return;
  try {
    const res = await fetch('/api/plugins/' + id, { method:'DELETE' });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    toast('🗑️ 插件已卸载', 'success');
    loadComponents();
  } catch(e) { toast('❌ 卸载失败: '+e.message, 'error'); }
}

// ── Skills ──
function renderSkills() {
  const list = compState.skills || [];
  const el = document.getElementById('skillList');
  if (!list.length) { el.innerHTML = '<div class="empty-state">暂无技能，点击「自定义技能」创建（内置技能已就绪）</div>'; return; }
  el.innerHTML = list.map(s => `
    <div class="skill-card">
      <div class="top">
        <div class="ico">✨</div>
        <div>
          <div class="sname">${esc(s.name)} ${s.builtin?'<span class="badge badge-model">内置</span>':'<span class="badge badge-local">自定义</span>'}</div>
        </div>
      </div>
      <div class="sdesc">${esc(s.desc||'')}</div>
      <div class="foot">
        <button class="btn btn-sm btn-primary" onclick="runSkill('${s.id}')">▶ 运行</button>
        ${s.builtin?'':`<button class="btn btn-sm btn-danger" onclick="deleteSkill('${s.id}')">🗑️</button>`}
      </div>
    </div>
  `).join('');
}

function openSkillModal() {
  document.getElementById('skName').value = '';
  document.getElementById('skDesc').value = '';
  document.getElementById('skPrompt').value = '';
  openModal('modalSkill');
}

async function saveSkill() {
  const body = {
    name: document.getElementById('skName').value.trim(),
    desc: document.getElementById('skDesc').value.trim(),
    prompt: document.getElementById('skPrompt').value.trim(),
  };
  if (!body.name || !body.prompt) { toast('❌ 名称与提示词不能为空', 'error'); return; }
  try {
    const res = await fetch('/api/skills', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    closeModal('modalSkill');
    toast('✅ 技能已创建', 'success');
    loadComponents();
  } catch(e) { toast('❌ 创建失败: '+e.message, 'error'); }
}

async function deleteSkill(id) {
  if (!confirm('确定删除该技能？')) return;
  try {
    const res = await fetch('/api/skills/' + id, { method:'DELETE' });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    toast('🗑️ 技能已删除', 'success');
    loadComponents();
  } catch(e) { toast('❌ 删除失败: '+e.message, 'error'); }
}

async function runSkill(id) {
  if (!currentResult) { toast('⚠️ 请先分析一个视频，再运行技能', 'error'); return; }
  const s = (compState.skills||[]).find(x => x.id === id);
  if (!s) return;
  showP('正在运行「' + s.name + '」...', 'AI 生成中，通常需要 10~60 秒');
  try {
    const body = currentSessionId ? { session_id: currentSessionId } : { dna: currentResult };
    const res = await fetch('/api/skills/' + id + '/run', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    hideP();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    document.getElementById('outputTitle').textContent = '✨ ' + data.skill;
    document.getElementById('outputBody').textContent = data.output;
    openModal('modalOutput');
  } catch(e) {
    hideP();
    toast('❌ 技能运行失败: '+e.message, 'error', 7000);
  }
}

function copyOutput() {
  const body = document.getElementById('outputBody');
  navigator.clipboard.writeText(body.textContent).then(() => toast('📋 已复制', 'success')).catch(() => toast('📋 复制失败', 'error'));
}
