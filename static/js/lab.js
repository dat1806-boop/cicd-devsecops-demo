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
  article.classList.toggle('has-error', status === 'failure');
  if (status === 'failure') {
    const log = article.querySelector('.log-details');
    if (log) log.open = true;
  }
  if (output !== undefined) {
    const node = document.getElementById(`${step}-output`);
    if (node) node.textContent = output;
  }
}
function outputForCommand(item) {
  return `$ ${item.command}\nExit code: ${item.exit_code}\n${item.output || ''}`;
}
// This board makes the actual results visible to the presenter.
function updateTeachingSummary(state) {
  const commands = state.tests?.commands || [];
  const pytest = commands.map(item => item.output || '').join('\n');
  const passed = pytest.match(/(\d+) passed\b/);
  const testsNode = document.getElementById('proof-tests');
  testsNode.textContent = state.tests?.status === 'success'
    ? `${passed ? passed[1] + ' bài test' : 'Kiểm thử'} đạt`
    : state.tests?.status === 'failure' ? 'Thất bại · Chặn build' : 'Chưa chạy';
  document.getElementById('proof-tests-detail').textContent = state.tests?.status === 'success'
    ? 'Flake8 đạt; Pytest hoàn tất bằng lệnh thật'
    : 'Flake8 + Pytest, chạy trong source WorkBoard';
  const img = state.image;
  document.getElementById('proof-image').textContent = img ? img.tag : 'Chưa build';
  document.getElementById('proof-image-detail').textContent = img
    ? `Image ID: ${img.id || 'không có'}` : 'Chờ Test đạt trước khi tạo image';
  const envs = state.environments || {};
  const intro = document.getElementById('proof-explanation');
  if (envs.production?.version === 'v1.1.0' && envs.production.status === 'success') {
    intro.textContent = 'Thưa thầy, Production vừa được cập nhật lên v1.1.0 sau phê duyệt. Bảng phân tích công việc mới đã có ở website Production.';
  } else if (envs.staging?.version === 'v1.1.0' && envs.production?.version === 'v1.0.0') {
    intro.textContent = 'Thưa thầy, DEV và STAGING đang dùng v1.1.0 nhưng Production vẫn là v1.0.0. Phiên bản cũ không bị thay đổi trước khi được phê duyệt.';
  } else if (envs.production?.version === 'v1.0.0') {
    intro.textContent = 'Đây là website Production v1.0.0 đang phục vụ từ container Docker. Khi phát hành bản nâng cấp, Production vẫn giữ bản cũ đến lúc phê duyệt.';
  } else if (state.tests?.status === 'failure') {
    intro.textContent = 'Kiểm thử phát hiện lỗi, nên Docker Build bị chặn. Đây là cơ chế fail-fast của quy trình CI.';
  } else if (envs.staging?.status === 'success') {
    intro.textContent = 'DEV và STAGING đã triển khai thành công. Em sẽ xác nhận health check rồi phê duyệt bản cập nhật Production.';
  } else if (envs.dev?.status === 'success') {
    intro.textContent = 'Container DEV đang chạy WorkBoard ở cổng 5101. Em sẽ kiểm tra /health và đưa cùng image lên STAGING.';
  } else if (img) {
    intro.textContent = 'Docker đã đóng gói WorkBoard thành image thật. Image ID ở đây là dấu vết để kiểm tra các môi trường đang chạy cùng sản phẩm đóng gói.';
  } else if (state.tests?.status === 'success') {
    intro.textContent = 'Bộ kiểm thử WorkBoard đã đạt, nên bước Build Docker được mở khóa. Nếu kiểm thử sai, quy trình sẽ dừng tại đây.';
  } else {
    intro.textContent = 'Thưa thầy, em sử dụng WorkBoard làm ứng dụng mẫu. Em sẽ lần lượt kiểm thử mã nguồn, build image và triển khai vào các container.';
  }
}
function setProofMessage(message) {
  document.getElementById('proof-feedback').textContent = message;
}
async function verifyDockerEvidence() {
  const button = document.getElementById('verify-docker');
  if (button.disabled) return;
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = 'Đang kiểm tra Docker Engine…';
  try {
    const data = await api('/api/lab/evidence');
    const envBox = document.getElementById('proof-environments');
    envBox.replaceChildren();
    let runningCount = 0;
    for (const [name, port] of [['dev', 5101], ['staging', 5102], ['production', 5103]]) {
      const item = data.environments?.[name] || {};
      const card = document.createElement('div');
      const title = document.createElement('b');
      title.textContent = `${name.toUpperCase()} · :${port}`;
      const state = document.createElement('p');
      if (item.running) runningCount++;
      state.className = item.healthy ? 'evidence-success' : 'evidence-error';
      state.textContent = item.healthy ? '✓ Container đang chạy · HTTP 200 /health'
        : item.running ? `⚠ Container đang chạy nhưng ${item.health_result}`
        : 'Chưa có container đang chạy';
      const info = document.createElement('p');
      info.textContent = `Version: ${item.version || '—'}\nTính năng: ${item.features || '—'}\nImage ID: ${item.image_id ? item.image_id.slice(0, 23) + '…' : '—'}\nCông việc: ${item.tasks ?? '—'}`;
      card.append(title, state, info);
      if (item.running && item.healthy) {
        const link = document.createElement('a');
        link.href = item.url;
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'evidence-link';
        link.textContent = `Mở WorkBoard ${name.toUpperCase()} ↗`;
        card.append(link);
      }
      envBox.append(card);
    }
    document.getElementById('proof-count').textContent = `${runningCount} / 3 đang chạy`;
    const imageLines = Object.entries(data.images || {}).map(([tag, item]) =>
      `${item.exists ? '✓' : '–'} ${tag}\n   ${item.exists ? item.image_id : 'Chưa có image'}`);
    document.getElementById('proof-images').textContent = imageLines.join('\n\n');
    setProofMessage(`Đã đối chiếu bằng Docker CLI và các API thực tế. ${data.checked_at}. ${data.source}`);
  } catch (error) {
    setProofMessage(`Chưa kiểm tra được Docker thật: ${error.message}`);
    document.getElementById('proof-count').textContent = 'Chưa xác minh';
    document.getElementById('proof-images').textContent = 'Docker chưa sẵn sàng.';
    document.querySelectorAll('#proof-environments > div').forEach(card => {
      const message = card.querySelector('p');
      if (message) message.textContent = 'Chưa xác minh. Kiểm tra Docker Desktop.';
      card.querySelectorAll('p:not(:first-of-type), a').forEach(node => node.remove());
    });
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}
function applyState(state) {
  updateTeachingSummary(state);
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
    const output = env.url ? `Phiên bản: ${env.version || 'n/a'}\nImage: ${env.image_tag || 'n/a'}\nContainer: ${env.container}\nURL: ${env.url}\nImage ID: ${env.image_id}\nHealth check: HTTP 200 /health` : 'Chưa có container ở môi trường này.';
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
  if (state.production_approved && envs.production?.status !== 'success') document.getElementById('production-output').textContent = 'Đã phê duyệt tại LOCAL. Có thể triển khai production mô phỏng.';
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
    await verifyDockerEvidence();
    return result;
  } catch (error) {
    showToast(error.message, true);
    await refreshState();
    await verifyDockerEvidence();
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
    await verifyDockerEvidence();
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
  if (!window.confirm('Đặt lại trạng thái và dừng các container DEV/STAGING/PRODUCTION? Dữ liệu SQLite trong Docker volumes và ứng dụng LOCAL vẫn được giữ lại.')) return;
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
document.getElementById('verify-docker').addEventListener('click', verifyDockerEvidence);
refreshState().then(verifyDockerEvidence);
