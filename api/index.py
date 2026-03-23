"""
KIRA — Analista Operacional Sênior
Versão Completa com Firebase
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio

# Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except:
    FIREBASE_AVAILABLE = False

# ============================================================
# CONFIGURAÇÕES
# ============================================================
GROQ_KEY = os.getenv("GROQ_KEY", "")
FIREBASE_CRED_JSON = os.getenv("FIREBASE_CRED_JSON", "")

# Cache
cache = {
    "dados": [],
    "ultima_atualizacao": None,
    "colhedoras_proprias": 0,
    "colhedoras_fretistas": 0,
    "total_registros": 0,
    "total_area": 0,
    "total_horas_corte": 0,
    "total_horas_rtk": 0,
    "adesao_rtk": 0,
    "erro": None,
    "carregando": True
}

# Inicializar Firebase
db = None
firebase_status = "Desconectado"

if FIREBASE_AVAILABLE and FIREBASE_CRED_JSON:
    try:
        cred_dict = json.loads(FIREBASE_CRED_JSON)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_status = "Conectado"
            print("✅ Firebase conectado")
    except Exception as e:
        firebase_status = f"Erro: {str(e)[:50]}"

# App
app = FastAPI(title="KIRA", version="1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# CARREGAR DADOS
# ============================================================
async def carregar_dados():
    """Carrega dados do Firebase"""
    global cache
    
    if not db:
        cache["carregando"] = False
        cache["erro"] = "Firebase não conectado"
        return
    
    cache["carregando"] = True
    
    colecoes = ["tpl", "acmSafra", "producao", "snapshots"]
    
    total_registros = 0
    colh_proprias = set()
    colh_fretistas = set()
    total_area = 0
    total_horas_corte = 0
    total_horas_rtk = 0
    
    for colecao in colecoes:
        try:
            docs = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: db.collection(colecao).limit(200).get()
                ),
                timeout=5.0
            )
            
            for doc in docs:
                dados = doc.to_dict()
                if dados:
                    total_registros += 1
                    
                    cod = dados.get("COD. EQUIPAMENTO") or dados.get("COD_EQUIPAMENTO")
                    if cod:
                        cod_str = str(cod)
                        if cod_str.startswith("80"):
                            colh_proprias.add(cod_str)
                        elif cod_str.startswith("93"):
                            colh_fretistas.add(cod_str)
                    
                    area = dados.get("AREA TRABALHADA ANALITICA") or dados.get("area_trabalhada") or 0
                    horas_corte = dados.get("HRS CORTE BASE AUT LIGADO") or dados.get("horas_corte") or 0
                    horas_rtk = dados.get("HRS RTK_LIGADO") or dados.get("horas_rtk") or 0
                    
                    try:
                        total_area += float(str(area).replace(",", ".")) if area else 0
                        total_horas_corte += float(str(horas_corte).replace(",", ".")) if horas_corte else 0
                        total_horas_rtk += float(str(horas_rtk).replace(",", ".")) if horas_rtk else 0
                    except:
                        pass
                        
        except Exception as e:
            print(f"Erro em {colecao}: {e}")
    
    adesao = (total_horas_rtk / total_horas_corte * 100) if total_horas_corte > 0 else 0
    
    cache.update({
        "total_registros": total_registros,
        "colhedoras_proprias": len(colh_proprias),
        "colhedoras_fretistas": len(colh_fretistas),
        "total_area": total_area,
        "total_horas_corte": total_horas_corte,
        "total_horas_rtk": total_horas_rtk,
        "adesao_rtk": adesao,
        "ultima_atualizacao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "carregando": False,
        "erro": None
    })
    
    print(f"✅ Carregado: {total_registros} registros, {len(colh_proprias)} próprias, {len(colh_fretistas)} fretistas")

@app.on_event("startup")
async def startup():
    asyncio.create_task(carregar_dados())

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
async def root():
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
            .offline { background: #ef4444; }
            .transcript-area {
                background: rgba(10, 10, 15, 0.8);
                padding: 16px;
                border-radius: 12px;
                margin: 15px 0;
                min-height: 80px;
            }
            .metric {
                display: inline-block;
                background: rgba(236, 72, 153, 0.2);
                padding: 8px 16px;
                border-radius: 8px;
                margin: 4px;
            }
            .metric-value {
                font-size: 1.5rem;
                font-weight: bold;
                color: #ec4899;
            }
            .loading {
                animation: pulse 1s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🤖 KIRA</div>
                <p>Analista Operacional Sênior - Usina Pitangueiras</p>
            </div>

            <div class="card">
                <h3>📡 Status do Sistema</h3>
                <div id="status"></div>
            </div>

            <div class="card">
                <h3>📊 Dados do Firebase</h3>
                <div id="dados"></div>
            </div>

            <div class="card">
                <h3>🎤 Comandos de Voz</h3>
                <button onclick="startRecording()">🎙️ FALAR AGORA</button>
                <button onclick="toggleHandsFree()">✋ MÃOS LIVRES</button>
                <div class="transcript-area" id="transcript">👉 Clique no botão e fale</div>
                <div class="transcript-area" id="response" style="color: #ec4899;"></div>
            </div>

            <div class="card">
                <h3>📋 Exemplos de Perguntas</h3>
                <ul>
                    <li>"Quantas colhedoras próprias?"</li>
                    <li>"Quantas colhedoras fretistas?"</li>
                    <li>"Qual a área total trabalhada?"</li>
                    <li>"Como está a adesão ao RTK?"</li>
                    <li>"Mostre as estatísticas"</li>
                </ul>
            </div>
        </div>

        <script>
            let mediaRecorder = null;
            let audioChunks = [];
            let isRecording = false;
            let handsFreeMode = false;

            async function atualizarDados() {
                try {
                    const res = await fetch('/api/dados');
                    const data = await res.json();
                    
                    document.getElementById('status').innerHTML = `
                        <p><span class="status-dot ${data.firebase_conectado ? 'online' : 'offline'}"></span>
                        Firebase: ${data.firebase_conectado ? '✅ CONECTADO' : '❌ DESCONECTADO'}</p>
                        <p>🎤 Groq: ${data.groq_ok ? '✅ Disponível' : '❌ Não configurado'}</p>
                        <p>🕐 Servidor: ${data.hora}</p>
                    `;
                    
                    if (data.carregando) {
                        document.getElementById('dados').innerHTML = '<div class="loading">🔄 Carregando dados do Firebase...</div>';
                    } else if (data.total_registros > 0) {
                        document.getElementById('dados').innerHTML = `
                            <div class="metric">
                                <div class="metric-value">${data.total_registros.toLocaleString()}</div>
                                <div>registros</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.colhedoras_proprias}</div>
                                <div>próprias</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.colhedoras_fretistas}</div>
                                <div>fretistas</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.total_area.toLocaleString()}</div>
                                <div>hectares</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.adesao_rtk.toFixed(1)}%</div>
                                <div>RTK</div>
                            </div>
                            <p style="margin-top: 12px; font-size: 0.8rem;">📅 Atualizado: ${data.ultima_atualizacao || 'Nunca'}</p>
                        `;
                    } else {
                        document.getElementById('dados').innerHTML = '<p>⚠️ Nenhum dado encontrado no Firebase</p>';
                    }
                } catch (error) {
                    console.error('Erro:', error);
                }
            }

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
                            document.getElementById('transcript').innerHTML = '❌ Erro ao processar';
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

            atualizarDados();
            setInterval(atualizarDados, 10000);
        </script>
    </body>
    </html>
    """)

@app.get("/api/status")
async def status():
    return {
        "status": "online",
        "hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "firebase_conectado": firebase_status == "Conectado",
        "groq_ok": bool(GROQ_KEY)
    }

@app.get("/api/dados")
async def get_dados():
    return {
        "total_registros": cache["total_registros"],
        "colhedoras_proprias": cache["colhedoras_proprias"],
        "colhedoras_fretistas": cache["colhedoras_fretistas"],
        "total_area": cache["total_area"],
        "total_horas_corte": cache["total_horas_corte"],
        "total_horas_rtk": cache["total_horas_rtk"],
        "adesao_rtk": cache["adesao_rtk"],
        "ultima_atualizacao": cache["ultima_atualizacao"],
        "carregando": cache["carregando"],
        "erro": cache["erro"],
        "firebase_conectado": firebase_status == "Conectado",
        "groq_ok": bool(GROQ_KEY),
        "hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }

@app.post("/api/transcribe")
async def transcrever(audio: UploadFile = File(...)):
    if not GROQ_KEY:
        return {"text": "Groq não configurado"}
    
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
        return {"text": f"Erro: {response.status_code}"}
            
    except Exception as e:
        return {"text": f"Erro: {str(e)[:100]}"}

@app.post("/api/chat")
async def chat(text: str = Form(...), session_id: str = Form(default="default")):
    if not GROQ_KEY:
        return {"answer": "Groq não configurado", "session_id": session_id}
    
    # Aprendizado
    if "aprenda" in text.lower() or "grave" in text.lower():
        return {"answer": "Memorizado, Senhor.", "session_id": session_id}
    
    # Contexto com dados reais
    contexto = ""
    if cache["total_registros"] > 0:
        contexto = f"""
DADOS REAIS DA USINA:
- Total de registros processados: {cache["total_registros"]}
- Colhedoras próprias: {cache["colhedoras_proprias"]}
- Colhedoras fretistas: {cache["colhedoras_fretistas"]}
- Área trabalhada: {cache["total_area"]:.0f} hectares
- Horas de corte: {cache["total_horas_corte"]:.0f} horas
- Adesão ao RTK: {cache["adesao_rtk"]:.1f}%
"""
    
    system_prompt = f"""Você é KIRA, Analista Operacional da Usina Pitangueiras.

{contexto}

REGRAS IMPORTANTES:
- Use SOMENTE os dados fornecidos acima
- Se não tiver dados, diga "Senhor, ainda não há dados carregados do Firebase"
- NUNCA invente números ou valores
- Responda de forma formal, trate o usuário como "Senhor"
- Respostas curtas (máximo 15 palavras)

RESPOSTA:"""

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
                    "max_tokens": 150
                }
            )
        
        if response.status_code == 200:
            resposta = response.json()["choices"][0]["message"]["content"].strip()
            return {"answer": resposta, "session_id": session_id}
        return {"answer": "Erro ao processar", "session_id": session_id}
            
    except Exception as e:
        return {"answer": f"Erro: {str(e)[:100]}", "session_id": session_id}
