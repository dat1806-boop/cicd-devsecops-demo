const toast = document.getElementById('toast');
let toastTimer;
function showToast(message, error=false) {
  toast.textContent = message;
  toast.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = 'toast'; }, 3500);
}
async function api(url, options={}) {
  const response = await fetch(url, {
    headers: {'Content-Type': 'application/json', ...(options.headers || {})},
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.message || `HTTP ${response.status}`);
  return data;
}
function setState(step, status, label, output) {
  const article = document.querySelector(`[data-step="${step}"]`);
  if (!article) return;
  const badge = article.querySelector('.step-state');
  badge.className = `step-state state-${status}`;
  badge.textContent = label;
  if (output !== undefined) {
    const node = document.getElementById(`${step}-output`);
    if (node) node.textContent = output;
  }
}
function outputForCommand(item) {
  return `$ ${item.command}\nExit code: ${item.exit_code}\n${item.output || ''}`;
}
function applyState(state) {
  const tests = state.tests || {};
  setState('tests', tests.status || 'not_run', tests.status === 'success' ? 'ĐẠT' : tests.status === 'failure' ? 'THẤT BẠI' : 'CHƯA CHẠY');
  if (tests.commands) document.getElementById('tests-output').textContent = tests.commands.map(outputForCommand).join('\n\n');
  else document.getElementById('tests-output').innerHTML = '<span class="muted">Chưa có log. Nhấn nút để chạy kiểm thử thật.</span>';
  const build = state.build || {};
  setState('build', build.status || 'not_run', build.status === 'success' ? 'ĐÃ BUILD' : build.status === 'failure' ? 'THẤT BẠI' : 'CHƯA BUILD');
  if (build.command) document.getElementById('build-output').textContent = outputForCommand(build.command) + (build.image_id ? `\nImage ID: ${build.image_id}` : '');
  else document.getElementById('build-output').innerHTML = '<span class="muted">Chưa có Docker image.</span>';
  const image = state.image;
  document.getElementById('image-tag').textContent = image ? image.tag : 'Chưa tạo image';
  document.getElementById('image-id').textContent = image ? image.id : 'Sau khi build thành công, Image ID sẽ xuất hiện ở đây.';
  const envs = state.environments || {};
  ['dev', 'staging', 'production'].forEach(name => {
    const env = envs[name] || {};
    const status = env.status || 'not_deployed';
    const label = status === 'success' ? 'Đang chạy' : 'Chưa chạy';
    document.getElementById(`env-${name}`).textContent = label;
    const output = env.url ? `Container: ${env.container}\nURL: ${env.url}\nImage ID: ${env.image_id}\nHealth check: HTTP 200 /health` : '<span class="muted">Chưa có container ở môi trường này.</span>';
    setState(name, status === 'success' ? 'success' : 'not_run', status === 'success' ? 'ĐÃ DEPLOY' : 'CHƯA DEPLOY', output);
    const link = document.getElementById(`${name}-link`);
    link.hidden = !env.url;
    if (env.url) link.href = env.url;
  });
  document.getElementById('build-image').disabled = tests.status !== 'success';
  document.getElementById('deploy-dev').disabled = !image;
  document.getElementById('deploy-staging').disabled = !image || envs.dev?.status !== 'success';
  const stagingReady = envs.staging?.status === 'success';
  document.getElementById('approve-production').disabled = !stagingReady || state.production_approved;
  document.getElementById('deploy-production').disabled = !stagingReady || !state.production_approved;
  if (state.production_approved) document.getElementById('production-output').textContent = 'Đã phê duyệt tại LOCAL. Có thể triển khai production mô phỏng.';
}
async function refreshState() {
  try { const state = await api('/api/lab/status'); applyState(state); }
  catch (error) { showToast(error.message, true); }
}
async function runAction(button, endpoint, successMessage) {
  button.disabled = true;
  const oldText = button.textContent;
  button.textContent = 'Đang thực hiện…';
  try {
    const result = await api(endpoint, {method: 'POST', body: '{}'});
    showToast(successMessage || result.message || 'Hoàn tất.');
    await refreshState();
    return result;
  } catch (error) {
    showToast(error.message, true);
    await refreshState();
    return null;
  } finally {
    button.textContent = oldText;
    await refreshState();
  }
}
document.getElementById('run-tests').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true; button.textContent = 'Đang chạy Flake8 và Pytest…';
  try {
    const result = await api('/api/lab/tests', {method: 'POST', body: '{}'});
    await refreshState();
    showToast(result.success ? 'Kiểm thử đạt. Có thể chuyển sang Docker build.' : 'Kiểm thử thất bại. Build bị khóa.', !result.success);
  } catch (error) { showToast(error.message, true); await refreshState(); }
  finally { button.textContent = '▶ Chạy kiểm thử tự động'; await refreshState(); }
});
document.getElementById('build-image').addEventListener('click', event => runAction(event.currentTarget, '/api/lab/build', 'Docker image đã được build.'));
document.getElementById('deploy-dev').addEventListener('click', event => runAction(event.currentTarget, '/api/lab/deploy/dev', 'DEV đã triển khai và health check đạt.'));
document.getElementById('deploy-staging').addEventListener('click', event => runAction(event.currentTarget, '/api/lab/deploy/staging', 'STAGING đã triển khai và health check đạt.'));
document.getElementById('approve-production').addEventListener('click', async event => {
  const button = event.currentTarget;
  if (!window.confirm('Bạn xác nhận phê duyệt phát hành PRODUCTION trong bài demo LOCAL?')) return;
  await runAction(button, '/api/lab/approve-production', 'Đã phê duyệt production.');
});
document.getElementById('deploy-production').addEventListener('click', event => runAction(event.currentTarget, '/api/lab/deploy/production', 'PRODUCTION đã triển khai và health check đạt.'));
document.getElementById('reset-lab').addEventListener('click', async event => {
  if (!window.confirm('Đặt lại trạng thái và dừng các container DEV/STAGING/PRODUCTION do demo tạo?')) return;
  await runAction(event.currentTarget, '/api/lab/reset', 'Đã đặt lại phòng CI/CD.');
});

document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', async () => {
  const box = document.getElementById('scenario-result');
  try {
    const item = await api(`/api/lab/scenario/${button.dataset.scenario}`);
    box.hidden = false; box.replaceChildren();
    const title = document.createElement('h3'); title.textContent = `${item.title} · ${item.tool}`;
    const result = document.createElement('div'); result.className = 'result-line'; result.textContent = item.result;
    const detail = document.createElement('p'); detail.textContent = item.detail;
    const effect = document.createElement('p'); effect.textContent = `Tác động: ${item.effect}`;
    const note = document.createElement('p'); note.textContent = `Nguồn: ${item.source} Đây là minh họa theo kết quả báo cáo, không chạy scanner thật.`;
    box.append(title, result, detail, effect, note);
  } catch (error) { showToast(error.message, true); }
}));

document.getElementById('dispatch-github').addEventListener('click', async event => {
  const button = event.currentTarget;
  const branch = document.getElementById('github-branch').value;
  if (!window.confirm(`Gửi yêu cầu kích hoạt GitHub Actions thật trên nhánh ${branch}?`)) return;
  button.disabled = true; button.textContent = 'Đang gửi yêu cầu…';
  try {
    const result = await api('/api/github/dispatch', {method: 'POST', body: JSON.stringify({branch})});
    document.getElementById('github-output').textContent = result.message;
    showToast(result.message);
    await loadGithubRuns();
  } catch (error) {
    document.getElementById('github-output').textContent = error.message;
    showToast(error.message, true);
  } finally { button.disabled = false; button.textContent = '▶ Chạy workflow trên GitHub'; }
});
async function loadGithubRuns() {
  const box = document.getElementById('github-runs');
  box.textContent = 'Đang tải lịch sử từ GitHub…';
  try {
    const data = await api('/api/github/runs');
    box.replaceChildren();
    if (!data.runs.length) { box.textContent = 'Repository chưa có workflow run.'; return; }
    data.runs.slice(0, 6).forEach(run => {
      const row = document.createElement('div'); row.className = 'github-run';
      const icon = document.createElement('b'); icon.textContent = run.status !== 'completed' ? '◷' : run.conclusion === 'success' ? '✓' : '×';
      const title = document.createElement('span'); title.textContent = `#${run.run_number} · ${run.display_title}`;
      const branch = document.createElement('small'); branch.textContent = run.head_branch;
      const link = document.createElement('a'); link.href = run.html_url; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Mở ↗';
      row.append(icon, title, branch, link); box.append(row);
    });
  } catch (error) { box.textContent = error.message; }
}
document.getElementById('refresh-github').addEventListener('click', loadGithubRuns);
refreshState();
