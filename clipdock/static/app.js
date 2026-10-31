const $ = id => document.getElementById(id);
const activeStates = new Set(['queued','starting','downloading','processing']);
let config, preview, jobs = [], filter = 'all', timer, renderKey = '', online = true;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#${name}"/></svg>`;
function duration(seconds) { if (!Number.isFinite(seconds)) return ''; const minutes = Math.floor(seconds / 60); return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2,'0')}`; }
function bytes(value) { if (!value) return ''; return value > 1048576 ? `${(value/1048576).toFixed(1)} MB` : `${Math.round(value/1024)} KB`; }
function thumbnail(value) { try { const url = new URL(value); return url.protocol === 'https:' ? url.href : ''; } catch { return ''; } }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(timer); timer = setTimeout(() => $('toast').hidden = true, 4500); }
function showError(message) { $('form-error').textContent = message; $('form-error').hidden = !message; }
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-ClipDock-Token':config?.token || ''},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong. Please try again.');
  return data;
}
async function initialize() {
  try {
    config = await api('/api/config');
    $('engine-label').textContent = `ClipDock / Engine ${config.engine}`;
    if (!config.ffmpeg || !config.node) { $('dependency-warning').hidden = false; $('dependency-warning').textContent = `Missing ${[!config.ffmpeg && 'FFmpeg',!config.node && 'Node.js'].filter(Boolean).join(' and ')}. Check README.txt, then restart the app.`; }
    await refresh();
  } catch (error) { showError('Could not connect to ClipDock. Start the app, then refresh this page.'); }
}
$('link-form').addEventListener('submit', async event => {
  event.preventDefault(); showError(''); preview = null; $('video-preview').hidden = true;
  const button = $('inspect-button'); button.disabled = true; button.textContent = 'Finding…'; button.classList.add('spin');
  const submittedUrl = $('url').value.trim();
  try {
    const result = await api('/api/inspect', {url: submittedUrl});
    if ($('url').value.trim() !== submittedUrl) return;
    preview = result;
    $('preview-title').textContent = preview.title;
    $('preview-platform').textContent = preview.platform;
    $('preview-details').textContent = [preview.creator,duration(preview.duration)].filter(Boolean).join(' · ');
    const image = thumbnail(preview.thumbnail); $('preview-img').hidden = !image; if (image) $('preview-img').src = image;
    $('video-preview').hidden = false;
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; button.innerHTML = `Find video ${icon('arrow')}`; button.classList.remove('spin'); }
});
$('url').addEventListener('input', () => { preview = null; $('video-preview').hidden = true; showError(''); });
function updateFormat() {
  const format = $('format').value;
  $('video-quality-field').hidden = format !== 'mp4';
  $('audio-quality-field').hidden = format !== 'mp3';
  $('source-quality-field').hidden = format !== 'audio';
  $('quality-hint').textContent = format === 'mp3'
    ? 'MP3 defaults to 320 kbps. A higher bitrate cannot restore quality missing from the source.'
    : format === 'audio' ? 'Keeps the best source audio in its native codec, usually M4A or Opus, avoiding an extra MP3 conversion.'
    : 'Prefers your chosen resolution; falls back to the smallest available if needed. Works with portrait videos too.';
}
$('format').addEventListener('change', updateFormat);
$('download-button').addEventListener('click', async () => {
  if (!preview) return;
  const button = $('download-button'); button.disabled = true; showError('');
  try {
    await api('/api/jobs', {url:preview.url,format:$('format').value,quality:$('quality').value,audio_bitrate:$('audio-bitrate').value});
    filter = 'all'; updateFilters(); toast('Added to your downloads.'); await refresh();
    $('library-heading').scrollIntoView({behavior:'smooth',block:'center'});
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; }
});
function updateFilters() { document.querySelectorAll('.filter').forEach(button => {button.classList.toggle('active',button.dataset.filter === filter);button.setAttribute('aria-pressed',String(button.dataset.filter === filter));}); }
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; updateFilters(); renderKey = ''; render(); }));
function render() {
  $('job-count').textContent = jobs.length;
  $('active-count').textContent = jobs.filter(job => activeStates.has(job.status)).length;
  const visible = jobs.filter(job => filter === 'all' || (filter === 'active' ? activeStates.has(job.status) : job.status === 'complete'));
  const key = JSON.stringify(visible);
  if (key === renderKey) return;
  renderKey = key;
  $('empty').hidden = visible.length > 0;
  $('empty').querySelector('h3').textContent = filter === 'all' ? 'Your next good find belongs here.' : filter === 'active' ? 'Nothing in the queue.' : 'Your finished downloads will appear here.';
  $('empty').querySelector('p').textContent = filter === 'active' ? 'Add another link whenever inspiration strikes.' : 'Paste a link above to save a video.';
  const statusNames = {queued:'Queued',starting:'Reading video…',downloading:'Downloading',processing:'Joining / converting…',complete:'Saved',error:'Could not save',cancelled:'Cancelled',interrupted:'Interrupted'};
  $('jobs').innerHTML = visible.map(job => {
    const active = activeStates.has(job.status), done = job.status === 'complete';
    const image = thumbnail(job.thumbnail);
    const formatLabel = job.format === 'audio' ? 'Source audio' : job.format.toUpperCase();
    const qualityLabel = job.format === 'mp3' ? `${job.audio_bitrate || '192'} kbps` : job.format === 'audio' ? 'Original codec' : job.quality === 'best' ? 'Best quality' : `Prefer ${job.quality}p`;
    const detail = [job.platform,formatLabel,qualityLabel,done ? bytes(job.size) : duration(job.duration)].filter(Boolean).join(' · ');
    return `<article class="job ${escapeHtml(job.status)}">${image ? `<img class="job-thumb" src="${escapeHtml(image)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : `<div class="job-thumb empty-icon">${icon(job.format === 'mp3' ? 'music' : 'play')}</div>`}<div class="job-main"><h3 class="job-title">${escapeHtml(job.title)}</h3><p class="job-meta">${escapeHtml(detail)}</p>${active ? `<div class="progress"><progress max="100" value="${Number(job.percent)||0}" aria-label="Download progress"></progress></div><p class="job-meta">${escapeHtml([job.speed ? `${bytes(job.speed)}/s` : '',job.eta ? `${duration(job.eta)} left` : ''].filter(Boolean).join(' · '))}</p>` : ''}${job.error ? `<p class="job-error">${escapeHtml(job.error)}</p>` : ''}</div><span class="job-status">${escapeHtml(statusNames[job.status] || job.status)}${job.status === 'downloading' && job.percent != null ? `<br>${job.percent}%` : ''}</span><div class="job-actions">${done ? `<a href="/api/jobs/${job.id}/file" download aria-label="Save ${escapeHtml(job.title)}">${icon('download')} Save copy</a>` : active ? `<button data-cancel="${job.id}" aria-label="Cancel download">${icon('close')}</button>` : `<button data-retry="${job.id}">Retry</button>`}</div></article>`;
  }).join('');
}
$('jobs').addEventListener('click', async event => {
  const cancel = event.target.closest('[data-cancel]'), retry = event.target.closest('[data-retry]');
  if (!cancel && !retry) return;
  const button = cancel || retry; button.disabled = true;
  try {
    if (cancel) await api(`/api/jobs/${cancel.dataset.cancel}/cancel`, {});
    else { const job = jobs.find(item => item.id === retry.dataset.retry); await api('/api/jobs', {url:job.url,format:job.format,quality:job.quality,audio_bitrate:job.audio_bitrate || '192'}); toast('Added to the queue again.'); }
    await refresh();
  } catch (error) { toast(error.message); button.disabled = false; }
});
$('open-folder').addEventListener('click', async () => { try { const result = await api('/api/open-folder', {}); if (!result.ok) toast(result.path); } catch (error) { toast(error.message); } });
async function refresh() { try { jobs = await api('/api/jobs'); online = true; render(); } catch { if (online) toast('Connection lost. Restart ClipDock or refresh this page.'); online = false; } }
updateFilters(); initialize(); setInterval(refresh, 1500);
