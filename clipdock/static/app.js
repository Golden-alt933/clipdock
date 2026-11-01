const $ = id => document.getElementById(id);
const activeStates = new Set(['queued','starting','downloading','processing']);
let config, preview, jobs = [], filter = 'all', query = '', timer, renderKey = '', online = true;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#${name}"/></svg>`;
function duration(seconds) { if (!Number.isFinite(seconds)) return ''; const minutes = Math.floor(seconds / 60); return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2,'0')}`; }
function bytes(value) { if (!value) return ''; return value > 1048576 ? `${(value/1048576).toFixed(1)} MB` : `${Math.round(value/1024)} KB`; }
function thumbnail(value) { try { const url = new URL(value); return url.protocol === 'https:' ? url.href : ''; } catch { return ''; } }
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(timer); timer = setTimeout(() => $('toast').hidden = true, 4500); }
function showError(message) { $('form-error').textContent = message; $('form-error').hidden = !message; }
function captureStatus(message) { $('capture-status').textContent = message; }
function connectionStatus(connected) {
  online = connected;
  $('mode-label').textContent = connected ? (config?.hosted ? 'Online workspace' : 'Running on your computer') : 'Workspace disconnected';
  $('mode-label').closest('.local-badge').classList.toggle('offline', !connected);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-ClipDock-Token':config?.token || ''},body:JSON.stringify(body)});
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('The service is waking up or is temporarily unavailable. Try again in a moment.');
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong. Please try again.');
  return data;
}
async function initialize() {
  try {
    config = await api('/api/config');
    connectionStatus(true);
    if (config.hosted) {
      $('open-folder').hidden = true;
      $('privacy-label').textContent = 'No installation needed';
      $('hosted-limits').hidden = false;
      $('hosted-limits').textContent = 'Free service: videos up to 10 minutes / 100 MB. Download your file within 1 hour. The service may need a minute to wake up.';
    }
    $('engine-label').textContent = `ClipDock / Engine ${config.engine}`;
    if (!config.ffmpeg || !config.node) { $('dependency-warning').hidden = false; $('dependency-warning').textContent = `Missing ${[!config.ffmpeg && 'FFmpeg',!config.node && 'Node.js'].filter(Boolean).join(' and ')}. Check the setup guide, then restart ClipDock.`; }
    await refresh();
  } catch (error) { connectionStatus(false); showError('Could not connect to ClipDock. Refresh this page in a moment.'); }
}
$('link-form').addEventListener('submit', async event => {
  event.preventDefault(); showError(''); preview = null; $('video-preview').hidden = true;
  const button = $('inspect-button'); button.disabled = true; button.textContent = 'Reading your link…'; button.classList.add('spin');
  captureStatus('READING SOURCE'); $('link-form').setAttribute('aria-busy', 'true');
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
    captureStatus('SOURCE FOUND'); updateFormat();
  } catch (error) { if ($('url').value.trim() === submittedUrl) { showError(error.message); captureStatus('CHECK YOUR LINK'); } }
  finally { button.disabled = false; button.innerHTML = `<span>Find video</span>${icon('arrow')}`; button.classList.remove('spin'); $('link-form').setAttribute('aria-busy', 'false'); }
});
$('url').addEventListener('input', () => { preview = null; $('video-preview').hidden = true; showError(''); captureStatus($('url').value.trim() ? 'LINK READY' : 'READY FOR A LINK'); });
$('paste-button').addEventListener('click', async () => {
  try {
    if (!navigator.clipboard?.readText) throw new Error('Clipboard unavailable');
    const text = (await navigator.clipboard.readText()).trim();
    if (!text) { toast('Your clipboard is empty. Copy a video link first.'); return; }
    $('url').value = text; $('url').dispatchEvent(new Event('input')); $('url').focus();
    toast('Link pasted. Find the video when you are ready.');
  } catch { $('url').focus(); toast('Paste directly into the link field with Ctrl+V or ⌘V.'); }
});
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
    filter = 'all'; query = ''; $('library-search').value = ''; updateFilters(); toast('Added to your downloads.'); await refresh();
    $('library-heading').scrollIntoView({behavior:'smooth',block:'center'});
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; }
});
function updateFilters() { document.querySelectorAll('.filter').forEach(button => {button.classList.toggle('active',button.dataset.filter === filter);button.setAttribute('aria-pressed',String(button.dataset.filter === filter));}); }
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; updateFilters(); renderKey = ''; render(); }));
$('library-search').addEventListener('input', () => { query = $('library-search').value.trim().toLowerCase(); renderKey = ''; render(); });
function render() {
  $('job-count').textContent = jobs.length;
  $('active-count').textContent = jobs.filter(job => activeStates.has(job.status)).length;
  const visible = jobs.filter(job => (filter === 'all' || (filter === 'active' ? activeStates.has(job.status) : job.status === 'complete')) && (!query || [job.title, job.platform, job.format === 'audio' ? 'source audio' : job.format].join(' ').toLowerCase().includes(query)));
  const key = JSON.stringify(visible);
  if (key === renderKey) return;
  renderKey = key;
  $('empty').hidden = visible.length > 0;
  $('empty').querySelector('h3').textContent = query ? 'No matching clips. Keep looking.' : filter === 'all' ? 'A little empty. A lot of possibility.' : filter === 'active' ? 'All quiet on the timeline.' : 'Your finished files will land here.';
  $('empty').querySelector('p').textContent = query ? 'Try a title, a platform, or another format.' : filter === 'active' ? 'Your next download will appear here while it is in progress.' : 'Drop a link above. Keep something worth creating with.';
  $('empty').querySelector('.empty-action').hidden = Boolean(query);
  const statusNames = {queued:'Queued',starting:'Reading video…',downloading:'Downloading',processing:'Joining / converting…',complete:'Saved',error:'Could not save',cancelled:'Cancelled',interrupted:'Interrupted'};
  $('jobs').innerHTML = visible.map(job => {
    const active = activeStates.has(job.status), done = job.status === 'complete';
    const image = thumbnail(job.thumbnail);
    const formatLabel = job.format === 'audio' ? 'Source audio' : job.format.toUpperCase();
    const qualityLabel = job.format === 'mp3' ? `${job.audio_bitrate || '192'} kbps` : job.format === 'audio' ? 'Original codec' : job.quality === 'best' ? 'Best quality' : `Prefer ${job.quality}p`;
    const detail = [job.platform,formatLabel,qualityLabel,done ? bytes(job.size) : duration(job.duration)].filter(Boolean).join(' · ');
    return `<article class="job ${escapeHtml(job.status)}">${image ? `<img class="job-thumb" src="${escapeHtml(image)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : `<div class="job-thumb empty-icon">${icon(job.format === 'mp4' ? 'play' : 'music')}</div>`}<div class="job-main"><h3 class="job-title">${escapeHtml(job.title)}</h3><p class="job-meta">${escapeHtml(detail)}</p>${active ? `<div class="progress"><progress max="100" value="${Number(job.percent)||0}" aria-label="Download progress"></progress></div><p class="job-meta">${escapeHtml([job.speed ? `${bytes(job.speed)}/s` : '',job.eta ? `${duration(job.eta)} left` : ''].filter(Boolean).join(' · '))}</p>` : ''}${job.error ? `<p class="job-error">${escapeHtml(job.error)}</p>` : ''}</div><span class="job-status">${escapeHtml(statusNames[job.status] || job.status)}${job.status === 'downloading' && job.percent != null ? `<br>${job.percent}%` : ''}</span><div class="job-actions">${done ? `<a href="/api/jobs/${job.id}/file" download aria-label="Save ${escapeHtml(job.title)}">${icon('download')} ${config?.hosted ? 'Save file' : 'Save copy'}</a>` : active ? `<button data-cancel="${job.id}" aria-label="Cancel download">${icon('close')}</button>` : `<button data-retry="${job.id}">Retry</button>`}</div></article>`;
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
async function refresh() { try { jobs = await api('/api/jobs'); if (config) connectionStatus(true); render(); } catch { if (online) toast('Connection lost. Restart ClipDock or refresh this page.'); connectionStatus(false); } }
async function poll() {
  await refresh();
  const active = jobs.some(job => activeStates.has(job.status));
  const delay = document.hidden ? 30000 : config?.hosted ? (active ? 2000 : 15000) : 1500;
  setTimeout(poll, delay);
}
function updateNavigation() {
  const target = location.hash === '#library' ? '#library' : '#workspace';
  document.querySelectorAll('.rail-link').forEach(link => {
    const selected = link.getAttribute('href') === target;
    link.classList.toggle('selected', selected);
    if (selected) link.setAttribute('aria-current', 'location'); else link.removeAttribute('aria-current');
  });
}
window.addEventListener('hashchange', updateNavigation);
function initializeAmbientResponse() {
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const scene = document.querySelector('.sky-scene');
  const image = document.querySelector('.scene-image');
  const details = document.querySelector('.scene-details');
  const eyes = [...document.querySelectorAll('.eye-iris')].map(element => ({
    element, x:Number(element.dataset.eyeX), y:Number(element.dataset.eyeY)
  }));
  const gazeTravel = {x:4, y:1.8};
  const gaze = {current:{x:0,y:0}, target:{x:0,y:0}};
  const gazeOrigin = {
    x:eyes.reduce((sum,eye) => sum + eye.x, 0) / (eyes.length || 1),
    y:eyes.reduce((sum,eye) => sum + eye.y, 0) / (eyes.length || 1)
  };
  eyes.forEach(eye => { eye.element.style.transformOrigin = `${eye.x}px ${eye.y}px`; });
  const states = [...document.querySelectorAll('.floating-object')].map((element, index) => ({
    element, layer: element.querySelector('.object-response'), depth: [1, .8, .65][index] || 1,
    current: {x:0, y:0, rx:0, ry:0, glow:0}, target: {x:0, y:0, rx:0, ry:0, glow:0}
  }));
  let paused = true, pointer = null, gazePointer = null, portrait = null, dirty = false, frame = null, previousTime = 0;
  function alignPortrait() {
    if (!image.naturalWidth || !image.naturalHeight) return;
    const box = image.getBoundingClientRect(), host = scene.getBoundingClientRect();
    const scale = Math.max(box.width / image.naturalWidth, box.height / image.naturalHeight);
    const [positionX, positionY] = getComputedStyle(image).objectPosition.split(' ').map(value => Number.parseFloat(value) / 100);
    const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
    const left = box.x - host.x + (box.width - width) * (Number.isFinite(positionX) ? positionX : .5);
    const top = box.y - host.y + (box.height - height) * (Number.isFinite(positionY) ? positionY : .5);
    portrait = {left:left + host.x, top:top + host.y, scale};
    Object.assign(details.style, {left:`${left}px`, top:`${top}px`, width:`${width}px`, height:`${height}px`});
    details.classList.add('is-aligned');
    dirty = true; schedule();
  }
  function reset() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null; previousTime = 0; pointer = null; gazePointer = null; dirty = false;
    states.forEach(state => {
      for (const key of Object.keys(state.current)) state.current[key] = state.target[key] = 0;
      state.layer.style.removeProperty('transform');
      state.layer.style.removeProperty('--pointer-glow');
    });
    gaze.current.x = gaze.current.y = gaze.target.x = gaze.target.y = 0;
    eyes.forEach(eye => eye.element.style.removeProperty('transform'));
  }
  function schedule() {
    if (!paused && finePointer.matches && frame === null) frame = requestAnimationFrame(animate);
  }
  function animate(time) {
    frame = null;
    if (paused || !finePointer.matches) return;
    if (dirty) {
      // Read all object bounds before writing transforms to keep layout work batched.
      const bounds = states.map(state => state.element.getBoundingClientRect());
      states.forEach((state, index) => {
        const box = bounds[index];
        const dx = pointer ? pointer.x - box.x - box.width / 2 : 0;
        const dy = pointer ? pointer.y - box.y - box.height / 2 : 0;
        const distance = Math.hypot(dx, dy);
        const influence = pointer ? Math.max(0, 1 - distance / 260) : 0;
        const nx = dx / (distance || 1), ny = dy / (distance || 1);
        const parallaxX = pointer ? (pointer.x / innerWidth - .5) * 7 * state.depth : 0;
        const parallaxY = pointer ? (pointer.y / innerHeight - .5) * 5 * state.depth : 0;
        Object.assign(state.target, {
          x: parallaxX - nx * influence * 26,
          y: parallaxY - ny * influence * 22,
          rx: ny * influence * 11, ry: -nx * influence * 14, glow: influence
        });
      });
      // A shared, distant focus avoids cross-eyed aiming at the screen plane.
      const dx = gazePointer && portrait ? gazePointer.x - portrait.left - gazeOrigin.x * portrait.scale : 0;
      const dy = gazePointer && portrait ? gazePointer.y - portrait.top - gazeOrigin.y * portrait.scale : 0;
      const horizontal = Math.tanh(dx / Math.max(480, innerWidth * .55));
      const vertical = Math.tanh(dy / Math.max(320, innerHeight * .55));
      // Independent limits prevent vertical tracking from pulling the gaze sideways.
      gaze.target.x = horizontal;
      gaze.target.y = vertical;
      dirty = false;
    }
    const elapsed = Math.min(40, previousTime ? time - previousTime : 16);
    const blend = 1 - Math.exp(-elapsed / 90);
    const gazeBlend = 1 - Math.exp(-elapsed / 60);
    previousTime = time;
    let unsettled = false;
    states.forEach(state => {
      for (const key of Object.keys(state.current)) {
        const difference = state.target[key] - state.current[key];
        if (Math.abs(difference) > .005) { state.current[key] += difference * blend; unsettled = true; }
        else state.current[key] = state.target[key];
      }
      const {x,y,rx,ry,glow} = state.current;
      state.layer.style.transform = `translate3d(${x.toFixed(3)}px, ${y.toFixed(3)}px, 0) rotateX(${rx.toFixed(3)}deg) rotateY(${ry.toFixed(3)}deg)`;
      state.layer.style.setProperty('--pointer-glow', glow.toFixed(3));
    });
    for (const key of ['x','y']) {
      const difference = gaze.target[key] - gaze.current[key];
      if (Math.abs(difference) > .002) { gaze.current[key] += difference * gazeBlend; unsettled = true; }
      else gaze.current[key] = gaze.target[key];
    }
    const x = gaze.current.x * gazeTravel.x, y = gaze.current.y * gazeTravel.y;
    // One transform keeps both pupils synchronized in direction, travel, and easing.
    // Fixed eyelid masks provide occlusion while each iris keeps a stable height.
    const scaleX = 1 - .055 * Math.abs(gaze.current.x);
    const irisTransform = `translate(${x.toFixed(3)}px, ${y.toFixed(3)}px) scale(${scaleX.toFixed(4)}, 1)`;
    eyes.forEach(eye => { eye.element.style.transform = irisTransform; });
    if (unsettled) schedule(); else previousTime = 0;
  }
  window.addEventListener('pointermove', event => {
    if (paused || !finePointer.matches || event.pointerType === 'touch') return;
    pointer = gazePointer = {x:event.clientX, y:event.clientY}; dirty = true; schedule();
  }, {passive:true});
  function leave() { pointer = null; dirty = true; schedule(); }
  document.documentElement.addEventListener('pointerleave', leave);
  window.addEventListener('blur', leave);
  window.addEventListener('resize', alignPortrait, {passive:true});
  // Media-query crop changes can settle after the window's resize event.
  window.matchMedia('(max-width: 760px)').addEventListener('change', alignPortrait);
  if ('ResizeObserver' in window) new ResizeObserver(alignPortrait).observe(image);
  image.addEventListener('load', alignPortrait);
  alignPortrait();
  finePointer.addEventListener('change', reset);
  return {setPaused(value) { paused = value; if (paused || !finePointer.matches) reset(); }};
}
function initializeMotion(ambientResponse) {
  const nodes = [...document.querySelectorAll('[data-reveal]')];
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const toggle = $('motion-toggle');
  let userPaused = false;
  try { userPaused = localStorage.getItem('clipdock-motion') === 'paused'; } catch { /* Storage can be disabled in private browsing. */ }
  let observer;
  function synchronize() {
    observer?.disconnect();
    const paused = preference.matches || userPaused;
    document.documentElement.classList.toggle('ambient-paused', paused);
    ambientResponse.setPaused(paused || document.hidden);
    toggle.disabled = preference.matches;
    toggle.setAttribute('aria-pressed', String(!paused));
    toggle.title = preference.matches ? 'Reduced motion is enabled in your system settings' : paused ? 'Resume background motion' : 'Pause background motion';
    toggle.innerHTML = icon(paused ? 'play' : 'pause');
    if (preference.matches || !('IntersectionObserver' in window)) {
      document.documentElement.classList.remove('motion-ready');
      nodes.forEach(node => node.classList.add('is-visible'));
      return;
    }
    observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, {threshold: 0, rootMargin: '0px 0px -32px 0px'});
    document.documentElement.classList.add('motion-ready');
    nodes.forEach(node => { if (!node.classList.contains('is-visible')) observer.observe(node); });
  }
  synchronize();
  preference.addEventListener('change', synchronize);
  toggle.addEventListener('click', () => {
    userPaused = !userPaused;
    try { localStorage.setItem('clipdock-motion', userPaused ? 'paused' : 'playing'); } catch { /* The toggle still works for this visit. */ }
    synchronize();
  });
  function updateVisibility() {
    document.documentElement.classList.toggle('page-hidden', document.hidden);
    ambientResponse.setPaused(preference.matches || userPaused || document.hidden);
  }
  document.addEventListener('visibilitychange', updateVisibility);
  updateVisibility();
}
initializeMotion(initializeAmbientResponse()); updateNavigation(); updateFormat(); updateFilters(); initialize(); setTimeout(poll, 1500);
