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
    title: form.title.value.trim(),
    description: form.description.value.trim(),
    priority: form.priority.value
  };
  try {
    await api('/api/tasks', {method: 'POST', body: JSON.stringify(payload)});
    form.reset(); showToast('Đã tạo công việc mới.'); await loadTasks();
  } catch (error) { showToast(error.message, true); }
});
document.getElementById('refresh-tasks').addEventListener('click', loadTasks);
loadTasks();


// Versioned local release: real Flake8/Pytest, Docker build, DEV/STAGING deploy.
const releaseForm = document.getElementById('release-form');
if (releaseForm) {
  const releaseResult = document.getElementById('release-result');
  const startButton = document.getElementById('start-release');
  const approveButton = document.getElementById('release-approve');
  const productionButton = document.getElementById('release-production');
  const productionLink = document.getElementById('release-prod-link');
  const releaseOutput = (lines, failed=false) => {
    releaseResult.textContent = lines.join('\n');
    releaseResult.classList.toggle('error-line', failed);
    releaseResult.classList.toggle('success-line', !failed);
  };
  releaseForm.addEventListener('submit', async event => {
    event.preventDefault();
    const version = releaseForm.version.value.trim();
    const description = releaseForm.description.value.trim();
    startButton.disabled = true; approveButton.disabled = true; productionButton.disabled = true;
    productionLink.hidden = true;
    releaseOutput(['Đang chạy CI: Flake8 + Pytest…', 'Nếu kiểm thử đạt, Docker sẽ build image phiên bản mới và triển khai DEV → STAGING.']);
    try {
      const result = await api('/api/lab/release/start', {method:'POST', body:JSON.stringify({version, description})});
      const testLog = (result.tests || []).map(item => `${item.command}\nExit code: ${item.exit_code}\n${item.output}`).join('\n\n');
      releaseOutput([`PHÁT HÀNH ${result.release.version}: ${result.release.description}`, 'CI: PASSED', testLog, `DOCKER BUILD: ${result.image.tag}`, `Image ID: ${result.image.id}`, `DEV: ${result.dev.url} — HEALTHY`, `STAGING: ${result.staging.url} — HEALTHY`, 'Đang chờ bạn phê duyệt Production.']);
      approveButton.disabled = false;
    } catch (error) {
      releaseOutput([`PHÁT HÀNH THẤT BẠI: ${error.message}`, 'Kiểm tra Docker Desktop, Python environment và log phía trên nếu có.'], true);
      showToast(error.message, true);
    } finally { startButton.disabled = false; }
  });
  approveButton.addEventListener('click', async () => {
    approveButton.disabled = true;
    try { const result = await api('/api/lab/approve-production', {method:'POST', body:'{}'}); releaseOutput([result.message, 'Production đã được phê duyệt. Bạn có thể triển khai phiên bản này.']); productionButton.disabled = false; }
    catch (error) { approveButton.disabled = false; showToast(error.message, true); releaseOutput([error.message], true); }
  });
  productionButton.addEventListener('click', async () => {
    productionButton.disabled = true;
    try { const result = await api('/api/lab/deploy/production', {method:'POST', body:'{}'}); releaseOutput([`PRODUCTION: ${result.url} — HEALTHY`, `Image ID: ${result.image_id}`, 'Phát hành hoàn tất. Cả ba môi trường dùng cùng một Docker Image.']); productionLink.hidden = false; showToast('Đã triển khai Production thành công.'); }
    catch (error) { productionButton.disabled = false; showToast(error.message, true); releaseOutput([`Không triển khai được Production: ${error.message}`], true); }
  });
}
