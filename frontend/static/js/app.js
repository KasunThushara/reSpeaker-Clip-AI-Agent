// reSpeaker Clip AI Agent frontend
// Supports three VOICE_INPUT_MODE values:
//   browser — legacy system-microphone push-to-talk only
//   clip    — reSpeaker Clip only (physical button + web click-to-toggle)
//   both    — manual Clip/browser selector (development)

const micBtn = document.getElementById('micBtn');
const clipBtn = document.getElementById('clipBtn');
const clipBtnLabel = document.getElementById('clipBtnLabel');
const clipStatusLine = document.getElementById('clipStatusLine');
const inputModeRow = document.getElementById('inputModeRow');
const inputModeSelect = document.getElementById('inputModeSelect');
const statusEl = document.getElementById('status');
const chatBox = document.getElementById('chatBox');
const audioPlayer = document.getElementById('audioPlayer');

let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let conversationId = null;
let currentAssistantMsg = null;

let clipMode = false;        // true when the active input is the Clip
let clipRecording = false;   // device recording state from events
let clipBusy = false;        // guards duplicate mouse/touch actions
let clipOffline = true;      // until /api/clip/status says otherwise
let clipEventSource = null;
let clipStartPending = false;
let clipStartedByWeb = false;
let clipDisconnectTimer = null;
let clipDisconnectError = '';

const CLIP_OFFLINE_GRACE_MS = 60000;

// ---- config embedded by the server ---------------------------------------
let CLIP_CONFIG = { input_mode: 'browser', clip_enabled: false, record_mode: 'enhanced' };
try {
    const el = document.getElementById('clip-config');
    if (el) CLIP_CONFIG = JSON.parse(el.textContent);
} catch (e) { console.error('bad clip config', e); }

const INPUT_MODE = CLIP_CONFIG.input_mode || 'browser';
const CLIP_AVAILABLE = !!CLIP_CONFIG.clip_enabled && INPUT_MODE !== 'browser';

// ---- shared UI helpers -----------------------------------------------------

function addMessage(role, text) {
    const msg = document.createElement('div');
    msg.className = 'message ' + role;
    msg.textContent = text;
    chatBox.appendChild(msg);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function setStatus(text, isError) {
    statusEl.textContent = text;
    statusEl.className = 'status' + (isError ? ' error' : '');
}

function setClipStatusLine(text, isError) {
    clipStatusLine.textContent = text || '';
    clipStatusLine.className = 'clip-status' + (isError ? ' error' : '');
}

function setClipUI(recording, busy, offline) {
    clipRecording = !!recording;
    clipBusy = !!busy;
    clipOffline = offline !== undefined ? !!offline : clipOffline;
    clipBtn.classList.toggle('recording', clipRecording);
    clipBtnLabel.textContent = clipRecording ? 'Stop' : 'Clip';
    clipBtn.disabled = clipBusy || clipOffline || !CLIP_AVAILABLE;
}

function noteClipDisconnected(error) {
    clipOffline = true;
    clipDisconnectError = error || clipDisconnectError || 'disconnected';
    // Disable commands while the link is unavailable, but keep the current
    // status text during the one-minute reconnect grace period.
    setClipUI(clipRecording, clipBusy, true);
    if (clipDisconnectTimer !== null) return;
    clipDisconnectTimer = window.setTimeout(() => {
        clipDisconnectTimer = null;
        if (!clipOffline) return;
        setClipStatusLine('Clip offline — ' + clipDisconnectError, true);
    }, CLIP_OFFLINE_GRACE_MS);
}

function noteClipConnected(label) {
    clipOffline = false;
    clipDisconnectError = '';
    if (clipDisconnectTimer !== null) {
        window.clearTimeout(clipDisconnectTimer);
        clipDisconnectTimer = null;
    }
    if (label) setClipStatusLine(label);
}

function applyMode() {
    const both = INPUT_MODE === 'both';
    inputModeRow.hidden = !both;
    if (INPUT_MODE === 'browser') {
        clipMode = false;
        micBtn.hidden = false;
        clipBtn.hidden = true;
    } else if (INPUT_MODE === 'clip') {
        clipMode = true;
        micBtn.hidden = true;
        clipBtn.hidden = false;
    } else { // both
        clipMode = inputModeSelect.value === 'clip';
        micBtn.hidden = clipMode;
        clipBtn.hidden = !clipMode;
        if (clipMode) {
            micBtn.classList.remove('recording');
        } else {
            micBtn.disabled = false;
        }
    }
    if (CLIP_AVAILABLE) {
        setClipUI(clipRecording, clipBusy);
    }
}

function registerContext(cid) {
    if (!cid || !CLIP_AVAILABLE) return;
    fetch('/api/clip/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: cid }),
    }).catch((err) => console.error('register context failed', err));
}

function rememberConversation(cid) {
    if (!cid || cid === conversationId) return;
    conversationId = cid;
    registerContext(cid);
}

// ---- browser microphone input (legacy) ------------------------------------

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach((track) => track.stop());
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            await sendVoice(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        micBtn.classList.add('recording');
        setStatus('Listening...');
    } catch (err) {
        setStatus('Mic access denied', true);
        console.error(err);
    }
}

function stopRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        micBtn.classList.remove('recording');
        setStatus('Processing...');
    }
}

async function sendVoice(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    if (conversationId) formData.append('conversation_id', conversationId);

    try {
        const response = await fetch('/api/voice', { method: 'POST', body: formData });

        const transcript = response.headers.get('X-Transcript') || '';
        const textResponse = response.headers.get('X-Response') || '';
        rememberConversation(response.headers.get('X-Conversation-Id'));

        if (transcript) addMessage('user', transcript);
        if (textResponse) addMessage('assistant', textResponse);

        if (response.ok) {
            const audioBlob2 = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob2);
            audioPlayer.src = audioUrl;
            audioPlayer.hidden = false;
            audioPlayer.play();
        }
        setStatus('Ready');
    } catch (err) {
        setStatus('Error: ' + err.message, true);
        console.error(err);
    }
}

micBtn.addEventListener('mousedown', startRecording);
micBtn.addEventListener('mouseup', stopRecording);
micBtn.addEventListener('mouseleave', () => { if (isRecording) stopRecording(); });
micBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
micBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecording(); });

// ---- reSpeaker Clip input ---------------------------------------------------

function clipStart() {
    if (clipBusy || clipOffline) return;
    clipStartPending = true;
    setClipUI(false, true);
    setStatus('Starting Clip...');
    fetch('/api/clip/recordings/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mode: CLIP_CONFIG.record_mode || 'enhanced',
            conversation_id: conversationId || undefined,
        }),
    })
        .then((resp) => {
            if (!resp.ok) return resp.json().then((d) => { throw new Error(d.error || 'start failed'); });
            return resp.json();
        })
        .then((data) => {
            clipStartPending = false;
            clipStartedByWeb = true;
            rememberConversation(data.conversation_id);
            setClipUI(true, false);
            setStatus('Recording (Clip)...');
        })
        .catch((err) => {
            clipStartPending = false;
            clipStartedByWeb = false;
            setClipUI(false, false);
            setStatus('Clip error: ' + err.message, true);
        });
}

function clipStop() {
    if (clipStartPending) return;
    if (clipBusy || clipOffline) return;
    setClipUI(false, true);
    setStatus('Stopping Clip...');
    fetch('/api/clip/recordings/stop', { method: 'POST' })
        .then((resp) => {
            if (!resp.ok) return resp.json().then((d) => { throw new Error(d.error || 'stop failed'); });
            return resp.json();
        })
        .then((data) => {
            clipStartedByWeb = false;
            if (data.session) setStatus('Processing session ' + data.session + '...');
        })
        .catch((err) => {
            // 409 (not recording) is expected after a physical stop.
            if (String(err.message).indexOf('not recording') === -1 && String(err.message).indexOf('409') === -1) {
                setStatus('Clip error: ' + err.message, true);
            }
            clipStartedByWeb = false;
            setClipUI(false, false);
        });
}

function toggleClipRecording(event) {
    event.preventDefault();
    if (!CLIP_AVAILABLE || clipOffline) {
        setStatus('Clip is offline — check BLE', true);
        return;
    }
    if (clipRecording) {
        // A web press can also stop a recording started from the physical key.
        clipStop();
        return;
    }
    clipStart();
}

clipBtn.addEventListener('click', toggleClipRecording);

if (inputModeSelect) {
    inputModeSelect.addEventListener('change', () => { applyMode(); });
}

function handleClipSseEvent(eventName, data) {
    if (eventName === 'connection') {
        if (data && data.connected) {
            noteClipConnected('Clip connected' + (data.status && data.status.device_name ? ' — ' + data.status.device_name : ''));
            setClipUI(clipRecording, false, false);
            // Re-sync recording state after any reconnect.
            refreshClipStatus();
        } else {
            noteClipDisconnected(data && data.error);
        }
    } else if (eventName === 'recording') {
        if (data && data.action === 'started') {
            clipStartedByWeb = data.trigger === 'web';
            setClipUI(true, false);
            setStatus('Recording (Clip)...');
            setClipStatusLine('Recording session ' + (data.session || '') + ' (' + (data.trigger || '') + ')');
        } else if (data && data.action === 'stopped') {
            clipStartedByWeb = false;
            setClipUI(false, true);
            setStatus('Processing session ' + (data.session || '') + '...');
            setClipStatusLine('Session stopped — downloading');
        }
    } else if (eventName === 'workflow') {
        const s = data && data.status;
        if (s === 'downloading') { setStatus('Downloading audio...'); setClipStatusLine('Downloading ' + data.session); }
        else if (s === 'processing') { setStatus('Transcribing & thinking...'); setClipStatusLine('Processing ' + data.session); }
        else if (s === 'failed') { setStatus('Processing failed: ' + (data.error || 'unknown'), true); setClipStatusLine('', true); setClipUI(false, false); }
    } else if (eventName === 'result') {
        if (data.transcript) addMessage('user', data.transcript);
        if (data.response) addMessage('assistant', data.response);
        rememberConversation(data.conversation_id);
        if (data.response) playTts(data.response);
        setClipUI(false, false);
        setStatus('Ready');
        setClipStatusLine('Answered from session ' + data.session + ' (' + (data.trigger || '') + ')');
    }
}

function refreshClipStatus() {
    fetch('/api/clip/status')
        .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error('status ' + resp.status))))
        .then((data) => {
            if (!data.connected) {
                noteClipDisconnected(data.last_error);
            } else {
                const suffix = data.transfer_active ? ' — downloading' : '';
                noteClipConnected('Clip connected — ' + (data.device_name || data.device_id || '') + suffix);
                // Recording is not busy; only in-flight transfers/requests disable it.
                setClipUI(!!data.recording, !!data.transfer_active, false);
                if (data.recording) setClipUI(true, false);
            }
        })
        .catch((err) => { noteClipDisconnected(err && err.message); });
}

function openClipEvents() {
    if (!CLIP_AVAILABLE || clipEventSource) return;
    const es = new EventSource('/api/clip/events');
    clipEventSource = es;
    es.onopen = () => { refreshClipStatus(); };
    es.onerror = () => {
        // EventSource retries automatically.  Short stream/BLE interruptions
        // stay silent and only become visible after the shared grace period.
        noteClipDisconnected('event stream disconnected');
    };
    ['connection', 'recording', 'workflow', 'result'].forEach((name) => {
        es.addEventListener(name, (ev) => {
            let data = {};
            try { data = JSON.parse(ev.data || '{}'); } catch (_) {}
            handleClipSseEvent(name, data);
        });
    });
}

// ---- text chat (SSE) ---------------------------------------------------------

const textForm = document.getElementById('textForm');
const textInput = document.getElementById('textInput');

textForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = textInput.value.trim();
    if (!text) return;
    textInput.value = '';
    sendTextChat(text);
});

function handleSseEvent(rawEvent) {
    const lines = rawEvent.split('\n');
    let event = 'message';
    let dataStr = '';
    for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
    }
    let data = {};
    try { data = JSON.parse(dataStr); } catch (_) {}

    if (event === 'thinking') {
        setStatus('AI is using ' + (data.tool || 'a tool') + '...');
    } else if (event === 'token') {
        if (!currentAssistantMsg) {
            currentAssistantMsg = document.createElement('div');
            currentAssistantMsg.className = 'message assistant';
            currentAssistantMsg.textContent = '';
            chatBox.appendChild(currentAssistantMsg);
        }
        currentAssistantMsg.textContent += data.text || '';
        chatBox.scrollTop = chatBox.scrollHeight;
    } else if (event === 'done') {
        if (currentAssistantMsg) {
            currentAssistantMsg.textContent = data.response || currentAssistantMsg.textContent;
            currentAssistantMsg = null;
        } else if (data.response) {
            addMessage('assistant', data.response);
        }
        rememberConversation(data.conversation_id);
        if (data.response) playTts(data.response);
        setStatus('Ready');
    } else if (event === 'error') {
        addMessage('assistant', 'Error: ' + (data.message || 'unknown error'));
        setStatus('Error', true);
    }
}

async function sendTextChat(text) {
    addMessage('user', text);
    setStatus('Thinking...');

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, conversation_id: conversationId }),
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buffer.indexOf('\n\n')) !== -1) {
                const rawEvent = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);
                handleSseEvent(rawEvent);
            }
        }
    } catch (err) {
        setStatus('Error: ' + err.message, true);
        console.error(err);
    }
}

async function playTts(text) {
    try {
        const resp = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        if (!resp.ok) return;
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        audioPlayer.src = url;
        audioPlayer.hidden = false;
        audioPlayer.play();
    } catch (err) {
        console.error('TTS failed', err);
    }
}

// ---- init ---------------------------------------------------------------------

if (INPUT_MODE === 'both') {
    inputModeSelect.value = 'clip';
}
applyMode();
if (CLIP_AVAILABLE) {
    refreshClipStatus();
    // SSE drives low-latency updates; polling also heals a stale offline label
    // if the event stream misses a short BLE disconnect/reconnect transition.
    window.setInterval(refreshClipStatus, 5000);
    openClipEvents();
} else if (INPUT_MODE !== 'browser') {
    setClipStatusLine('Clip runtime unavailable on this server', true);
    setClipUI(false, false, true);
}
