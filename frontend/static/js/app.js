const micBtn = document.getElementById('micBtn');
const micIcon = document.getElementById('micIcon');
const statusEl = document.getElementById('status');
const chatBox = document.getElementById('chatBox');
const audioPlayer = document.getElementById('audioPlayer');

let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let conversationId = null;

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

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
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
    if (conversationId) {
        formData.append('conversation_id', conversationId);
    }

    try {
        const response = await fetch('/api/voice', {
            method: 'POST',
            body: formData,
        });

        const transcript = response.headers.get('X-Transcript') || '';
        const textResponse = response.headers.get('X-Response') || '';
        const cid = response.headers.get('X-Conversation-Id');
        if (cid) conversationId = cid;

        if (transcript) {
            addMessage('user', transcript);
        }

        if (textResponse) {
            addMessage('assistant', textResponse);
        }

        if (response.ok) {
            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
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
micBtn.addEventListener('mouseleave', () => {
    if (isRecording) stopRecording();
});

micBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    startRecording();
});
micBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    stopRecording();
});

// ---- Text chat (SSE) ----
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
        if (data.conversation_id) conversationId = data.conversation_id;
        if (data.response) {
            playTts(data.response);
        }
        setStatus('Ready');
    } else if (event === 'error') {
        addMessage('assistant', 'Error: ' + (data.message || 'unknown error'));
        setStatus('Error', true);
    }
}

let currentAssistantMsg = null;

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
