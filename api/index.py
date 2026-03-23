"""
KIRA — Versão de Diagnóstico
Mostra exatamente o que está sendo lido do Firebase
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
    "diagnostico": [],
    "ultima_sync": None,
    "erro": None,
    "colecoes_encontradas": [],
    "total_registros": 0
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

app = FastAPI(title="KIRA Diagnóstico", version="13.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# FUNÇÃO DE DIAGNÓSTICO - VAI MOSTRAR TUDO
# ============================================================
async def diagnosticar_firebase():
    """Diagnostica todas as coleções do Firebase"""
    global cache
    
    if not db:
        cache["erro"] = "Firebase não conectado"
        return
    
    cache["diagnostico"] = []
    cache["colecoes_encontradas"] = []
    
    # Lista de todas as coleções que você tem
    colecoes = [
        "PRODUCAO_07_2025",
        "PRODUCAO_08_2025", 
        "PRODUCAO_09_2025",
        "tpl",
        "acmSafra",
        "snapshots",
        "snapshots_bulk"
    ]
    
    print("\n" + "=" * 60)
    print("🔍 DIAGNÓSTICO DO FIREBASE")
    print("=" * 60)
    
    for colecao in colecoes:
        print(f"\n📁 Coleção: {colecao}")
        
        try:
            # Primeiro tenta encontrar o documento "chunks"
            doc_ref = db.collection(colecao).document("chunks")
            doc = doc_ref.get()
            
            if doc.exists:
                dados = doc.to_dict()
                print(f"   ✅ Documento 'chunks' encontrado!")
                
                # Mostra o que tem no documento
                campos = list(dados.keys())
                print(f"   📋 Campos: {campos}")
                
                if "cab" in dados:
                    cabecalho = dados["cab"]
                    print(f"   📊 Cabeçalho: {len(cabecalho)} campos")
                    print(f"      Exemplo: {cabecalho[:5]}...")
                
                if "chunks" in dados:
                    chunks = dados["chunks"]
                    print(f"   📦 Total de chunks: {len(chunks)}")
                    
                    total_linhas = 0
                    for chunk_name, chunk_data in list(chunks.items())[:3]:  # Mostra só 3 chunks
                        if "rows" in chunk_data:
                            linhas = chunk_data["rows"]
                            total_linhas += len(linhas)
                            print(f"      - {chunk_name}: {len(linhas)} linhas")
                            if len(linhas) > 0:
                                print(f"        Primeira linha: {linhas[0][:5]}...")
                    
                    print(f"   📈 Total de linhas: {total_linhas}")
                    cache["total_registros"] += total_linhas
                    cache["colecoes_encontradas"].append(f"{colecao} (chunks: {total_linhas} linhas)")
                    
                    # Salva um exemplo para debug
                    if total_linhas > 0 and len(cache["diagnostico"]) < 3:
                        primeiro_chunk = list(chunks.values())[0]
                        if "rows" in primeiro_chunk and len(primeiro_chunk["rows"]) > 0:
                            cache["diagnostico"].append({
                                "colecao": colecao,
                                "cabecalho": cabecalho[:10] if cabecalho else [],
                                "primeira_linha": primeiro_chunk["rows"][0][:10]
                            })
            else:
                # Tenta ler como documentos normais
                docs = db.collection(colecao).limit(5).get()
                if len(docs) > 0:
                    print(f"   ✅ {len(docs)} documentos encontrados (estrutura normal)")
                    cache["colecoes_encontradas"].append(f"{colecao} ({len(docs)} docs)")
                    for doc in docs[:1]:
                        dados = doc.to_dict()
                        print(f"      Campos: {list(dados.keys())[:10]}")
                else:
                    print(f"   ⚠️ Nenhum documento encontrado")
                    
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            cache["erro"] = str(e)
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTADO DO DIAGNÓSTICO:")
    print(f"   Coleções com dados: {len(cache['colecoes_encontradas'])}")
    print(f"   Total de registros: {cache['total_registros']}")
    print("=" * 60)
    
    cache["ultima_sync"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

@app.on_event("startup")
async def startup():
    asyncio.create_task(diagnosticar_firebase())

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
        <title>KIRA - Diagnóstico</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
                color: #e2e8f0;
                font-family: monospace;
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 900px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 30px; }
            .logo { font-size: 2.5rem; color: #ec4899; }
            .card {
                background: rgba(26, 26, 46, 0.9);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                border-left: 4px solid #ec4899;
            }
            pre {
                background: #0a0a0f;
                padding: 15px;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 0.8rem;
                margin-top: 10px;
            }
            .success { color: #10b981; }
            .error { color: #ef4444; }
            .info { color: #f59e0b; }
            button {
                background: #ec4899;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                color: white;
                cursor: pointer;
                margin-top: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🔍 KIRA - DIAGNÓSTICO</div>
                <p>Verificando conexão com Firebase</p>
            </div>

            <div class="card">
                <h3>📡 Status</h3>
                <div id="status"></div>
            </div>

            <div class="card">
                <h3>📊 Resultado do Diagnóstico</h3>
                <div id="diagnostico"></div>
            </div>

            <div class="card">
                <h3>🎤 Teste de Voz</h3>
                <button onclick="startRecording()">🎙️ TESTAR MICROFONE</button>
                <div id="transcript" style="margin-top: 10px; padding: 10px; background: #0a0a0f; border-radius: 8px;"></div>
                <div id="response" style="margin-top: 10px; padding: 10px; background: #0a0a0f; border-radius: 8px; color: #ec4899;"></div>
            </div>
        </div>

        <script>
            let mediaRecorder = null;
            let audioChunks = [];

            async function carregarDiagnostico() {
                try {
                    const res = await fetch('/api/diagnostico');
                    const data = await res.json();
                    
                    document.getElementById('status').innerHTML = `
                        <p><span class="${data.firebase_conectado ? 'success' : 'error'}">●</span> 
                        Firebase: ${data.firebase_conectado ? 'CONECTADO' : 'DESCONECTADO'}</p>
                        <p>🕐 Última verificação: ${data.ultima_sync || 'Nunca'}</p>
                        ${data.erro ? `<p class="error">❌ Erro: ${data.erro}</p>` : ''}
                    `;
                    
                    let html = `<p><strong>Coleções encontradas:</strong> ${data.colecoes_encontradas.length}</p>`;
                    if (data.colecoes_encontradas.length > 0) {
                        html += '<ul>';
                        data.colecoes_encontradas.forEach(c => {
                            html += `<li>📁 ${c}</li>`;
                        });
                        html += '</ul>';
                        html += `<p><strong>Total de registros:</strong> ${data.total_registros.toLocaleString()}</p>`;
                    } else {
                        html += '<p class="error">⚠️ Nenhuma coleção encontrada com dados!</p>';
                        html += '<p class="info">Verifique se as coleções existem no Firebase e se as regras de leitura estão corretas.</p>';
                    }
                    
                    if (data.diagnostico && data.diagnostico.length > 0) {
                        html += '<hr><p><strong>Exemplo de estrutura:</strong></p>';
                        html += `<pre>${JSON.stringify(data.diagnostico[0], null, 2)}</pre>`;
                    }
                    
                    document.getElementById('diagnostico').innerHTML = html;
                    
                } catch (error) {
                    document.getElementById('diagnostico').innerHTML = `<p class="error">Erro ao carregar: ${error.message}</p>`;
                }
            }

            async function startRecording() {
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

                        document.getElementById('transcript').innerHTML = 'Processando...';

                        const transcribeRes = await fetch('/api/transcribe', { method: 'POST', body: formData });
                        const { text } = await transcribeRes.json();
                        
                        document.getElementById('transcript').innerHTML = `🗣️ Você: "${text}"`;
                        
                        const chatForm = new FormData();
                        chatForm.append('text', text);
                        const chatRes = await fetch('/api/chat', { method: 'POST', body: chatForm });
                        const { answer } = await chatRes.json();
                        
                        document.getElementById('response').innerHTML = `🤖 KIRA: ${answer}`;
                        
                        const utterance = new SpeechSynthesisUtterance(answer);
                        utterance.lang = 'pt-BR';
                        speechSynthesis.speak(utterance);
                    };

                    mediaRecorder.start();
                    setTimeout(() => mediaRecorder.stop(), 5000);
                    document.getElementById('transcript').innerHTML = '🎙️ Gravando... Fale por 5 segundos';
                    
                } catch (error) {
                    alert('Erro no microfone: ' + error.message);
                }
            }

            carregarDiagnostico();
            setInterval(carregarDiagnostico, 30000);
        </script>
    </body>
    </html>
    """)

@app.get("/api/diagnostico")
async def get_diagnostico():
    return {
        "firebase_conectado": firebase_status == "Conectado",
        "ultima_sync": cache["ultima_sync"],
        "colecoes_encontradas": cache["colecoes_encontradas"],
        "total_registros": cache["total_registros"],
        "diagnostico": cache["diagnostico"],
        "erro": cache["erro"],
        "groq_ok": bool(GROQ_KEY)
    }

@app.post("/api/transcribe")
async def transcrever(audio: UploadFile = File(...)):
    if not GROQ_KEY:
        return {"text": "Groq não configurado"}
    
    try:
        conteudo = await audio.read()
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
    
    # Contexto baseado no diagnóstico
    if cache["total_registros"] > 0:
        contexto = f"""
DIAGNÓSTICO ATUAL:
- Firebase conectado
- {cache['total_registros']} registros encontrados
- Coleções: {', '.join(cache['colecoes_encontradas'][:3])}
"""
    else:
        contexto = """
DIAGNÓSTICO ATUAL:
- Firebase conectado mas NENHUM DADO ENCONTRADO
- Verifique se as coleções existem e têm dados
- Coleções procuradas: PRODUCAO_07_2025, tpl, acmSafra
"""
    
    system_prompt = f"""Você é KIRA, Analista da Usina Pitangueiras.

{contexto}

REGRAS:
- Se não houver dados, informe que o diagnóstico está sendo feito
- Se houver dados, informe os números encontrados
- Respostas curtas e objetivas
- Trate o usuário como "Senhor"

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
    await diagnosticar_firebase()
    return {"status": "diagnóstico concluído", "registros": cache["total_registros"]}
