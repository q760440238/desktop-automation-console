/* 桌面自动化控制台 — 前端逻辑（原生 JS，无依赖） */
'use strict';

const $ = (id) => document.getElementById(id);

const S = {
  health: null,
  settings: null,
  platform: null,
  action: null,
  job: null,
  plan: null,
  events: [],
  lastEventId: 0,
  panic: false,
  tick: 0,
  timer: null,
  busy: false,
};

const LS = {
  platform: 'dac.platform',
  action: 'dac.action',
  targets: 'dac.targets',
  message: 'dac.message',
};

/* ---------------------------------------------------------------- 工具 */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function trim(s, n) {
  s = String(s == null ? '' : s);
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function toast(msg, kind) {
  const el = $('toast');
  el.textContent = msg;
  el.className = 'toast ' + (kind || '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), 4200);
  el.classList.remove('hidden');
}

function showModal(title, body) {
  $('modalTitle').textContent = title;
  $('modalBody').textContent = body;
  $('modal').classList.remove('hidden');
}

async function api(path, opts) {
  const res = await fetch('/api' + path, Object.assign({
    headers: { 'Content-Type': 'application/json' },
  }, opts || {}));
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = { ok: false, detail: '响应不是合法 JSON（HTTP ' + res.status + '）' };
  }
  if (!res.ok) {
    throw new Error(data && data.detail ? data.detail : 'HTTP ' + res.status);
  }
  return data;
}

function log(level, platform, message) {
  const body = $('logBody');
  const now = new Date();
  const t = now.toTimeString().slice(0, 8);
  const line = document.createElement('div');
  line.className = 'log-line ' + (level || 'info');
  line.innerHTML =
    '<span class="t">' + t + '</span>' +
    (platform ? '<span class="p">[' + esc(platform) + ']</span>' : '') +
    '<span class="m">' + esc(message) + '</span>';
  const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
  body.appendChild(line);
  while (body.childElementCount > 300) body.removeChild(body.firstChild);
  if (atBottom) body.scrollTop = body.scrollHeight;
}

/* ---------------------------------------------------------------- 渲染：顶栏 */
function renderTop() {
  const h = S.health;
  if (!h) return;
  $('runningCount').textContent = h.running || 0;
  $('pendingCount').textContent = h.pending || 0;

  S.panic = !!h.panic;
  $('panicBanner').classList.toggle('hidden', !S.panic);
  $('panicBtn').textContent = S.panic ? '已急停' : '急停';
  $('panicBtn').style.background = S.panic ? 'rgba(255,77,79,.4)' : '';

  const mode = (S.settings && S.settings.mode) || h.mode || 'confirm';
  document.querySelectorAll('#modeSwitch button').forEach((b) => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  const sim = S.settings ? !!S.settings.simulation : !!h.simulation;
  $('simToggle').checked = sim;
}

/* ---------------------------------------------------------------- 渲染：平台 */
function platforms() {
  return (S.health && S.health.platforms) || [];
}

function currentPlatform() {
  const list = platforms();
  return list.find((p) => p.key === S.platform) || null;
}

function renderPlatforms() {
  const box = $('platformList');
  const list = platforms();
  if (!list.length) {
    box.innerHTML = '<div class="empty">正在读取平台状态…</div>';
    return;
  }
  box.innerHTML = list.map((p) => {
    const ready = p.health && p.health.ready;
    return `
      <div class="platform-card ${p.key === S.platform ? 'selected' : ''}"
           data-key="${esc(p.key)}" style="--c:${esc(p.color)}" role="button" tabindex="0">
        <div class="pc-row">
          <span class="pc-glyph">${esc(p.name.slice(0, 1))}</span>
          <span class="pc-name">${esc(p.name)}</span>
          <span class="pc-kind">${p.kind === 'desktop' ? '桌面端' : '网页端'}</span>
          <span class="pc-dot ${ready ? 'ready' : ''}"></span>
        </div>
        <div class="pc-detail" title="${esc(p.health ? p.health.detail : '')}">
          ${esc((p.health && p.health.detail) || '未知状态')}
        </div>
        <div class="pc-tools">
          <button data-act="open" data-key="${esc(p.key)}">${p.kind === 'desktop' ? '启动应用' : '打开浏览器登录'}</button>
          <button data-act="probe" data-key="${esc(p.key)}">探测</button>
        </div>
      </div>`;
  }).join('');
}

function renderActions() {
  const p = currentPlatform();
  const box = $('actionChips');
  if (!p) {
    box.innerHTML = '<span class="hint">请先在左侧选择平台</span>';
    $('platformTag').textContent = '未选平台';
    $('platformHint').textContent = '';
    $('limitsBox').innerHTML = '';
    return;
  }
  if (!p.actions.includes(S.action)) S.action = p.actions[0];
  box.innerHTML = p.actions.map((a) => `
    <button class="chip ${a === S.action ? 'active' : ''}" data-action="${esc(a)}">
      ${esc((p.action_labels && p.action_labels[a]) || a)}
    </button>`).join('');
  $('platformTag').textContent = p.name + ' · ' + (p.kind === 'desktop' ? '桌面端' : '网页端');
  $('platformHint').textContent = p.hint || '';
  $('messageStep').style.display = S.action === 'send_message' ? '' : 'none';
  $('targets').placeholder = '每行一个目标：' + (p.target_label || '链接或账号');
  renderLimits();
}

function renderLimits() {
  const p = currentPlatform();
  const box = $('limitsBox');
  if (!p || !S.settings) { box.innerHTML = ''; return; }
  const g = S.settings.guardrails || {};
  const lim = Object.assign({}, g.default || {}, (g.per_platform || {})[p.key] || {});
  box.innerHTML = `
    <div class="limit-item"><b>${esc(lim.per_hour != null ? lim.per_hour : '—')}</b><span>次 / 小时</span></div>
    <div class="limit-item"><b>${esc(lim.per_day != null ? lim.per_day : '—')}</b><span>次 / 天</span></div>
    <div class="limit-item"><b>${esc(lim.delay_min != null ? lim.delay_min : '—')}–${esc(lim.delay_max != null ? lim.delay_max : '—')}</b><span>秒 / 间隔</span></div>`;
}

/* ---------------------------------------------------------------- 渲染：任务 */
function renderJob() {
  const job = S.job;
  const list = $('stepList');

  // 被拦截项
  const blocked = (S.plan || []).filter((x) => !x.allowed);
  const bBox = $('blockedBox');
  if (blocked.length) {
    bBox.classList.remove('hidden');
    bBox.innerHTML = '<h4>被安全策略拦截 ' + blocked.length + ' 条</h4>' +
      blocked.map((b) => `<div>· ${esc(trim(b.target, 60))} — ${esc(b.reason)}</div>`).join('');
  } else {
    bBox.classList.add('hidden');
    bBox.innerHTML = '';
  }

  if (!job) {
    $('jobTitle').textContent = '尚未生成计划';
    list.innerHTML = '<div class="empty">选择平台并生成计划后，这里会列出每一条待执行动作。</div>';
    $('progressBar').style.width = '0%';
    $('progressText').textContent = '0 / 0';
    $('progressPct').textContent = '0%';
    ['approveAll', 'rejectAll', 'runBtn', 'stopBtn'].forEach((id) => { $(id).disabled = true; });
    return;
  }

  $('jobTitle').textContent = job.platform_name + ' · ' + job.action_label + ' · ' + job.steps.length + ' 条';
  const st = job.stats || {};
  const total = st.total || job.steps.length || 0;
  const done = (st.ok || 0) + (st.failed || 0) + (st.skipped || 0) + (st.rejected || 0);
  const pct = total ? Math.round((done / total) * 100) : 0;
  $('progressBar').style.width = pct + '%';
  $('progressText').textContent = done + ' / ' + total +
    '（成功 ' + (st.ok || 0) + ' · 失败 ' + (st.failed || 0) +
    ' · 跳过 ' + (st.skipped || 0) + ' · 待执行 ' + (st.approved || 0) + '）';
  $('progressPct').textContent = pct + '%';

  $('approveAll').disabled = !(st.pending > 0);
  $('rejectAll').disabled = !(st.pending > 0 || st.approved > 0);
  $('runBtn').disabled = !(st.approved > 0) || job.status === 'running';
  $('stopBtn').disabled = job.status !== 'running';

  if (!job.steps.length) {
    list.innerHTML = '<div class="empty">该任务没有可执行步骤。</div>';
    return;
  }

  const label = { pending: '待审批', approved: '已批准', running: '执行中', ok: '成功', failed: '失败', rejected: '已拒绝', skipped: '跳过' };
  const riskLabel = { low: '低', medium: '中', high: '高' };

  list.innerHTML = job.steps.map((s) => {
    const acts = s.status === 'pending'
      ? `<button data-step-act="approve" data-id="${esc(s.id)}">批准</button>
         <button data-step-act="reject" data-id="${esc(s.id)}">拒绝</button>`
      : '';
    const detail = s.detail
      ? `<div class="si-detail ${s.status === 'failed' ? 'err' : ''}" title="${esc(s.detail)}">${esc(trim(s.detail, 90))}</div>`
      : (s.text ? `<div class="si-detail" title="${esc(s.text)}">${esc(trim(s.text, 60))}</div>` : '');
    return `
      <div class="step-item ${esc(s.status)}">
        <span class="si-index">${String(s.index + 1).padStart(2, '0')}</span>
        <div class="si-main">
          <div class="si-target" title="${esc(s.target)}">${esc(trim(s.target, 70))}</div>
          ${detail}
        </div>
        <span class="risk risk-${esc(s.risk)}">${esc(riskLabel[s.risk] || s.risk)}</span>
        <span class="status st-${esc(s.status)}">${esc(label[s.status] || s.status)}</span>
        <div class="si-actions">${acts}</div>
      </div>`;
  }).join('');
}

/* ---------------------------------------------------------------- 动作 */
async function loadSettings() {
  try {
    S.settings = await api('/settings');
  } catch (e) {
    S.settings = null;
  }
}

async function refreshHealth() {
  try {
    S.health = await api('/health');
  } catch (e) {
    log('error', '', '无法连接控制台服务：' + e.message);
    return;
  }
  renderTop();
  renderPlatforms();
}

async function selectPlatform(key) {
  S.platform = key;
  const p = currentPlatform();
  if (p && !p.actions.includes(S.action)) S.action = p.actions[0];
  localStorage.setItem(LS.platform, S.platform || '');
  localStorage.setItem(LS.action, S.action || '');
  renderPlatforms();
  renderActions();
}

async function doPlan() {
  const p = currentPlatform();
  if (!p) { toast('请先选择平台', 'error'); return; }
  const raw = $('targets').value || '';
  const targets = raw.split(/\r?\n|，|,/).map((x) => x.trim()).filter(Boolean);
  if (!targets.length) { toast('请填写至少一个目标', 'error'); return; }
  if (S.action === 'send_message' && !$('message').value.trim()) {
    toast('发消息需要填写文案', 'error'); return;
  }

  $('planBtn').disabled = true;
  $('planStatus').textContent = '正在校验…';
  try {
    const data = await api('/plan', {
      method: 'POST',
      body: JSON.stringify({
        platform: p.key,
        action: S.action,
        targets: targets,
        message: $('message').value,
      }),
    });
    S.job = data.job;
    S.plan = data.plan || [];
    localStorage.setItem('dac.job', S.job.id);
    const blocked = S.plan.filter((x) => !x.allowed).length;
    $('planStatus').textContent = '已生成：' + S.job.steps.length + ' 条可执行，' + blocked + ' 条被拦截';
    toast('计划已生成，请在右侧批准', 'success');
    renderJob();
  } catch (e) {
    $('planStatus').textContent = '';
    toast(e.message, 'error');
    log('error', p.name, '生成计划失败：' + e.message);
  } finally {
    $('planBtn').disabled = false;
  }
}

async function jobAction(kind, body) {
  if (!S.job) return;
  const id = S.job.id;
  try {
    if (kind === 'approve' || kind === 'reject') {
      const data = await api('/jobs/' + id + '/' + kind, { method: 'POST', body: JSON.stringify(body || {}) });
      S.job = data.job;
      renderJob();
      await refreshHealth();
    } else if (kind === 'run') {
      const data = await api('/jobs/' + id + '/run', { method: 'POST', body: '{}' });
      S.job = data.job;
      renderJob();
      await refreshHealth();
      toast('已开始执行', 'success');
    } else if (kind === 'stop') {
      const data = await api('/jobs/' + id + '/stop', { method: 'POST', body: '{}' });
      S.job = data.job;
      renderJob();
      toast('已请求停止', '');
    }
  } catch (e) {
    toast(e.message, 'error');
    log('error', '', e.message);
  }
}

async function setPanic(on) {
  try {
    const data = await api('/panic', { method: 'POST', body: JSON.stringify({ on: on }) });
    S.panic = !!data.panic;
    await refreshHealth();
    toast(S.panic ? '已急停，所有任务中止' : '急停已解除', S.panic ? 'error' : 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function patchSettings(patch) {
  try {
    S.settings = await api('/settings', { method: 'POST', body: JSON.stringify({ patch: patch }) });
    renderTop();
    renderLimits();
    toast('设置已保存', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ---------------------------------------------------------------- 轮询 */
async function tick() {
  if (document.hidden) return;
  S.tick += 1;
  if (S.tick % 3 === 1) await refreshHealth();

  if (S.job) {
    try {
      const d = await api('/jobs/' + S.job.id);
      if (d.job) {
        S.job = d.job;
        renderJob();
      }
    } catch (e) { /* 任务可能已被清理，忽略 */ }
  }

  try {
    const d = await api('/events?after=' + S.lastEventId + '&limit=100');
    (d.events || []).forEach((ev) => {
      S.lastEventId = Math.max(S.lastEventId, ev.id);
      log(ev.level, '', ev.message);
    });
  } catch (e) { /* 静默 */ }

  if (S.tick % 4 === 0) {
    try {
      const a = await api('/audit?limit=1');
      const t = a.today || {};
      $('auditStats').innerHTML =
        '今日成功 <b>' + (t.ok || 0) + '</b> · 失败 <b>' + (t.failed || 0) + '</b> · ' +
        '拒绝 <b>' + (t.rejected || 0) + '</b> · 跳过 <b>' + (t.skipped || 0) + '</b>';
    } catch (e) { /* 静默 */ }
  }
}

/* ---------------------------------------------------------------- 事件绑定 */
function bind() {
  $('platformList').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (btn) {
      e.stopPropagation();
      const key = btn.dataset.key;
      const act = btn.dataset.act;
      const label = btn.textContent;
      btn.disabled = true;
      btn.textContent = act === 'probe' ? '探测中…' : '打开中…';
      try {
        if (act === 'probe') {
          const d = await api('/adapters/' + key + '/probe', { method: 'POST', body: '{}' });
          showModal('控件探测 · ' + key, JSON.stringify(d.data || d, null, 2));
        } else {
          const d = await api('/adapters/' + key + '/open', { method: 'POST', body: '{}' });
          toast(d.detail || '已打开', d.ok ? 'success' : 'error');
        }
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = label;
        refreshHealth();
      }
      return;
    }
    const card = e.target.closest('.platform-card');
    if (card) selectPlatform(card.dataset.key);
  });

  $('actionChips').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    S.action = chip.dataset.action;
    localStorage.setItem(LS.action, S.action);
    renderActions();
  });

  $('targets').addEventListener('input', () => {
    const n = $('targets').value.split(/\r?\n|，|,/).map((x) => x.trim()).filter(Boolean);
    const uniq = new Set(n);
    $('targetCount').textContent = uniq.size + ' 个';
    localStorage.setItem(LS.targets, $('targets').value);
  });

  $('message').addEventListener('input', () => {
    $('charCount').textContent = $('message').value.length + ' 字';
    localStorage.setItem(LS.message, $('message').value);
  });

  $('clearTargets').addEventListener('click', () => {
    $('targets').value = '';
    $('targetCount').textContent = '0 个';
    localStorage.removeItem(LS.targets);
  });

  $('planBtn').addEventListener('click', doPlan);

  $('approveAll').addEventListener('click', () => {
    if (S.busy) return;
    if (!confirm('批准该任务的全部待审步骤？')) return;
    jobAction('approve', { all: true });
  });

  $('rejectAll').addEventListener('click', () => {
    if (!confirm('拒绝全部步骤？')) return;
    jobAction('reject', { all: true });
  });

  $('runBtn').addEventListener('click', () => {
    if (!S.job) return;
    const sim = S.settings ? !!S.settings.simulation : true;
    const msg = sim
      ? '当前是【演练模式】，不会真的操作微信/浏览器。\n\n开始执行？'
      : '将真实操作平台：' + S.job.platform_name + ' · ' + S.job.action_label + '\n\n确定开始？';
    if (!confirm(msg)) return;
    jobAction('run');
  });

  $('stopBtn').addEventListener('click', () => {
    if (!confirm('停止当前任务？剩余步骤会标记为跳过。')) return;
    jobAction('stop');
  });

  $('stepList').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-step-act]');
    if (!btn) return;
    const act = btn.dataset.stepAct;
    jobAction(act, { step_ids: [btn.dataset.id] });
  });

  $('panicBtn').addEventListener('click', () => {
    if (S.panic) { setPanic(false); return; }
    if (confirm('急停会立刻中止所有正在运行的任务，并阻止新任务启动。\n\n确定急停？')) setPanic(true);
  });
  $('panicRelease').addEventListener('click', () => setPanic(false));

  $('modeSwitch').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (!b) return;
    if (b.dataset.mode === 'auto' && !confirm('自动执行模式会在批准后立即连续执行，不再逐条确认。\n\n确定切换？')) return;
    patchSettings({ mode: b.dataset.mode });
  });

  $('simToggle').addEventListener('change', (e) => {
    patchSettings({ simulation: e.target.checked });
  });

  $('refreshHealth').addEventListener('click', refreshHealth);

  $('clearLog').addEventListener('click', () => { $('logBody').innerHTML = ''; });

  $('modalClose').addEventListener('click', () => $('modal').classList.add('hidden'));
  $('modal').addEventListener('click', (e) => {
    if (e.target === $('modal')) $('modal').classList.add('hidden');
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') $('modal').classList.add('hidden');
  });
}

/* ---------------------------------------------------------------- 启动 */
async function boot() {
  bind();

  const savedPlatform = localStorage.getItem(LS.platform);
  const savedAction = localStorage.getItem(LS.action);
  if (localStorage.getItem(LS.targets)) $('targets').value = localStorage.getItem(LS.targets);
  if (localStorage.getItem(LS.message)) $('message').value = localStorage.getItem(LS.message);
  $('message').dispatchEvent(new Event('input'));
  $('targets').dispatchEvent(new Event('input'));

  await loadSettings();
  await refreshHealth();

  const list = platforms();
  if (savedPlatform && list.some((p) => p.key === savedPlatform)) S.platform = savedPlatform;
  else if (list.length) S.platform = list[0].key;
  if (savedAction) S.action = savedAction;

  renderTop();
  renderPlatforms();
  renderActions();

  // 刷新页面后恢复上次的任务，避免计划丢失
  const savedJob = localStorage.getItem('dac.job');
  if (savedJob) {
    try {
      const d = await api('/jobs/' + savedJob);
      if (d.job) S.job = d.job;
    } catch (e) {
      localStorage.removeItem('dac.job');
    }
  }

  renderJob();

  log('info', '', '控制台已就绪，共 ' + list.length + ' 个平台');
  S.timer = setInterval(() => { tick().catch(() => {}); }, 1500);
  tick().catch(() => {});
}

document.addEventListener('DOMContentLoaded', boot);
