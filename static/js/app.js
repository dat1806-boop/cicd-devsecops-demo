const taskList = document.getElementById('task-list');
const toast = document.getElementById('toast');
let toastTimer;
function showToast(message, error=false) {
  toast.textContent = message;
  toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = 'toast'; }, 3000);
}
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
async function api(url, options={}) {
  const response = await fetch(url, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function renderTasks(tasks) {
  taskList.replaceChildren();
  const done = tasks.filter(t => t.status === 'done').length;
  document.getElementById('total-count').textContent = tasks.length;
  document.getElementById('done-count').textContent = done;
  document.getElementById('pending-count').textContent = tasks.length - done;
  document.getElementById('task-caption').textContent = `${tasks.length} công việc · dữ liệu được lưu trong SQLite`;
  const insightProgress = document.getElementById('insight-progress');
  if (insightProgress) {
    insightProgress.textContent = `${tasks.length ? Math.round(done * 100 / tasks.length) : 0}%`;
    ['high', 'normal', 'low'].forEach(priority => {
      const count = tasks.filter(task => task.priority === priority).length;
      document.getElementById(`priority-${priority}-count`).textContent = count;
      document.getElementById(`priority-${priority}-bar`).style.width =
        `${tasks.length ? count * 100 / tasks.length : 0}%`;
    });
  }
  if (!tasks.length) {
    taskList.append(el('div', 'empty-state', 'Chưa có công việc. Hãy tạo công việc đầu tiên ở khung bên phải.'));
    return;
  }
  tasks.forEach(task => {
    const card = el('article', `task-item${task.status === 'done' ? ' done' : ''}`);
    const check = el('button', 'task-check', task.status === 'done' ? '✓' : '');
    check.type = 'button';
    check.title = task.status === 'done' ? 'Đánh dấu chưa hoàn thành' : 'Đánh dấu hoàn thành';
    check.addEventListener('click', () => updateTask(task.id, {status: task.status === 'done' ? 'pending' : 'done'}));
    const main = el('div', 'task-main');
    main.append(el('b', '', task.title));
    if (task.description) main.append(el('p', '', task.description));
    const meta = el('div', 'task-meta');
    meta.append(el('span', 'tag', task.status === 'done' ? 'HOÀN THÀNH' : 'ĐANG THỰC HIỆN'));
    meta.append(el('span', `tag ${task.priority === 'high' ? 'tag-high' : task.priority === 'low' ? 'tag-low' : ''}`, `ƯU TIÊN ${task.priority.toUpperCase()}`));
    main.append(meta);
    const actions = el('div', 'task-actions');
    const edit = el('button', '', 'Sửa');
    edit.type = 'button';
    edit.addEventListener('click', async () => {
      const title = window.prompt('Nhập tên công việc mới:', task.title);
      if (title === null) return;
      const description = window.prompt('Nhập mô tả mới:', task.description || '');
      if (description === null) return;
      await updateTask(task.id, {title, description});
    });
    const remove = el('button', 'delete', 'Xóa');
    remove.type = 'button';
    remove.addEventListener('click', async () => {
      if (!window.confirm(`Bạn có chắc muốn xóa “${task.title}”?`)) return;
      try { await api(`/api/tasks/${task.id}`, {method: 'DELETE'}); showToast('Đã xóa công việc.'); await loadTasks(); }
      catch (error) { showToast(error.message, true); }
    });
    actions.append(edit, remove);
    card.append(check, main, actions);
    taskList.append(card);
  });
}
async function loadTasks() {
  try { const data = await api('/api/tasks'); renderTasks(data.tasks); }
  catch (error) { taskList.replaceChildren(el('div', 'empty-state', error.message)); showToast(error.message, true); }
}
async function updateTask(id, patch) {
  try { await api(`/api/tasks/${id}`, {method: 'PATCH', body: JSON.stringify(patch)}); showToast('Đã cập nhật công việc.'); await loadTasks(); }
  catch (error) { showToast(error.message, true); }
}
document.getElementById('task-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    title: form.elements.namedItem('title').value.trim(),
    description: form.elements.namedItem('description').value.trim(),
    priority: form.elements.namedItem('priority').value
  };
  try {
    await api('/api/tasks', {method: 'POST', body: JSON.stringify(payload)});
    form.reset(); showToast('Đã tạo công việc mới.'); await loadTasks();
  } catch (error) { showToast(error.message, true); }
});
document.getElementById('refresh-tasks').addEventListener('click', loadTasks);
loadTasks();


// Versioned local release: two prebuilt feature configurations, real Docker and CI.
const releaseForm = document.getElementById('release-form');
if (releaseForm) {
  const releaseResult = document.getElementById('release-result');
  const baselineButton = document.getElementById('prepare-baseline');
  const startButton = document.getElementById('start-release');
  const approveButton = document.getElementById('release-approve');
  const productionButton = document.getElementById('release-production');
  const oldProdLink = document.getElementById('baseline-prod-link');
  const productionLink = document.getElementById('release-prod-link');
  const names = ['dev', 'staging', 'production'];
  const releaseOutput = (lines, failed=false) => {
    releaseResult.textContent = lines.join('\n');
    releaseResult.classList.toggle('error-line', failed);
    releaseResult.classList.toggle('success-line', !failed);
  };
  function applyReleaseState(state) {
    const envs = state.environments || {};
    names.forEach(name => {
      const env = envs[name] || {};
      const ready = env.status === 'success';
      document.getElementById(`compare-${name}`).textContent =
        ready ? `${env.version || '?'} · đang chạy` : 'Chưa triển khai';
      document.getElementById(`compare-${name}-link`).hidden = !ready;
    });
    const oldVersion = envs.production?.version === 'v1.0.0';
    oldProdLink.hidden = !oldVersion;
    baselineButton.disabled = state.release?.status === 'running';
    const status = state.release?.status;
    const upgradeStatus = document.getElementById('edition-upgrade-status');
    if (upgradeStatus) {
      upgradeStatus.textContent = status === 'released' ? '(đã lên Production)' :
        status === 'approved' ? '(đã duyệt, chưa lên Production)' :
        status === 'awaiting_approval' ? '(đã lên DEV/STAGING)' :
        status === 'running' ? '(đang kiểm thử và triển khai)' :
        '(chưa phát hành)';
    }
    approveButton.disabled = status !== 'awaiting_approval';
    productionButton.disabled = status !== 'approved';
    productionLink.hidden = status !== 'released';
  }
  async function refreshReleaseState() {
    try { applyReleaseState(await api('/api/lab/status')); }
    catch (error) { showToast(error.message, true); }
  }
  baselineButton.addEventListener('click', async () => {
    if (!window.confirm('Chuẩn bị bản cũ v1.0.0 trên PRODUCTION :5103? Container production demo hiện tại sẽ được thay thế.')) return;
    baselineButton.disabled = true;
    releaseOutput(['Đang build image cũ v1.0.0…', 'Sau đó khởi chạy Production tại cổng 5103.']);
    try {
      const data = await api('/api/lab/baseline', {method:'POST', body:'{}'});
      releaseOutput([
        'BẢN CŨ ĐÃ CHẠY: v1.0.0', `PRODUCTION: ${data.production.url}`,
        `Image: ${data.baseline.image_tag}`, `Image ID: ${data.baseline.image_id}`,
        'Mở Production để xem bản cũ. Sau đó mới phát hành v1.1.0.'
      ]);
      showToast('Bản cũ v1.0.0 đã hoạt động trên Production.');
    } catch (error) {
      releaseOutput([`Không chuẩn bị được bản cũ: ${error.message}`], true);
      showToast(error.message, true);
    } finally { baselineButton.disabled = false; await refreshReleaseState(); }
  });
  releaseForm.addEventListener('submit', async event => {
    event.preventDefault();
    const version = releaseForm.elements.namedItem('version').value.trim();
    const description = releaseForm.elements.namedItem('description').value.trim();
    startButton.disabled = true;
    approveButton.disabled = true;
    productionButton.disabled = true;
    releaseOutput([
      'Đang chạy CI: Flake8 + Pytest…',
      'Kế tiếp: build image v1.1.0 (bật bảng phân tích), deploy DEV và STAGING.',
      'Production đang chạy v1.0.0 sẽ KHÔNG bị thay đổi trước phê duyệt.'
    ]);
    try {
      const data = await api('/api/lab/release/start', {
        method:'POST', body:JSON.stringify({version,description})
      });
      const log = (data.tests || []).map(item =>
        `${item.command} | Exit code: ${item.exit_code} | ${item.output}`
      ).join('\n');
      releaseOutput([
        `PHIÊN BẢN MỚI ${data.release.version}: ${data.release.description}`,
        'CI: PASSED', log, `IMAGE MỚI: ${data.image.tag}`,
        `Image ID: ${data.image.id}`, `DEV ${data.dev.version}: ${data.dev.url}`,
        `STAGING ${data.staging.version}: ${data.staging.url}`,
        'Mở DEV và STAGING: tính năng mới đã xuất hiện.',
        'Mở PRODUCTION: vẫn là bản cũ trước khi phê duyệt.'
      ]);
      showToast('Bản v1.1.0 đã lên DEV/STAGING. Production vẫn giữ bản cũ.');
    } catch (error) {
      releaseOutput([`Phát hành chưa thành công: ${error.message}`], true);
      showToast(error.message, true);
    } finally { startButton.disabled = false; await refreshReleaseState(); }
  });
  approveButton.addEventListener('click', async () => {
    if (!window.confirm('Đã kiểm tra tính năng mới ở STAGING? Đồng ý cho v1.1.0 lên Production?')) return;
    approveButton.disabled = true;
    try {
      const data = await api('/api/lab/approve-production', {
        method:'POST', body:'{}'
      });
      releaseOutput([data.message, 'Production vẫn là bản cũ cho tới lúc nhấn Cập nhật Production.']);
      showToast('Đã phê duyệt phát hành v1.1.0.');
    } catch (error) { showToast(error.message, true); }
    await refreshReleaseState();
  });
  productionButton.addEventListener('click', async () => {
    productionButton.disabled = true;
    try {
      const data = await api('/api/lab/deploy/production', {
        method:'POST', body:'{}'
      });
      releaseOutput([
        `PRODUCTION ĐÃ NÂNG CẤP: ${data.version}`, `URL: ${data.url}`,
        `Image ID: ${data.image_id}`, 'Mở lại Production để xem bảng phân tích mới.',
        'DEV, STAGING và PRODUCTION giờ dùng chung image v1.1.0.'
      ]);
      showToast('Production đã chuyển từ v1.0.0 lên v1.1.0.');
    } catch (error) {
      releaseOutput([`Không triển khai được Production: ${error.message}`], true);
      showToast(error.message, true);
    }
    await refreshReleaseState();
  });
  refreshReleaseState();
}
