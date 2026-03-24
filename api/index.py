"""
KIRA - Diagnóstico Completo do Firebase
Mostra TUDO que existe
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
resultado = {
    "colecoes": [],
    "conteudo": {},
    "erro": None
}

def explorar_firebase():
    """Explora TUDO no Firebase"""
    global resultado
    
    try:
        # Passo 1: Lista todas as coleções (documentos no root)
        url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents?key={FIREBASE_API_KEY}"
        print(f"🔍 Buscando: {url}")
        
        response = httpx.get(url, timeout=30.0)
        if response.status_code != 200:
            resultado["erro"] = f"Erro {response.status_code}: {response.text[:500]}"
            return
        
        dados = response.json()
        documentos = dados.get("documents", [])
        
        print(f"📁 Documentos encontrados no root: {len(documentos)}")
        
        # Extrai nomes das coleções (primeiro nível)
        colecoes = set()
        for doc in documentos:
            nome = doc.get("name", "")
            partes = nome.split("/")
            # Formato: projects/.../documents/NOME_COLECAO/...
            if len(partes) >= 6:
                colecao = partes[5]
                colecoes.add(colecao)
                print(f"   Coleção encontrada: {colecao}")
        
        resultado["colecoes"] = list(colecoes)
        
        # Passo 2: Para cada coleção, lista seus documentos
        for colecao in colecoes:
            print(f"\n📖 Lendo coleção: {colecao}")
            colecao_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/{colecao}?key={FIREBASE_API_KEY}"
            resp = httpx.get(colecao_url, timeout=30.0)
            
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("documents", [])
                
                resultado["conteudo"][colecao] = {
                    "total_documentos": len(docs),
                    "documentos": []
                }
                
                for doc in docs[:5]:  # Limita a 5 docs por coleção
                    doc_nome = doc.get("name", "").split("/")[-1]
                    fields = doc.get("fields", {})
                    campos = list(fields.keys())
                    
                    # Se tiver o campo "chunks" ou "cab", mostra detalhe
                    detalhe = {}
                    if "cab" in fields:
                        cab = fields["cab"]
                        cab_values = cab.get("arrayValue", {}).get("values", [])
                        detalhe["cab"] = [c.get("stringValue", "") for c in cab_values[:10]]
                    
                    if "chunks" in fields:
                        chunks = fields["chunks"]
                        chunks_map = chunks.get("mapValue", {}).get("fields", {})
                        detalhe["chunks"] = list(chunks_map.keys())[:10]
                        detalhe["total_chunks"] = len(chunks_map)
                    
                    resultado["conteudo"][colecao]["documentos"].append({
                        "nome": doc_nome,
                        "campos": campos[:20],
                        "detalhe": detalhe
                    })
                
                print(f"   ✅ {len(docs)} documentos encontrados")
            else:
                print(f"   ❌ Erro: {resp.status_code}")
        
        # Passo 3: Se encontrou PRODUCAO_07_2025, tenta ler direto
        if "PRODUCAO_07_2025" in colecoes:
            print(f"\n🔍 Examinando PRODUCAO_07_2025 em detalhe...")
            
            # Tenta ler o documento "chunks" se existir
            chunks_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/PRODUCAO_07_2025/chunks?key={FIREBASE_API_KEY}"
            chunks_resp = httpx.get(chunks_url, timeout=30.0)
            
            if chunks_resp.status_code == 200:
                print("   ✅ Documento 'chunks' encontrado!")
                chunks_data = chunks_resp.json()
                fields = chunks_data.get("fields", {})
                
                resultado["conteudo"]["PRODUCAO_07_2025_chunks"] = {
                    "campos": list(fields.keys()),
                    "cab": [],
                    "chunks": []
                }
                
                if "cab" in fields:
                    cab = fields["cab"]
                    cab_values = cab.get("arrayValue", {}).get("values", [])
                    resultado["conteudo"]["PRODUCAO_07_2025_chunks"]["cab"] = [c.get("stringValue", "") for c in cab_values]
                
                if "chunks" in fields:
                    chunks_map = fields["chunks"].get("mapValue", {}).get("fields", {})
                    resultado["conteudo"]["PRODUCAO_07_2025_chunks"]["chunks"] = list(chunks_map.keys())
                    resultado["conteudo"]["PRODUCAO_07_2025_chunks"]["total_chunks"] = len(chunks_map)
            else:
                print(f"   ⚠️ Documento 'chunks' não encontrado (status {chunks_resp.status_code})")
                
                # Tenta listar os documentos dentro de PRODUCAO_07_2025
                docs_url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/PRODUCAO_07_2025?key={FIREBASE_API_KEY}"
                docs_resp = httpx.get(docs_url, timeout=30.0)
                
                if docs_resp.status_code == 200:
                    data = docs_resp.json()
                    docs = data.get("documents", [])
                    resultado["conteudo"]["PRODUCAO_07_2025_documentos"] = [doc.get("name", "").split("/")[-1] for doc in docs]
                    print(f"   📄 Documentos dentro de PRODUCAO_07_2025: {len(docs)}")
        
    except Exception as e:
        resultado["erro"] = str(e)
        print(f"❌ Erro: {e}")

# Executa diagnóstico
explorar_firebase()

@app.get("/")
async def index():
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>KIRA - Diagnóstico Firebase</title>
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
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            details {{
                margin: 10px 0;
                cursor: pointer;
            }}
            summary {{
                font-weight: bold;
                color: #ec4899;
            }}
        </style>
    </head>
    <body>
        <h1>🔍 KIRA - Diagnóstico do Firebase</h1>
        
        <div class="box">
            <h3>📁 Coleções encontradas:</h3>
            <ul>
                {"".join(f'<li>{c}</li>' for c in resultado["colecoes"]) if resultado["colecoes"] else "<li>Nenhuma coleção encontrada</li>"}
            </ul>
        </div>
        
        <div class="box">
            <h3>📊 Detalhes por coleção:</h3>
            {''.join(f'''
            <details>
                <summary>📁 {colecao} ({data.get('total_documentos', 0)} documentos)</summary>
                <pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>
            </details>
            ''' for colecao, data in resultado["conteudo"].items())}
        </div>
        
        <div class="box">
            <h3>❌ Erro:</h3>
            <pre class="error">{resultado["erro"] or "Nenhum erro"}</pre>
        </div>
        
        <div class="box">
            <h3>📋 Resumo:</h3>
            <p>Total de coleções: {len(resultado["colecoes"])}</p>
            <p>API Key: {FIREBASE_API_KEY[:20]}...</p>
            <p>Project ID: {PROJECT_ID}</p>
        </div>
    </body>
    </html>
    """)
