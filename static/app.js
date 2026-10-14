document.querySelectorAll('[data-open]').forEach(button => button.addEventListener('click', () => document.getElementById(button.dataset.open).showModal()));
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
document.querySelectorAll('[data-autosubmit]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
document.querySelectorAll('[data-confirm]').forEach(form => form.addEventListener('submit', event => { if (!confirm(form.dataset.confirm)) event.preventDefault(); }));
document.querySelectorAll('[data-upload]').forEach(form => {
  const input = form.querySelector('input[type=file]'), zone = form.querySelector('.upload-zone');
  const refresh = () => { form.querySelector('.file-selection').textContent = Array.from(input.files).map(file => file.name).join(' · ') || '最多 20 个文件，单个文件不超过 25 MB。'; };
  input.addEventListener('change', refresh);
  ['dragover', 'dragenter'].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add('dragging'); }));
  zone.addEventListener('dragleave', () => zone.classList.remove('dragging'));
  zone.addEventListener('drop', event => { event.preventDefault(); zone.classList.remove('dragging'); input.files = event.dataTransfer.files; refresh(); });
  form.addEventListener('submit', () => { const button = form.querySelector('button[type=submit], button.primary'); button.disabled = true; button.textContent = '正在上传…'; });
});
let baseline;
if (document.querySelector('.sidebar')) setInterval(async () => {
  if (document.hidden || document.querySelector('dialog[open]') || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
  try { const response = await fetch('/status/'); if (!response.ok) return; const state = await response.json(); const revision = JSON.stringify(state.revision); const displayed = document.querySelector('[data-document-id]'); const current = displayed && state.revision.find(([id]) => id === displayed.dataset.documentId); if ((baseline !== undefined && baseline !== revision) || (current && current[1] !== displayed.dataset.documentStatus)) location.reload(); baseline = revision; } catch (_) { /* A disconnected local service can be retried on the next tick. */ }
}, 5000);
