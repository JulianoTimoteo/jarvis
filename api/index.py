"""
KIRA — Analista Operacional Sênior v12.0
Leitura CORRETA de dados em chunks do Firebase
"""

import os
import json
import tempfile
import logging
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
    "caminhoes_proprios": 0,
    "caminhoes_terceiros": 0,
    "total_registros": 0,
    "total_peso_liquido": 0,
    "total_viagens": 0,
    "ultima_sync": None,
    "carregando": True,
    "erro": None
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
        print(f"❌ {firebase_status}")

app = FastAPI(title="KIRA", version="12.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# FUNÇÕES DE LEITURA DOS DADOS
# ============================================================
def extrair_dados_da_linha(linha, cabecalho):
    """Extrai dados de uma linha do chunk"""
    if len(linha) != len(cabecalho):
        return None
    
    registro = {}
    for i, campo in enumerate(cabecalho):
        valor = linha[i]
        # Converte valores numéricos
        if campo in ["Peso Líquido", "Peso Bruto", "Peso Tara"]:
            try:
                valor = float(str(valor).replace(",", "."))
            except:
                valor = 0
        registro[campo] = valor
    
    return registro

async def ler_colecao_chunks():
    """Lê dados da coleção PRODUCAO_07_2025 que está em chunks"""
    if not db:
        return []
    
    todos_registros = []
    cabecalho = None
    
    try:
        # Primeiro, busca o documento principal que tem a estrutura de chunks
        doc_ref = db.collection("PRODUCAO_07_2025").document("chunks")
        doc = doc_ref.get()
        
        if doc.exists:
            dados = doc.to_dict()
            # Pega o cabeçalho do campo 'cab'
            if "cab" in dados:
                cabecalho = dados["cab"]
                print(f"📋 Cabeçalho encontrado: {len(cabecalho)} campos")
            
            # Pega todos os chunks
            chunks = dados.get("chunks", {})
            print(f"📦 Encontrados {len(chunks)} chunks")
            
            for chunk_name, chunk_data in chunks.items():
                if "rows" in chunk_data:
                    linhas = chunk_data["rows"]
                    print(f"   Processando {chunk_name}: {len(linhas)} linhas")
                    
                    for linha in linhas:
                        if cabecalho:
                            registro = extrair_dados_da_linha(linha, cabecalho)
                            if registro:
                                todos_registros.append(registro)
        
        # Também tenta ler outras coleções
        outras_colecoes = ["acmSafra", "tpl", "snapshots"]
        for colecao in outras_colecoes:
            try:
                docs = db.collection(colecao).limit(500).get()
                for doc in docs:
                    dados = doc.to_dict()
                    if dados:
                        dados["_colecao"] = colecao
                        todos_registros.append(dados)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Erro ao ler chunks: {e}")
        cache["erro"] = str(e)
    
    return todos_registros

def processar_dados(dados):
    """Processa os dados extraídos"""
    
    colh_proprias = set()
    colh_fretistas = set()
    cam_proprios = set()
    cam_terceiros = set()
    total_peso = 0
    total_viagens = 0
    
    for reg in dados:
        try:
            # Identifica equipamento
            cod_equip = reg.get("Carreg./Colhed. 1") or reg.get("Carreg./Colhed. 2") or reg.get("Carreg./Colhed. 3") or reg.get("COD. EQUIPAMENTO")
            
            if cod_equip:
                cod_str = str(cod_equip).strip()
                
                # Colhedoras: 80 = Própria, 93 = Fretista
                if cod_str.startswith("80"):
                    colh_proprias.add(cod_str)
                elif cod_str.startswith("93"):
                    colh_fretistas.add(cod_str)
            
            # Caminhões da frota motriz
            frota = reg.get("Frota Motriz") or reg.get("frota_motriz")
            if frota:
                frota_str = str(frota).strip()
                if frota_str.startswith("31"):
                    cam_proprios.add(frota_str)
                elif frota_str.startswith("91"):
                    cam_terceiros.add(frota_str)
            
            # Peso líquido
            peso = reg.get("Peso Líquido") or reg.get("peso_liquido") or 0
            try:
                peso_num = float(str(peso).replace(",", "."))
                if peso_num > 0:
                    total_peso += peso_num
                    total_viagens += 1
            except:
                pass
                
        except Exception as e:
            continue
    
    return {
        "colhedoras_proprias": len(colh_proprias),
        "colhedoras_fretistas": len(colh_fretistas),
        "caminhoes_proprios": len(cam_proprios),
        "caminhoes_terceiros": len(cam_terceiros),
        "total_peso_liquido": total_peso,
        "total_viagens": total_viagens,
        "total_registros": len(dados)
    }

async def sincronizar_dados():
    """Sincroniza dados do Firebase"""
    global cache
    
    cache["carregando"] = True
    
    try:
        dados = await ler_colecao_chunks()
        
        if dados:
            stats = processar_dados(dados)
            
            cache.update({
                "dados": dados[:100],  # Guarda apenas os primeiros 100
                "total_registros": stats["total_registros"],
                "colhedoras_proprias": stats["colhedoras_proprias"],
                "colhedoras_fretistas": stats["colhedoras_fretistas"],
                "caminhoes_proprios": stats["caminhoes_proprios"],
                "caminhoes_terceiros": stats["caminhoes_terceiros"],
                "total_peso_liquido": stats["total_peso_liquido"],
                "total_viagens": stats["total_viagens"],
                "ultima_sync": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "carregando": False,
                "erro": None
            })
            
            print(f"✅ Sincronizado: {stats['total_registros']} registros")
            print(f"   🚜 Colhedoras: {stats['colhedoras_proprias']} próprias, {stats['colhedoras_fretistas']} fretistas")
            print(f"   🚛 Caminhões: {stats['caminhoes_proprios']} próprios, {stats['caminhoes_terceiros']} terceiros")
            print(f"   📊 Peso total: {stats['total_peso_liquido']:,.0f} t")
            
        else:
            cache["carregando"] = False
            cache["erro"] = "Nenhum dado encontrado"
            
    except Exception as e:
        cache["carregando"] = False
        cache["erro"] = str(e)
        print(f"❌ Erro na sincronização: {e}")

@app.on_event("startup")
async def startup():
    asyncio.create_task(sincronizar_dados())

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
                padding: 10px 16px;
                border-radius: 8px;
                margin: 5px;
            }
            .metric-value {
                font-size: 1.3rem;
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
                <h3>📊 Dados Carregados</h3>
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
                    <li>"Qual o peso total moído?"</li>
                    <li>"Quantas viagens foram realizadas?"</li>
                    <li>"Quantos caminhões próprios?"</li>
                </ul>
            </div>
        </div>

        <script>
            let mediaRecorder = null;
            let audioChunks = [];
            let isRecording = false;
            let handsFreeMode = false;

            async function carregarStatus() {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    
                    document.getElementById('status').innerHTML = `
                        <p><span class="status-dot ${data.firebase_conectado ? 'online' : 'offline'}"></span>
                        Firebase: ${data.firebase_conectado ? '✅ CONECTADO' : '❌ DESCONECTADO'}</p>
                        <p>🎤 Groq: ${data.groq_ok ? '✅ Disponível' : '❌ Não configurado'}</p>
                        <p>🕐 ${data.hora}</p>
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
                                <div>colhedoras próprias</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.colhedoras_fretistas}</div>
                                <div>colhedoras fretistas</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${(data.total_peso / 1000).toFixed(1)}</div>
                                <div>mil toneladas</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.total_viagens.toLocaleString()}</div>
                                <div>viagens</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.caminhoes_proprios}</div>
                                <div>caminhões próprios</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${data.caminhoes_terceiros}</div>
                                <div>caminhões terceiros</div>
                            </div>
                            <p style="margin-top: 12px; font-size: 0.8rem;">📅 Última sincronização: ${data.ultima_sync || 'Nunca'}</p>
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

            carregarStatus();
            setInterval(carregarStatus, 10000);
        </script>
    </body>
    </html>
    """)

@app.get("/api/status")
async def status():
    return {
        "firebase_conectado": firebase_status == "Conectado",
        "groq_ok": bool(GROQ_KEY),
        "total_registros": cache["total_registros"],
        "colhedoras_proprias": cache["colhedoras_proprias"],
        "colhedoras_fretistas": cache["colhedoras_fretistas"],
        "caminhoes_proprios": cache["caminhoes_proprios"],
        "caminhoes_terceiros": cache["caminhoes_terceiros"],
        "total_peso": cache["total_peso_liquido"],
        "total_viagens": cache["total_viagens"],
        "ultima_sync": cache["ultima_sync"],
        "carregando": cache["carregando"],
        "hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    }

@app.get("/api/dados")
async def get_dados():
    return {
        "total_registros": cache["total_registros"],
        "colhedoras_proprias": cache["colhedoras_proprias"],
        "colhedoras_fretistas": cache["colhedoras_fretistas"],
        "caminhoes_proprios": cache["caminhoes_proprios"],
        "caminhoes_terceiros": cache["caminhoes_terceiros"],
        "total_peso": cache["total_peso_liquido"],
        "total_viagens": cache["total_viagens"],
        "ultima_sync": cache["ultima_sync"],
        "carregando": cache["carregando"]
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
    
    if "aprenda" in text.lower() or "grave" in text.lower():
        return {"answer": "Memorizado, Senhor.", "session_id": session_id}
    
    # Contexto com dados REAIS
    contexto = f"""
DADOS REAIS DA USINA PITANGUEIRAS (PRODUÇÃO 2025):

- Registros processados: {cache['total_registros']}
- Colhedoras próprias: {cache['colhedoras_proprias']}
- Colhedoras fretistas: {cache['colhedoras_fretistas']}
- Caminhões próprios: {cache['caminhoes_proprios']}
- Caminhões terceiros: {cache['caminhoes_terceiros']}
- Peso total moído: {cache['total_peso_liquido']:.0f} toneladas
- Total de viagens: {cache['total_viagens']}
"""
    
    system_prompt = f"""Você é KIRA, Analista Operacional da Usina Pitangueiras.

{contexto}

REGRAS IMPORTANTES:
- USE SOMENTE OS DADOS FORNECIDOS ACIMA
- Se não tiver dados, diga "Senhor, aguardando dados do Firebase"
- NUNCA invente números
- Trate o usuário como "Senhor"
- Respostas curtas e objetivas (máximo 15 palavras)

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

@app.post("/api/sync")
async def forcar_sincronizacao():
    await sincronizar_dados()
    return {"status": "sincronizado", "registros": cache["total_registros"]}
