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
