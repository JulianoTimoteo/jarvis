"""
KIRA — Analista Operacional Sênior
Versão Super Otimizada - Sem Firebase por enquanto
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

# ============================================================
# CONFIGURAÇÕES
# ============================================================
GROQ_KEY = os.getenv("GROQ_KEY", "")

# App
app = FastAPI(title="KIRA", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    """Interface principal - Super Rápida"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>KIRA - Analista Operacional</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 800px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 40px; }
            .logo {
                font-size: 3rem;
                font-weight: 800;
                background: linear-gradient(135deg, #ec4899, #f472b6);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
            }
            .card {
                background: rgba(26, 26, 46, 0.9);
                border-radius: 16px;
                padding: 24px;
                margin-bottom: 20px;
                border-left: 4px solid #ec4899;
            }
            button {
                background: #ec4899;
                border: none;
                padding: 12px 28px;
                border-radius: 40px;
                color: white;
                cursor: pointer;
                font-size: 16px;
                margin: 5px;
                transition: transform 0.2s;
            }
            button:hover { transform: scale(1.05); }
            .status-dot {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 8px;
            }
            .online { background: #10b981; box-shadow: 0 0 8px #10b981; }
            .transcript-area {
                background: rgba(10, 10, 15, 0.8);
                padding: 16px;
                border-radius: 12px;
                margin: 15px 0;
                min-height: 80px;
            }
            a { color: #ec4899; text-decoration: none; }
            .highlight { color: #ec4899; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🤖 KIRA</div>
                <p>Analista Operacional Sênior - Usina Pitangueiras</p>
            </div>

            <div class="card">
                <h3>📡 Status</h3>
                <p><span class="status-dot online"></span> Sistema Operacional</p>
                <p>🎤 <span class="highlight">Groq</span> disponível</p>
                <p>🗣️ <span class="highlight">Reconhecimento de voz</span> ativo</p>
                <p>📅 <span id="time"></span></p>
            </div>

            <div class="card">
                <h3>🎤 Comandos de Voz</h3>
                <button onclick="startRecording()">🎙️ FALAR AGORA</button>
                <button onclick="toggleHandsFree()">✋ MÃOS LIVRES</button>
                <div class="transcript-area" id="transcript">👉 Clique no botão e fale</div>
                <div class="transcript-area" id="response" style="color: #ec4899;"></div>
            </div>

            <div class="card">
                <h3>📊 Exemplos de Perguntas</h3>
                <ul>
                    <li>"Qual a produção total?"</li>
                    <li>"Quantas colhedoras?"</li>
                    <li>"Como está a eficiência?"</li>
                    <li>"Aprenda que [fato importante]"</li>
                </ul>
            </div>
        </div>

        <script>
            let mediaRecorder = null;
            let audioChunks = [];
            let isRecording = false;
            let handsFreeMode = false;

            document.getElementById('time').innerHTML = new Date().toLocaleString('pt-BR');

            async function startRecording() {
                if (isRecording) {
                    if (mediaRecorder && mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                    }
                    isRecording = false;
                    document.querySelector('button[onclick="startRecording()"]').innerHTML = '🎙️ FALAR AGORA';
                    return;
                }

                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];

                    mediaRecorder.ondataavailable = event => {
                        if (event.data.size > 0) audioChunks.push(event.data);
                    };

                    mediaRecorder.onstop = async () => {
                        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                        const formData = new FormData();
                        formData.append('audio', audioBlob, 'audio.webm');

                        document.getElementById('transcript').innerHTML = '🎙️ Processando...';

                        try {
                            const transcribeRes = await fetch('/api/transcribe', { method: 'POST', body: formData });
                            const { text } = await transcribeRes.json();

                            document.getElementById('transcript').innerHTML = `🗣️ Você: "${text}"`;

                            const chatForm = new FormData();
                            chatForm.append('text', text);
                            chatForm.append('session_id', 'web_' + Date.now());

                            const chatRes = await fetch('/api/chat', { method: 'POST', body: chatForm });
                            const { answer } = await chatRes.json();

                            document.getElementById('response').innerHTML = `🤖 KIRA: ${answer}`;

                            const utterance = new SpeechSynthesisUtterance(answer);
                            utterance.lang = 'pt-BR';
                            utterance.rate = 0.95;
                            speechSynthesis.speak(utterance);

                        } catch (error) {
                            document.getElementById('transcript').innerHTML = '❌ Erro ao processar: ' + error.message;
                        }

                        if (handsFreeMode) setTimeout(startRecording, 1000);
                    };

                    mediaRecorder.start();
                    isRecording = true;
                    document.querySelector('button[onclick="startRecording()"]').innerHTML = '⏹️ PARAR';
                    document.getElementById('transcript').innerHTML = '🎙️ Ouvindo... Fale agora';

                } catch (error) {
                    alert('❌ Permissão do microfone negada');
                }
            }

            function toggleHandsFree() {
                handsFreeMode = !handsFreeMode;
                const btn = document.querySelector('button[onclick="toggleHandsFree()"]');
                if (handsFreeMode) {
                    btn.innerHTML = '✋ MÃOS LIVRES (ATIVO)';
                    btn.style.background = '#10b981';
                    if (!isRecording) startRecording();
                } else {
                    btn.innerHTML = '✋ MÃOS LIVRES';
                    btn.style.background = '#ec4899';
                    if (isRecording) {
                        mediaRecorder.stop();
                        isRecording = false;
                    }
                }
            }
        </script>
    </body>
    </html>
    """)

@app.get("/api/status")
async def status():
    """Status rápido"""
    return {
        "status": "online",
        "time": datetime.now().isoformat(),
        "groq_available": bool(GROQ_KEY),
        "message": "KIRA operacional"
    }

@app.post("/api/transcribe")
async def transcrever(audio: UploadFile = File(...)):
    """Transcreve áudio usando Groq"""
    if not GROQ_KEY:
        return {"text": "Groq não configurado. Configure GROQ_KEY nas variáveis de ambiente."}
    
    try:
        conteudo = await audio.read()
        
        if len(conteudo) < 1000:
            return {"text": "Áudio muito curto"}
        
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(conteudo)
            tmp_path = tmp.name
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            with open(tmp_path, "rb") as audio_file:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"},
                    files={"file": ("audio.webm", audio_file, "audio/webm")},
                    data={"model": "whisper-large-v3-turbo", "language": "pt"}
                )
        
        Path(tmp_path).unlink(missing_ok=True)
        
        if response.status_code == 200:
            texto = response.json().get("text", "").strip()
            return {"text": texto if texto else "Não entendi"}
        else:
            return {"text": f"Erro na transcrição: {response.status_code}"}
            
    except Exception as e:
        return {"text": f"Erro: {str(e)}"}

@app.post("/api/chat")
async def chat(text: str = Form(...), session_id: str = Form(default="default")):
    """Chat com IA usando Groq"""
    if not GROQ_KEY:
        return {"answer": "Groq não configurado. Configure GROQ_KEY.", "session_id": session_id}
    
    if "aprenda" in text.lower() or "grave" in text.lower():
        return {"answer": "Memorizado, Senhor.", "session_id": session_id}
    
    system_prompt = """Você é KIRA, assistente da Usina Pitangueiras.
- Seja formal e trate o usuário como "Senhor"
- Respostas curtas (máximo 15 palavras)
- Seja objetiva e profissional"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 100
                }
            )
        
        if response.status_code == 200:
            resposta = response.json()["choices"][0]["message"]["content"].strip()
            return {"answer": resposta, "session_id": session_id}
        else:
            return {"answer": "Erro ao processar consulta.", "session_id": session_id}
            
    except Exception as e:
        return {"answer": f"Erro: {str(e)[:100]}", "session_id": session_id}
