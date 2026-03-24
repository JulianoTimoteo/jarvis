"""
KIRA - Versão Final com Firebase Admin SDK
"""

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import tempfile
import json
from pathlib import Path
from datetime import datetime

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_KEY = os.getenv("GROQ_KEY", "")

# Inicializar Firebase com a chave que você tem
cred_path = Path(__file__).parent.parent / "firebase-credentials.json"

# Se o arquivo não existir, tenta criar com a variável de ambiente
if not cred_path.exists():
    firebase_cred_json = os.getenv("FIREBASE_CRED_JSON", "")
    if firebase_cred_json:
        with open(cred_path, "w") as f:
            f.write(firebase_cred_json)

# Inicializar
if not firebase_admin._apps and cred_path.exists():
    try:
        cred = credentials.Certificate(str(cred_path))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase conectado!")
    except Exception as e:
        print(f"❌ Erro Firebase: {e}")
        db = None
else:
    db = None

# Cache dos dados
dados_reais = {
    "carregado": False,
    "total_registros": 0,
    "colhedoras_proprias": 0,
    "colhedoras_fretistas": 0,
    "caminhoes_proprios": 0,
    "caminhoes_terceiros": 0,
    "peso_total_kg": 0,
    "total_viagens": 0,
    "ultima_atualizacao": None,
    "erro": None
}

def carregar_dados():
    """Carrega dados usando Firebase Admin SDK"""
    global dados_reais
    
    if not db:
        dados_reais["erro"] = "Firebase não conectado. Verifique as credenciais."
        return
    
    try:
        print("🔍 Buscando dados em PRODUCAO_07_2025...")
        
        # Tenta acessar a coleção
        colecao_ref = db.collection("PRODUCAO_07_2025")
        docs = colecao_ref.limit(10).get()
        
        print(f"📁 Documentos encontrados: {len(docs)}")
        
        if len(docs) == 0:
            dados_reais["erro"] = "Nenhum documento encontrado na coleção PRODUCAO_07_2025"
            return
        
        # Lista todos os documentos
        todos_docs = colecao_ref.get()
        
        colh_proprias = set()
        colh_fretistas = set()
        cam_proprios = set()
        cam_terceiros = set()
        peso_total = 0
        total_viagens = 0
        registros = 0
        
        for doc in todos_docs:
            dados = doc.to_dict()
            print(f"   Documento: {doc.id} - Campos: {list(dados.keys())[:5]}")
            
            # Verifica se é um chunk com rows
            if "rows" in dados and "cab" in dados:
                cabecalho = dados["cab"]
                linhas = dados["rows"]
                
                print(f"      Chunk com {len(linhas)} linhas")
                
                for linha in linhas:
                    if len(linha) != len(cabecalho):
                        continue
                    
                    # Converte para dicionário
                    reg = {}
                    for i, campo in enumerate(cabecalho):
                        reg[campo] = linha[i]
                    
                    registros += 1
                    
                    # Colhedoras
                    for i in range(1, 4):
                        colh = reg.get(f"Carreg./Colhed. {i}")
                        if colh and colh != "":
                            colh_str = str(colh).strip()
                            if colh_str.startswith("80"):
                                colh_proprias.add(colh_str)
                            elif colh_str.startswith("93"):
                                colh_fretistas.add(colh_str)
                    
                    # Caminhões
                    frota = reg.get("Frota Motriz")
                    if frota and frota != "":
                        frota_str = str(frota).strip()
                        if frota_str.startswith("31"):
                            cam_proprios.add(frota_str)
                        elif frota_str.startswith("91"):
                            cam_terceiros.add(frota_str)
                    
                    # Peso
                    peso = reg.get("Peso Líquido", 0)
                    if peso and peso != "":
                        try:
                            peso_num = float(str(peso).replace(",", "."))
                            if peso_num > 0:
                                peso_total += peso_num
                                total_viagens += 1
                        except:
                            pass
        
        # Atualiza cache
        dados_reais["carregado"] = True
        dados_reais["total_registros"] = registros
        dados_reais["colhedoras_proprias"] = len(colh_proprias)
        dados_reais["colhedoras_fretistas"] = len(colh_fretistas)
        dados_reais["caminhoes_proprios"] = len(cam_proprios)
        dados_reais["caminhoes_terceiros"] = len(cam_terceiros)
        dados_reais["peso_total_kg"] = peso_total
        dados_reais["total_viagens"] = total_viagens
        dados_reais["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        dados_reais["erro"] = None
        
        print(f"\n✅ DADOS CARREGADOS!")
        print(f"   Registros: {registros}")
        print(f"   Colhedoras próprias: {len(colh_proprias)}")
        print(f"   Colhedoras fretistas: {len(colh_fretistas)}")
        print(f"   Caminhões próprios: {len(cam_proprios)}")
        print(f"   Caminhões terceiros: {len(cam_terceiros)}")
        print(f"   Peso total: {peso_total/1000:,.0f} t")
        
    except Exception as e:
        dados_reais["erro"] = str(e)
        print(f"❌ Erro: {e}")

# Carrega os dados
carregar_dados()

@app.get("/")
async def index():
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>KIRA - Cana-de-Açúcar</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                background: #0a0a0f;
                color: white;
                font-family: monospace;
                padding: 20px;
                text-align: center;
            }}
            button {{
                background: #ec4899;
                border: none;
                padding: 15px 30px;
                border-radius: 50px;
                color: white;
                font-size: 18px;
                cursor: pointer;
                margin: 10px;
            }}
            .box {{
                background: #1a1a2e;
                padding: 20px;
                border-radius: 10px;
                margin: 20px auto;
                max-width: 600px;
                text-align: left;
            }}
            .success {{ color: #10b981; }}
            .warning {{ color: #f59e0b; }}
            .error {{ color: #ef4444; }}
            .metric {{
                display: inline-block;
                background: #0a0a0f;
                padding: 10px;
                margin: 5px;
                border-radius: 8px;
            }}
            .value {{
                font-size: 1.5rem;
                font-weight: bold;
                color: #ec4899;
            }}
        </style>
    </head>
    <body>
        <h1>🤖 KIRA</h1>
        <p>Analista de Cana-de-Açúcar - Usina Pitangueiras</p>
        
        <div class="box">
            <h3>📊 DADOS DO FIREBASE</h3>
            {f'''
            <div class="metric"><div class="value">{dados_reais["total_registros"]:,}</div>registros</div>
            <div class="metric"><div class="value">{dados_reais["colhedoras_proprias"]}</div>colhedoras próprias</div>
            <div class="metric"><div class="value">{dados_reais["colhedoras_fretistas"]}</div>colhedoras fretistas</div>
            <div class="metric"><div class="value">{dados_reais["peso_total_kg"]/1000:,.0f}</div>toneladas</div>
            <div class="metric"><div class="value">{dados_reais["total_viagens"]:,}</div>viagens</div>
            <div class="metric"><div class="value">{dados_reais["caminhoes_proprios"]}</div>caminhões próprios</div>
            <div class="metric"><div class="value">{dados_reais["caminhoes_terceiros"]}</div>caminhões terceiros</div>
            <p style="margin-top: 10px;">📅 Atualizado: {dados_reais["ultima_atualizacao"] or "Nunca"}</p>
            ''' if dados_reais["carregado"] else f'<p class="error">❌ {dados_reais["erro"] or "Carregando..."}</p>'}
        </div>
        
        <div class="box">
            <h3>🎤 Fale com a KIRA</h3>
            <button onclick="startRecording()">🎙️ FALAR (5 segundos)</button>
            <div id="result" style="margin-top: 20px; padding: 10px; background: #0a0a0f; border-radius: 8px;"></div>
        </div>
        
        <div class="box">
            <h3>📋 Perguntas sobre CANA-DE-AÇÚCAR</h3>
            <ul>
                <li>"Quantas colhedoras próprias?"</li>
                <li>"Quantas colhedoras fretistas?"</li>
                <li>"Qual o peso total moído?"</li>
                <li>"Quantas viagens?"</li>
                <li>"Quantos caminhões próprios?"</li>
            </ul>
        </div>
        
        <script>
            let mediaRecorder;
            let chunks = [];
            
            async function startRecording() {{
                try {{
                    const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
                    mediaRecorder = new MediaRecorder(stream);
                    chunks = [];
                    
                    mediaRecorder.ondataavailable = e => chunks.push(e.data);
                    mediaRecorder.onstop = async () => {{
                        const blob = new Blob(chunks, {{ type: 'audio/webm' }});
                        const form = new FormData();
                        form.append('audio', blob);
                        
                        document.getElementById('result').innerHTML = '🎙️ Processando...';
                        
                        const trans = await fetch('/api/transcribe', {{ method: 'POST', body: form }});
                        const {{ text }} = await trans.json();
                        
                        const chatForm = new FormData();
                        chatForm.append('text', text);
                        const chatRes = await fetch('/api/chat', {{ method: 'POST', body: chatForm }});
                        const {{ answer }} = await chatRes.json();
                        
                        document.getElementById('result').innerHTML = `
                            <strong>🗣️ Você:</strong> ${{text}}<br>
                            <strong>🤖 KIRA:</strong> ${{answer}}
                        `;
                        
                        const speech = new SpeechSynthesisUtterance(answer);
                        speech.lang = 'pt-BR';
                        speechSynthesis.speak(speech);
                    }};
                    
                    mediaRecorder.start();
                    setTimeout(() => mediaRecorder.stop(), 5000);
                    document.getElementById('result').innerHTML = '🎙️ Gravando... Fale sobre cana-de-açúcar';
                }} catch (error) {{
                    document.getElementById('result').innerHTML = '❌ Erro: ' + error.message;
                }}
            }}
        </script>
    </body>
    </html>
    """)

@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    if not GROQ_KEY:
        return {"text": "Groq não configurado"}
    
    content = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    
    async with httpx.AsyncClient() as client:
        with open(tmp_path, "rb") as f:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": ("audio.webm", f, "audio/webm")},
                data={"model": "whisper-large-v3-turbo", "language": "pt"}
            )
    
    Path(tmp_path).unlink()
    return {"text": r.json().get("text", "")}

@app.post("/api/chat")
async def chat(text: str = Form(...)):
    if not GROQ_KEY:
        return {"answer": "Groq não configurado"}
    
    if dados_reais["carregado"]:
        contexto = f"""
DADOS REAIS DA USINA PITANGUEIRAS (CANA-DE-AÇÚCAR):
- Registros: {dados_reais["total_registros"]}
- Colhedoras próprias: {dados_reais["colhedoras_proprias"]}
- Colhedoras fretistas: {dados_reais["colhedoras_fretistas"]}
- Caminhões próprios: {dados_reais["caminhoes_proprios"]}
- Caminhões terceiros: {dados_reais["caminhoes_terceiros"]}
- Peso total: {dados_reais["peso_total_kg"]/1000:.0f} toneladas
- Viagens: {dados_reais["total_viagens"]}
"""
    else:
        contexto = f"ERRO: {dados_reais['erro']}"
    
    system_prompt = f"""Você é KIRA, Analista de Cana-de-Açúcar da Usina Pitangueiras.

{contexto}

REGRAS:
1. SÓ FALE SOBRE CANA-DE-AÇÚCAR
2. USE SOMENTE OS NÚMEROS ACIMA
3. Se perguntarem sobre soja, milho ou dinheiro: "Senhor, meu banco de dados é exclusivo de cana-de-açúcar."
4. Trate o usuário como "Senhor"
5. Respostas curtas (máximo 15 palavras)

RESPOSTA:"""

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.3,
                "max_tokens": 100
            }
        )
    
    return {"answer": r.json()["choices"][0]["message"]["content"]}
