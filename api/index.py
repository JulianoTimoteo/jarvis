"""
KIRA - Analista de Cana-de-Açúcar
Lendo chunks corretamente do Firebase
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_KEY = os.getenv("GROQ_KEY", "")
FIREBASE_API_KEY = "AIzaSyADUuqh_THzGInTSytxzUFEwHV5LmwdvYc"
PROJECT_ID = "agroanalytics-api"

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

def extrair_dados_da_linha(linha, cabecalho):
    """Extrai dados de uma linha do chunk"""
    if len(linha) != len(cabecalho):
        return None
    
    registro = {}
    for i, campo in enumerate(cabecalho):
        valor = linha[i]
        if campo in ["Peso Líquido", "Peso Bruto", "Peso Tara"]:
            try:
                if valor and valor != "" and valor != " ":
                    valor = float(str(valor).replace(",", "."))
                else:
                    valor = 0
            except:
                valor = 0
        registro[campo] = valor
    
    return registro

def carregar_dados():
    """Carrega dados do Firebase lendo os chunks individualmente"""
    global dados_reais
    
    try:
        # Primeiro, lista todos os documentos dentro de PRODUCAO_07_2025
        list_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/PRODUCAO_07_2025?key={FIREBASE_API_KEY}"
        
        print(f"🔍 Listando documentos em PRODUCAO_07_2025...")
        response = httpx.get(list_url, timeout=30.0)
        
        if response.status_code != 200:
            dados_reais["erro"] = f"Erro {response.status_code}: {response.text[:200]}"
            print(f"❌ {dados_reais['erro']}")
            return
        
        dados = response.json()
        documentos = dados.get("documents", [])
        
        print(f"📁 Documentos encontrados: {len(documentos)}")
        
        # Procura o documento "chunks" que contém todos os chunks
        chunks_doc = None
        for doc in documentos:
            doc_name = doc.get("name", "")
            if "chunks" in doc_name:
                chunks_doc = doc
                print(f"✅ Encontrado: {doc_name}")
                break
        
        if not chunks_doc:
            dados_reais["erro"] = "Documento 'chunks' não encontrado"
            print(f"❌ {dados_reais['erro']}")
            return
        
        # Agora lê o documento chunks
        chunks_url = f"https://firestore.googleapis.com/v1/{chunks_doc['name']}?key={FIREBASE_API_KEY}"
        chunks_response = httpx.get(chunks_url, timeout=30.0)
        
        if chunks_response.status_code != 200:
            dados_reais["erro"] = f"Erro ao ler chunks: {chunks_response.status_code}"
            return
        
        chunks_data = chunks_response.json()
        fields = chunks_data.get("fields", {})
        
        # Pega o cabeçalho
        cab_field = fields.get("cab", {})
        cab_array = cab_field.get("arrayValue", {}).get("values", [])
        cabecalho = [c.get("stringValue", "") for c in cab_array]
        
        print(f"📋 Cabeçalho: {len(cabecalho)} campos")
        
        # Pega os chunks (subdocumentos)
        chunks_field = fields.get("chunks", {})
        chunks_map = chunks_field.get("mapValue", {}).get("fields", {})
        
        print(f"📦 Chunks encontrados: {len(chunks_map)}")
        
        # Processa cada chunk
        colh_proprias = set()
        colh_fretistas = set()
        cam_proprios = set()
        cam_terceiros = set()
        peso_total = 0
        total_viagens = 0
        registros = 0
        
        for chunk_name, chunk_data in chunks_map.items():
            # Cada chunk tem um campo "rows"
            rows_field = chunk_data.get("mapValue", {}).get("fields", {}).get("rows", {})
            rows_array = rows_field.get("arrayValue", {}).get("values", [])
            
            print(f"   Processando {chunk_name}: {len(rows_array)} linhas")
            
            for row in rows_array:
                row_values = row.get("arrayValue", {}).get("values", [])
                linha = []
                for v in row_values:
                    # Pega o valor de cada campo (pode ser string, int, double)
                    if "stringValue" in v:
                        linha.append(v["stringValue"])
                    elif "integerValue" in v:
                        linha.append(v["integerValue"])
                    elif "doubleValue" in v:
                        linha.append(v["doubleValue"])
                    else:
                        linha.append("")
                
                if len(linha) != len(cabecalho):
                    continue
                
                # Converte para dicionário
                reg = {}
                for i, campo in enumerate(cabecalho):
                    reg[campo] = linha[i]
                
                registros += 1
                
                # Colhedoras (Carreg./Colhed. 1, 2, 3)
                for i in range(1, 4):
                    colh = reg.get(f"Carreg./Colhed. {i}")
                    if colh and colh != "" and colh != " ":
                        colh_str = str(colh).strip()
                        if colh_str.startswith("80"):
                            colh_proprias.add(colh_str)
                        elif colh_str.startswith("93"):
                            colh_fretistas.add(colh_str)
                
                # Caminhões (Frota Motriz)
                frota = reg.get("Frota Motriz")
                if frota and frota != "":
                    frota_str = str(frota).strip()
                    if frota_str.startswith("31"):
                        cam_proprios.add(frota_str)
                    elif frota_str.startswith("91"):
                        cam_terceiros.add(frota_str)
                
                # Peso Líquido
                peso = reg.get("Peso Líquido", 0)
                if peso and peso != "" and peso != " ":
                    try:
                        peso_num = float(str(peso).replace(",", "."))
                        if peso_num > 0:
                            peso_total += peso_num
                            total_viagens += 1
                    except:
                        pass
                
                # Mostra progresso
                if registros % 1000 == 0:
                    print(f"      Processados {registros} registros...")
        
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
        
        print(f"\n✅ DADOS CARREGADOS COM SUCESSO!")
        print(f"   📊 {registros} registros processados")
        print(f"   🚜 Colhedoras próprias: {len(colh_proprias)}")
        print(f"   🚜 Colhedoras fretistas: {len(colh_fretistas)}")
        print(f"   🚛 Caminhões próprios: {len(cam_proprios)}")
        print(f"   🚛 Caminhões terceiros: {len(cam_terceiros)}")
        print(f"   📈 Peso total: {peso_total/1000:,.0f} toneladas")
        print(f"   🚚 Viagens: {total_viagens}")
        
    except Exception as e:
        dados_reais["erro"] = str(e)
        print(f"❌ Erro: {e}")

# Carrega os dados na inicialização
try:
    carregar_dados()
except Exception as e:
    print(f"Erro na inicialização: {e}")
    dados_reais["erro"] = str(e)

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
            ''' if dados_reais["carregado"] else f'<p class="error">❌ {dados_reais["erro"] or "Carregando dados..."}</p>'}
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
- Registros processados: {dados_reais["total_registros"]}
- Colhedoras próprias (prefixo 80): {dados_reais["colhedoras_proprias"]}
- Colhedoras fretistas (prefixo 93): {dados_reais["colhedoras_fretistas"]}
- Caminhões próprios (prefixo 31): {dados_reais["caminhoes_proprios"]}
- Caminhões terceiros (prefixo 91): {dados_reais["caminhoes_terceiros"]}
- Peso total moído: {dados_reais["peso_total_kg"]/1000:.0f} toneladas
- Total de viagens: {dados_reais["total_viagens"]}
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
