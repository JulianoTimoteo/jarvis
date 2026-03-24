"""
KIRA - Diagnóstico do Firebase
Lista toda a estrutura de dados
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FIREBASE_API_KEY = "AIzaSyADUuqh_THzGInTSytxzUFEwHV5LmwdvYc"
PROJECT_ID = "agroanalytics-api"

# Cache
diagnostico = {
    "colecoes": [],
    "estrutura": {},
    "erro": None
}

def listar_tudo():
    """Lista toda a estrutura do Firebase"""
    global diagnostico
    
    # Lista todas as coleções
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents?key={FIREBASE_API_KEY}"
    
    try:
        response = httpx.get(url, timeout=30.0)
        if response.status_code != 200:
            diagnostico["erro"] = f"Erro {response.status_code}: {response.text[:200]}"
            return
        
        dados = response.json()
        documentos = dados.get("documents", [])
        
        # Extrai nomes das coleções
        colecoes = {}
        for doc in documentos:
            nome = doc.get("name", "")
            partes = nome.split("/")
            if len(partes) >= 5:
                colecao = partes[5]
                if colecao not in colecoes:
                    colecoes[colecao] = []
                colecoes[colecao].append(nome)
        
        diagnostico["colecoes"] = list(colecoes.keys())
        
        # Para cada coleção, pega a estrutura
        for colecao in list(colecoes.keys())[:5]:  # Limita a 5 coleções
            colecao_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/{colecao}?key={FIREBASE_API_KEY}"
            resp = httpx.get(colecao_url, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("documents", [])
                
                estrutura = []
                for doc in docs[:10]:  # Limita a 10 documentos
                    nome = doc.get("name", "").split("/")[-1]
                    fields = doc.get("fields", {})
                    estrutura.append({
                        "nome": nome,
                        "campos": list(fields.keys())[:10]
                    })
                
                diagnostico["estrutura"][colecao] = estrutura
        
        # Especificamente para PRODUCAO_07_2025
        if "PRODUCAO_07_2025" in colecoes:
            producao_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/PRODUCAO_07_2025?key={FIREBASE_API_KEY}"
            resp = httpx.get(producao_url, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("documents", [])
                
                detalhes = []
                for doc in docs:
                    nome = doc.get("name", "").split("/")[-1]
                    fields = doc.get("fields", {})
                    detalhes.append({
                        "nome": nome,
                        "campos": list(fields.keys())
                    })
                
                diagnostico["estrutura"]["PRODUCAO_07_2025_detalhes"] = detalhes
                
    except Exception as e:
        diagnostico["erro"] = str(e)

# Executa diagnóstico
listar_tudo()

@app.get("/")
async def index():
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>KIRA - Diagnóstico</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                background: #0a0a0f;
                color: white;
                font-family: monospace;
                padding: 20px;
            }}
            .box {{
                background: #1a1a2e;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
                overflow-x: auto;
            }}
            .success {{ color: #10b981; }}
            .error {{ color: #ef4444; }}
            pre {{
                background: #0a0a0f;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <h1>🔍 KIRA - Diagnóstico do Firebase</h1>
        
        <div class="box">
            <h3>📁 Coleções encontradas:</h3>
            <pre>{json.dumps(diagnostico["colecoes"], indent=2, ensure_ascii=False)}</pre>
        </div>
        
        <div class="box">
            <h3>📊 Estrutura das coleções:</h3>
            <pre>{json.dumps(diagnostico["estrutura"], indent=2, ensure_ascii=False)}</pre>
        </div>
        
        <div class="box">
            <h3>❌ Erro:</h3>
            <pre class="error">{diagnostico["erro"] or "Nenhum erro"}</pre>
        </div>
        
        <div class="box">
            <h3>🔗 Links úteis:</h3>
            <ul>
                <li><a href="/api/colecoes" target="_blank">/api/colecoes</a> - Lista coleções</li>
                <li><a href="/api/producao" target="_blank">/api/producao</a> - Detalhes da PRODUCAO_07_2025</li>
            </ul>
        </div>
    </body>
    </html>
    """)

@app.get("/api/colecoes")
async def listar_colecoes():
    return {"colecoes": diagnostico["colecoes"]}

@app.get("/api/producao")
async def detalhes_producao():
    return diagnostico["estrutura"].get("PRODUCAO_07_2025_detalhes", [])
