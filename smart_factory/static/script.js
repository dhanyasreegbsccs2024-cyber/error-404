const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const cameraPlaceholder = document.getElementById('cameraPlaceholder');
const cameraMessage = document.getElementById('cameraMessage');
const cameraState = document.getElementById('cameraState');
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');
const captureButton = document.getElementById('captureButton');
const calibrateButton = document.getElementById('calibrateButton');
let stream = null;
let captureInProgress = false;

function setCameraState(active, message) {
  cameraPlaceholder.classList.toggle('hidden', active);
  video.classList.toggle('visible', active);
  startButton.disabled = active;
  stopButton.disabled = !active;
  captureButton.disabled = !active;
  calibrateButton.disabled = !active;
  cameraState.textContent = active ? 'LIVE' : 'STANDBY';
  if (message) cameraMessage.textContent = message;
}

async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraMessage.textContent = 'This browser does not support webcam access.';
    return;
  }
  try {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    } catch {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    }
    video.srcObject = stream;
    video.muted = true;
    video.setAttribute('playsinline', 'true');
    video.onloadedmetadata = () => { video.play().catch(() => { cameraMessage.textContent = 'Camera connected. Click inside the camera view to start playback.'; }); };
    stream.getVideoTracks()[0].addEventListener('ended', () => stopCamera('The camera stopped. Click Start camera to reconnect it.'));
    setCameraState(true, 'Bottle detected by the operator? Center it inside the inspection frame.');
    video.play().catch(() => undefined);
  } catch (error) {
    cameraMessage.textContent = 'Camera permission was denied or no webcam was found. Check browser permissions and try again.';
  }
}

function stopCamera(message = 'Camera stopped. Start it again whenever you are ready.') {
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  video.srcObject = null;
  setCameraState(false, message);
}

async function captureAndInspect() {
  const track = stream?.getVideoTracks()[0];
  if (!track || track.readyState !== 'live') {
    stopCamera('The camera connection is not active. Click Start camera to reconnect it.');
    return;
  }
  if (!video.videoWidth || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    cameraMessage.textContent = 'Wait for the live camera frame before capturing.';
    return;
  }
  if (captureInProgress) return;
  captureInProgress = true;
  captureButton.disabled = true;
  captureButton.innerHTML = '<span class="capture-dot spinning"></span> Analyzing frame';
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    const response = await fetch('/inspect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: canvas.toDataURL('image/jpeg', 0.9) }), signal: controller.signal });
    window.clearTimeout(timeout);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Inspection failed');
    renderResult(result);
  } catch (error) {
    cameraMessage.textContent = error.name === 'AbortError' ? 'Inspection took too long. Keep the bottle centered and try again.' : `Inspection failed: ${error.message}`;
  } finally {
    captureInProgress = false;
    captureButton.disabled = false;
    captureButton.innerHTML = '<span class="capture-dot"></span> Capture &amp; inspect';
  }
}

async function calibrateGoodProduct() {
  if (!stream || !video.videoWidth) { cameraMessage.textContent = 'Start the camera and center a clean bottle before calibrating.'; return; }
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  calibrateButton.disabled = true;
  try {
    const response = await fetch('/calibrate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: canvas.toDataURL('image/jpeg', 0.9) }) });
    const result = await response.json();
    cameraMessage.textContent = result.message;
    if (result.success) calibrateButton.classList.add('calibrated');
  } catch (error) { cameraMessage.textContent = `Calibration failed: ${error.message}`; }
  finally { calibrateButton.disabled = false; }
}

function renderResult(result) {
  document.getElementById('resultEmpty').classList.add('hidden');
  document.getElementById('resultContent').classList.remove('hidden');
  const noBottle = result.status === 'NO BOTTLE DETECTED';
  const defective = !result.good && !noBottle;
  document.getElementById('resultCard').classList.toggle('defective', defective);
  const status = document.getElementById('resultStatus');
  status.textContent = noBottle ? 'NO BOTTLE' : defective ? 'REJECT' : 'PASS';
  status.className = `status-chip ${noBottle ? 'neutral' : defective ? 'bad' : 'good'}`;
  document.getElementById('verdictIcon').textContent = noBottle ? '?' : defective ? '!' : '✓';
  document.getElementById('verdictIcon').className = `verdict-icon ${noBottle ? 'neutral' : defective ? 'bad' : 'good'}`;
  document.getElementById('verdictText').textContent = result.status;
  document.getElementById('verdictReason').textContent = result.reason;
  document.getElementById('confidence').textContent = `${result.confidence}%`;
  document.getElementById('defect').textContent = result.defect;
  document.getElementById('action').textContent = result.recommended_action;
  const resultImage = document.getElementById('resultImage');
  if (result.image) { resultImage.src = result.image; resultImage.classList.remove('hidden'); }
  document.getElementById('resultCard').classList.toggle('no-bottle', noBottle);
  updateStats(result.stats, result.history);
  cameraMessage.textContent = `${result.status} · ${result.reason}`;
}

function updateStats(stats, history) {
  document.getElementById('totalCount').textContent = stats.total;
  document.getElementById('goodCount').textContent = stats.good;
  document.getElementById('defectiveCount').textContent = stats.defective;
  const passRate = stats.total ? Math.round((stats.good / stats.total) * 100) : 0;
  document.getElementById('passRate').textContent = stats.total ? `${passRate}%` : '—';
  document.getElementById('qualityBar').style.width = `${passRate}%`;
  const historyList = document.getElementById('historyList');
  historyList.innerHTML = history.length ? history.map((item) => `<div class="history-row"><span class="history-time">${item.time}</span><span class="history-product">Product #${1042 + history.indexOf(item)}</span><span class="history-defect">${item.defect}</span><b class="history-status ${item.status === 'GOOD PRODUCT' ? 'good-text' : 'bad-text'}">${item.status === 'GOOD PRODUCT' ? 'PASS' : 'REJECT'}</b><span class="history-confidence">${item.confidence}%</span></div>`).join('') : '<div class="history-empty">No inspection records yet.</div>';
}

function renderMachine(state, records) {
  document.getElementById('machineStatus').textContent = state.status;
  document.getElementById('machineStatus').className = state.status.toLowerCase();
  document.getElementById('temperature').textContent = `${state.temperature}°C`;
  document.getElementById('vibration').textContent = `${state.vibration} mm/s`;
  document.getElementById('pressure').textContent = `${state.pressure} bar`;
  document.getElementById('machineHealth').textContent = `${state.health}%`;
  document.getElementById('healthBar').style.width = `${state.health}%`;
  ['temperature', 'vibration', 'pressure'].forEach((name) => { document.getElementById(`${name}Status`).textContent = state.status === 'NORMAL' ? 'NORMAL' : name === 'temperature' && state.temperature > 85 || name === 'vibration' && state.vibration > 7 || name === 'pressure' && (state.pressure > 7 || state.pressure < 2) ? 'CRITICAL' : 'WARNING'; });
  const maintenance = document.getElementById('maintenanceStatus'); maintenance.textContent = state.maintenance; maintenance.className = `maintenance-chip ${state.status.toLowerCase()}`;
  document.getElementById('machineExplanation').textContent = state.explanation;
  document.getElementById('quickMachineStatus').textContent = state.status;
  document.getElementById('quickMachineStatus').className = state.status.toLowerCase();
  document.getElementById('quickTemperature').textContent = `${state.temperature}°C`;
  document.getElementById('quickVibration').textContent = `${state.vibration} mm/s`;
  document.getElementById('quickPressure').textContent = `${state.pressure} bar`;
  document.getElementById('quickHealth').textContent = `${state.health}%`;
  document.getElementById('quickHealthBar').style.width = `${state.health}%`;
  document.getElementById('quickMaintenance').textContent = state.maintenance.replace('MAINTENANCE ', '');
  ['quickTemperatureState', 'quickVibrationState', 'quickPressureState'].forEach((id, index) => { document.getElementById(id).textContent = [state.temperature > 85 ? 'CRITICAL' : state.temperature > 70 ? 'WARNING' : 'NORMAL', state.vibration > 7 ? 'CRITICAL' : state.vibration > 4 ? 'WARNING' : 'NORMAL', state.pressure > 7 || state.pressure < 2 ? 'CRITICAL' : state.pressure > 5 ? 'WARNING' : 'NORMAL'][index]; });
  document.querySelector('.machine-overview').classList.toggle('machine-critical', state.status === 'CRITICAL');
  document.getElementById('machineHistory').innerHTML = records.length ? records.slice(0, 6).map((item) => `<div class="machine-history-row"><span>${item.time}</span><span>${item.temperature}°C</span><span>${item.vibration} mm/s</span><span>${item.pressure} bar</span><b class="${item.status.toLowerCase()}">${item.status}</b></div>`).join('') : '<div class="history-empty">Run a simulation to create a monitoring record.</div>';
}

async function simulateMachine(mode = 'random') {
  try { const response = await fetch('/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode }) }); const result = await response.json(); renderMachine(result.machine, result.history); } catch { cameraMessage.textContent = 'Machine simulation is temporarily unavailable.'; }
}

async function loadIncident() {
  const panel = document.getElementById('incidentPanel');
  const button = document.getElementById('incidentButton');
  button.disabled = true;
  button.innerHTML = 'Analyzing factory signals <span class="capture-dot spinning"></span>';
  try {
    const response = await fetch('/incident');
    const data = await response.json();
    const incident = data.incident;
    panel.innerHTML = `<div class="incident-flow"><div class="incident-story"><span class="kicker">WHAT HAPPENED</span><strong>Production dropped from ${incident.target.toLocaleString()} to ${incident.output.toLocaleString()} units</strong><p>${incident.drop_percent}% below target. An abnormal disruption needs attention.</p></div><div class="incident-story"><span class="kicker">WHY IT HAPPENED / POSSIBLE CAUSE</span><strong>${incident.cause}</strong><ul>${incident.evidence.map((item) => `<li>${item}</li>`).join('')}</ul></div><div class="incident-story prediction"><span class="kicker">WHAT HAPPENS NEXT / ESTIMATED</span><div class="prediction-grid"><b>${incident.failure_risk}%<small>failure risk</small></b><b>${incident.downtime_hours}h<small>potential downtime</small></b><b>${incident.units_at_risk.toLocaleString()}<small>units at risk</small></b></div><p>${incident.quality_signal}</p></div><div class="incident-story action"><span class="kicker">WHAT SHOULD WE DO / AI-ASSISTED</span><strong>${incident.recommendation}</strong><p>${incident.why}</p><button id="applyRecommendation" class="primary-button">Open recommended decision <span>→</span></button></div></div><div class="scenario-title"><span class="kicker">CHOOSE A RESPONSE</span><strong>Compare production loss before acting</strong></div><div class="scenario-options">${data.scenarios.map((item) => `<button class="scenario-option ${item.recommended ? 'recommended' : ''}" data-loss="${item.loss}" data-name="${item.name}"><span>${item.id}</span><div><strong>${item.name}</strong><small>${item.risk}</small></div><b>${item.loss.toLocaleString()}<small>units loss</small></b></button>`).join('')}</div>`;
    panel.querySelectorAll('.scenario-option').forEach((option) => option.addEventListener('click', () => { panel.querySelectorAll('.scenario-option').forEach((item) => item.classList.remove('selected')); option.classList.add('selected'); }));
    document.getElementById('applyRecommendation').addEventListener('click', () => { panel.classList.add('decision-applied'); document.getElementById('applyRecommendation').textContent = 'Recommendation acknowledged'; });
  } catch { panel.innerHTML = '<div class="incident-empty"><strong>Incident analysis unavailable</strong><span>Check that the Flask server is running and try again.</span></div>'; }
  finally { button.disabled = false; button.innerHTML = 'Re-run factory incident <span>→</span>'; }
}

async function resetStats() {
  await fetch('/reset', { method: 'POST' });
  updateStats({ total: 0, good: 0, defective: 0 }, []);
  document.getElementById('resultEmpty').classList.remove('hidden');
  document.getElementById('resultContent').classList.add('hidden');
  document.getElementById('resultStatus').textContent = 'WAITING';
  document.getElementById('resultStatus').className = 'status-chip neutral';
  document.getElementById('resultCard').classList.remove('defective');
  document.getElementById('resultCard').classList.remove('no-bottle');
  document.getElementById('resultImage').classList.add('hidden');
}

startButton.addEventListener('click', startCamera);
stopButton.addEventListener('click', stopCamera);
captureButton.addEventListener('click', captureAndInspect);
calibrateButton.addEventListener('click', calibrateGoodProduct);
document.getElementById('resetButton').addEventListener('click', resetStats);
document.getElementById('randomMachine').addEventListener('click', () => simulateMachine('random'));
document.querySelectorAll('.mode-button').forEach((button) => button.addEventListener('click', () => simulateMachine(button.dataset.mode)));
document.getElementById('incidentButton').addEventListener('click', loadIncident);
window.addEventListener('beforeunload', stopCamera);
