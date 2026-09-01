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
let lastSentText = null;     // last text request, for Gmail auth retry

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

// ---- Gmail OAuth connect flow ---------------------------------------------

let pendingGmailRequest = null;   // the user request blocked on authorization
let gmailConnectButtons = [];     // live Connect buttons (disabled after success)
let gmailAuthInFlight = false;    // guards against double-starting the flow
let gmailAuthorized = false;      // once true, ignore further auth notifications

function looksLikeGmailConnectHint(text) {
    return /gmail[^.]{0,40}not connected|not connected[^.]{0,40}gmail|connect[^.]{0,20}google account|连接.{0,6}google\s*账号|连接.{0,6}谷歌\s*账号|google\s*账号.{0,8}未\s*连接|谷歌\s*账号.{0,8}未\s*连接|日历.{0,10}未\s*连接|日历.{0,10}无法\s*使用|gmail.{0,10}未\s*连接|gmail.{0,10}无法\s*使用/i.test(text || '');
}

function insertGmailConnectButton() {
    const wrap = document.createElement('div');
    wrap.className = 'message system';
    const btn = document.createElement('button');
    btn.textContent = 'Connect Google Account';
    btn.className = 'gmail-connect-btn';
    btn.addEventListener('click', startGmailAuth);
    wrap.appendChild(btn);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
    // Keep a handle so the button can be disabled after a successful connect.
    gmailConnectButtons.push(btn);
}

function insertAuthLink(url) {
    const wrap = document.createElement('div');
    wrap.className = 'message system';
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'Popup blocked — click here to authorize Gmail';
    wrap.appendChild(a);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function startGmailAuth() {
    if (gmailAuthInFlight || gmailAuthorized) return;
    gmailAuthInFlight = true;
    setStatus('Waiting for Google authorization...');
    try {
        const resp = await fetch('/api/gmail/auth/start');
        const data = await resp.json();
        if (!resp.ok) {
            addMessage('assistant', 'Error: ' + (data.error || 'failed to start authorization'));
            setStatus('Error', true);
            return;
        }
        if (data.status === 'already_authorized') {
            onGmailAuthorized();
            return;
        }
        const win = window.open(data.auth_url, 'gmailAuth', 'width=520,height=680');
        if (!win) insertAuthLink(data.auth_url);
    } catch (err) {
        setStatus('Error: ' + err.message, true);
        console.error(err);
    } finally {
        gmailAuthInFlight = false;
    }
}

function onGmailAuthorized() {
    if (gmailAuthorized) return;   // postMessage + focus-check can both fire
    gmailAuthorized = true;
    // Disable every Connect button still in the chat history.
    gmailConnectButtons.forEach((b) => { b.disabled = true; b.textContent = '✓ Connected'; });
    addMessage('assistant', '✅ Google account connected (Gmail + Calendar).');
    setStatus('Ready');
    if (pendingGmailRequest) {
        const text = pendingGmailRequest;
        pendingGmailRequest = null;
        sendTextChat(text);
    }
}

function onGmailAuthError(message) {
    addMessage('assistant', 'Gmail authorization failed: ' + (message || 'unknown error') + '. You can try the Connect Gmail button again.');
    setStatus('Error', true);
}

window.addEventListener('message', (e) => {
    if (!e.data || typeof e.data !== 'object') return;
    if (e.data.type === 'gmail_authorized') onGmailAuthorized();
    else if (e.data.type === 'gmail_auth_error') onGmailAuthError(e.data.error);
});

// Fallback for popups blocked into a plain tab (opener is null there):
// check once when the main window regains focus.
window.addEventListener('focus', () => {
    if (!pendingGmailRequest) return;
    fetch('/api/gmail/auth/status')
        .then((r) => r.json())
        .then((s) => { if (s.authorized) onGmailAuthorized(); })
        .catch(() => {});
});

function maybeOfferGmailConnect(responseText, originalRequest) {
    if (gmailAuthorized) return;   // already connected; no need to offer again
    if (!looksLikeGmailConnectHint(responseText)) return;
    pendingGmailRequest = originalRequest || null;
    insertGmailConnectButton();
}

// ---- Composio Connect Link flow -------------------------------------------

// Composio returns a hosted OAuth link (a *.composio.dev URL) when a tool
// needs an account. Extract it from the assistant reply so the user can open
// it directly, mirroring the Gmail connect flow.
let composioShownLinks = new Set();   // avoid rendering the same link twice

function findComposioLinks(text) {
    const re = /https?:\/\/[^\s<>"']*composio\.dev[^\s<>"']*/gi;
    const found = text && text.match(re);
    return found || [];
}

function insertComposioConnectLink(url) {
    if (composioShownLinks.has(url)) return;
    composioShownLinks.add(url);
    const wrap = document.createElement('div');
    wrap.className = 'message system';
    const btn = document.createElement('button');
    btn.textContent = 'Connect Account';
    btn.className = 'gmail-connect-btn';   // reuse the Gmail button style for a consistent look
    btn.addEventListener('click', () => openComposioConnect(url));
    wrap.appendChild(btn);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function openComposioConnect(url) {
    const win = window.open(url, 'composioConnect', 'width=520,height=680');
    if (win) return;
    // Popup blocked: render a direct link as a fallback.
    const wrap = document.createElement('div');
    wrap.className = 'message system';
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'Popup blocked - click here to connect';
    wrap.appendChild(a);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function maybeOfferComposioConnect(responseText) {
    const links = findComposioLinks(responseText);
    links.forEach(insertComposioConnectLink);
    // 方案3(预备): 连接完成后的自动确认,对齐 Gmail 的 onGmailAuthorized 闭环。
    // 后续若要做,需:
    //   1) 后端加 /api/composio/auth/status?toolkit=...(用 session.toolkits(is_connected=True) 判断)
    //   2) 前端 window.addEventListener('focus', ...) 里轮询该端点
    //   3) maybeOfferComposioConnect 增加 originalRequest 参数并存入 pendingComposioRequest,
    //      连接成功后自动重发原请求(参照 onGmailAuthorized)
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
        maybeOfferGmailConnect(textResponse, transcript);
        maybeOfferComposioConnect(textResponse);

        if (response.ok) {
            const audioBlob2 = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob2);
            audioPlayer.src = audioUrl;
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
        maybeOfferGmailConnect(data.response, data.transcript);
        maybeOfferComposioConnect(data.response);
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
        maybeOfferComposioConnect(data.response);
        maybeOfferGmailConnect(data.response, lastSentText);
        if (data.response) playTts(data.response);
        setStatus('Ready');
    } else if (event === 'error') {
        addMessage('assistant', 'Error: ' + (data.message || 'unknown error'));
        setStatus('Error', true);
    }
}

async function sendTextChat(text) {
    addMessage('user', text);
    lastSentText = text;
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
