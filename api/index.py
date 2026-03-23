"""
KIRA - Analista de Cana-de-Açúcar
Dados REAIS do Firebase
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

# Tentar importar Firebase
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_OK = True
except:
    FIREBASE_OK = False

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_KEY = os.getenv("GROQ_KEY", "")
FIREBASE_CRED = os.getenv("FIREBASE_CRED_JSON", "")

# Cache dos dados reais
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

# Inicializar Firebase
db = None
if FIREBASE_OK and FIREBASE_CRED:
    try:
        cred_dict = json.loads(FIREBASE_CRED)
        cred = credentials.Certificate(cred_dict)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ Firebase conectado")
    except Exception as e:
        print(f"❌ Firebase: {e}")

def carregar_dados():
    """Carrega dados do Firebase"""
    global dados_reais
    
    if not db:
        dados_reais["erro"] = "Firebase não conectado"
        return
    
    try:
        # Tenta ler a coleção PRODUCAO_07_2025
        doc_ref = db.collection("PRODUCAO_07_2025").document("chunks")
        doc = doc_ref.get()
        
        if not doc.exists:
            dados_reais["erro"] = "Coleção PRODUCAO_07_2025 não encontrada"
            return
        
        dados = doc.to_dict()
        cabecalho = dados.get("cab", [])
        chunks = dados.get("chunks", {})
        
        # Processa os dados
        colh_proprias = set()
        colh_fretistas = set()
        cam_proprios = set()
        cam_terceiros = set()
        peso_total = 0
        total_viagens = 0
        registros = 0
        
        for chunk_name, chunk_data in chunks.items():
            if "rows" in chunk_data:
                linhas = chunk_data["rows"]
                for linha in linhas:
                    if len(linha) != len(cabecalho):
                        continue
                    
                    # Converte linha em dicionário
                    reg = {}
                    for i, campo in enumerate(cabecalho):
                        reg[campo] = linha[i]
                    
                    registros += 1
                    
                    # Colhedoras
                    for i in range(1, 4):
                        colh = reg.get(f"Carreg./Colhed. {i}")
                        if colh:
                            colh_str = str(colh).strip()
                            if colh_str.startswith("80"):
                                colh_proprias.add(colh_str)
                            elif colh_str.startswith("93"):
                                colh_fretistas.add(colh_str)
                    
                    # Caminhões
                    frota = reg.get("Frota Motriz")
                    if frota:
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
        
        print(f"✅ Dados carregados: {registros} registros")
        print(f"   🚜 Colhedoras: {len(colh_proprias)} próprias, {len(colh_fretistas)} fretistas")
        print(f"   🚛 Caminhões: {len(cam_proprios)} próprios, {len(cam_terceiros)} terceiros")
        print(f"   📊 Peso: {peso_total:,.0f} kg")
        
    except Exception as e:
        dados_reais["erro"] = str(e)
        print(f"❌ Erro ao carregar: {e}")

# Carrega os dados na inicialização
try:
    carregar_dados()
except Exception as e:
    print(f"Erro na inicialização: {e}")

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
            <h3>📊 DADOS REAIS DO FIREBASE</h3>
            {f'''
            <div class="metric"><div class="value">{dados_reais["total_registros"]:,}</div>registros</div>
            <div class="metric"><div class="value">{dados_reais["colhedoras_proprias"]}</div>colhedoras próprias</div>
            <div class="metric"><div class="value">{dados_reais["colhedoras_fretistas"]}</div>colhedoras fretistas</div>
            <div class="metric"><div class="value">{dados_reais["peso_total_kg"]/1000:,.0f}</div>toneladas</div>
            <div class="metric"><div class="value">{dados_reais["total_viagens"]:,}</div>viagens</div>
            <div class="metric"><div class="value">{dados_reais["caminhoes_proprios"]}</div>caminhões próprios</div>
            <div class="metric"><div class="value">{dados_reais["caminhoes_terceiros"]}</div>caminhões terceiros</div>
            <p style="margin-top: 10px;">📅 Atualizado: {dados_reais["ultima_atualizacao"] or "Nunca"}</p>
            ''' if dados_reais["carregado"] else f'<p class="warning">⚠️ {dados_reais["erro"] or "Carregando dados..."}</p>'}
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
    
    # Constrói o contexto com dados REAIS
    if dados_reais["carregado"]:
        contexto = f"""
DADOS REAIS DA USINA PITANGUEIRAS (CANA-DE-AÇÚCAR):
- Registros processados: {dados_reais["total_registros"]}
- Colhedoras próprias (prefixo 80): {dados_reais["colhedoras_proprias"]}
- Colhedoras fretistas (prefixo 93): {dados_reais["colhedoras_fretistas"]}
- Caminhões próprios (prefixo 31): {dados_reais["caminhoes_proprios"]}
- Caminhões terceiros (prefixo 91): {dados_reais["caminhoes_terceiros"]}
- Peso total moído: {dados_reais["peso_total_kg"]/1000:.0f} toneladas
- Total de viagens: {dados_reais["total_viagens"]}
"""
    else:
        contexto = "Aguardando dados do Firebase. Conecte-se ao banco de dados."
    
    system_prompt = f"""Você é KIRA, Analista de Cana-de-Açúcar da Usina Pitangueiras.

{contexto}

REGRAS OBRIGATÓRIAS:
1. VOCÊ SÓ FALA SOBRE CANA-DE-AÇÚCAR
2. USE SOMENTE OS NÚMEROS ACIMA - NUNCA INVENTE
3. Se perguntarem sobre soja, milho, dinheiro ou qualquer outra coisa, responda: "Senhor, meu banco de dados é exclusivo de cana-de-açúcar."
4. Trate o usuário como "Senhor"
5. Respostas curtas (máximo 15 palavras)
6. Seja formal e objetiva

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
