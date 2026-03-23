"""
KIRA — Analista Operacional Sênior v11.0
Deploy na Vercel - Firebase + Groq
Seguro - Credenciais via Environment Variables
"""

import os
import json
import tempfile
import logging
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

# ============================================================
# CONFIGURAÇÕES - APENAS VARIÁVEIS DE AMBIENTE
# ============================================================
GROQ_KEY = os.getenv("GROQ_KEY", "")
FIREBASE_CRED_JSON = os.getenv("FIREBASE_CRED_JSON", "")

# Firebase - inicialização segura
db = None
firebase_conectado = False

if FIREBASE_AVAILABLE and FIREBASE_CRED_JSON:
    try:
        cred_dict = json.loads(FIREBASE_CRED_JSON)
        cred = credentials.Certificate(cred_dict)
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_conectado = True
            print("✅ Firebase conectado via env vars")
    except Exception as e:
        print(f"❌ Erro Firebase: {e}")
else:
    print("⚠️ Firebase não configurado")

# Coleções TPL
COLECOES_TPL = [
    "tpl", "TPL_01_2025", "TPL_02_2025", "TPL_03_2025", "TPL_04_2025",
    "TPL_05_2025", "TPL_06_2025", "TPL_07_2025", "TPL_08_2025",
    "TPL_01_2026", "TPL_02_2026", "TPL_03_2026"
]

COLECOES_SUPORTE = ["acmSafra", "Metas", "producao", "snapshots", "snapshots_bulk"]
COLECOES = COLECOES_TPL + COLECOES_SUPORTE

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kira")

# ============================================================
# MODELOS DE DADOS
# ============================================================
@dataclass
class Colhedora:
    id: str
    tipo: str = ""
    modelo: str = ""
    grupo: str = ""
    horas_corte: float = 0.0
    horas_rtk: float = 0.0
    area_trabalhada: float = 0.0
    produtividade_ha_h: float = 0.0

@dataclass
class Caminhao:
    id: str
    tipo: str = ""
    viagens: int = 0
    horas_motor: float = 0.0

@dataclass
class Transbordo:
    id: str
    horas_motor: float = 0.0
    horas_operacionais: float = 0.0

# ============================================================
# MEMÓRIA DO SISTEMA
# ============================================================
class KiraMemory:
    def __init__(self):
        self.dados: List[Dict] = []
        self.colhedoras: Dict[str, Colhedora] = {}
        self.caminhoes: Dict[str, Caminhao] = {}
        self.transbordos: Dict[str, Transbordo] = {}
        self.tabelas_info: Dict[str, Dict] = {}
        self.estatisticas = {
            "firebase_conectado": firebase_conectado,
            "total_registros": 0,
            "colecoes_carregadas": [],
            "colhedoras_proprias": 0,
            "colhedoras_fretistas": 0,
            "total_area_ha": 0,
            "total_horas_corte": 0,
            "total_horas_rtk": 0,
            "adesao_rtk": 0,
            "caminhoes_proprios": 0,
            "caminhoes_terceiros": 0,
            "transbordos": 0,
            "ultima_sincronizacao": ""
        }
        self.insights: List[str] = []
        self.fatos: List[Dict] = []
        self._carregar_fatos()
    
    def _carregar_fatos(self):
        try:
            arquivo = Path("/tmp/kira_facts.json")
            if arquivo.exists():
                self.fatos = json.loads(arquivo.read_text())
        except:
            self.fatos = []
    
    def salvar_fatos(self):
        try:
            arquivo = Path("/tmp/kira_facts.json")
            arquivo.write_text(json.dumps(self.fatos[-50:], ensure_ascii=False, indent=2))
        except:
            pass
    
    def aprender(self, fato: str):
        self.fatos.append({"fato": fato, "timestamp": datetime.now().isoformat()})
        self.salvar_fatos()
        log.info(f"📚 Aprendido: {fato[:50]}")
    
    def obter_contexto(self, pergunta: str) -> str:
        if self.estatisticas["total_registros"] == 0:
            return "Aguardando dados do Firebase."
        
        pergunta_lower = pergunta.lower()
        partes = []
        
        if "colhedora" in pergunta_lower or "colhedoras" in pergunta_lower:
            partes.append(f"COLHEDORAS: {self.estatisticas['colhedoras_proprias']} próprias, {self.estatisticas['colhedoras_fretistas']} fretistas")
            partes.append(f"ÁREA TOTAL: {self.estatisticas['total_area_ha']:,.0f} hectares")
            prod = self.estatisticas['total_area_ha'] / max(self.estatisticas['total_horas_corte'], 1)
            partes.append(f"PRODUTIVIDADE: {prod:.1f} ha/h")
        
        if "rtk" in pergunta_lower or "piloto" in pergunta_lower:
            partes.append(f"RTK: {self.estatisticas['adesao_rtk']:.1f}% de adesão")
            if self.estatisticas['adesao_rtk'] < 80:
                partes.append("⚠️ META: 80% de adesão ao piloto automático")
        
        if "caminhão" in pergunta_lower or "caminhões" in pergunta_lower:
            partes.append(f"CAMINHÕES: {self.estatisticas['caminhoes_proprios']} próprios, {self.estatisticas['caminhoes_terceiros']} terceiros")
        
        if "transbordo" in pergunta_lower:
            partes.append(f"TRANSBORDOS: {self.estatisticas['transbordos']} equipamentos")
        
        if "tabela" in pergunta_lower or "coleção" in pergunta_lower:
            cols = self.estatisticas['colecoes_carregadas']
            partes.append(f"TABELAS CARREGADAS: {', '.join(cols[:8])}")
            if len(cols) > 8:
                partes.append(f"... e mais {len(cols) - 8} tabelas")
        
        return "\n".join(partes) if partes else "Dados carregados. Aguardando consulta."

# Instância global
kira = KiraMemory()

# ============================================================
# PROCESSAMENTO DE DADOS TPL
# ============================================================
def processar_dados_tpl(dados: List[Dict]):
    """Processa dados TPL do Firebase"""
    
    kira.colhedoras = {}
    kira.caminhoes = {}
    kira.transbordos = {}
    
    total_area = 0
    total_horas_corte = 0
    total_horas_rtk = 0
    proprias = set()
    fretistas = set()
    caminhoes_proprios = set()
    caminhoes_terceiros = set()
    transbordos_set = set()
    
    for registro in dados:
        try:
            # Código do equipamento
            cod_equip = registro.get("COD. EQUIPAMENTO") or registro.get("COD_EQUIPAMENTO") or registro.get("equipamento")
            if not cod_equip:
                continue
            
            cod_str = str(cod_equip).strip()
            
            # Função para extrair valores numéricos
            def get_float(campo):
                val = registro.get(campo) or registro.get(campo.replace(" ", "_"))
                if val:
                    try:
                        return float(str(val).replace(",", "."))
                    except:
                        pass
                return 0.0
            
            horas_corte = get_float("HRS CORTE BASE AUT LIGADO")
            horas_rtk = get_float("HRS RTK_LIGADO")
            area = get_float("AREA TRABALHADA ANALITICA")
            horas_motor = get_float("HRS MOTOR LIGADO")
            
            # ========== COLHEDORAS ==========
            if cod_str.startswith("80") or cod_str.startswith("93"):
                tipo = "PRÓPRIA" if cod_str.startswith("80") else "FRETISTA"
                
                if cod_str not in kira.colhedoras:
                    kira.colhedoras[cod_str] = Colhedora(
                        id=cod_str,
                        tipo=tipo,
                        modelo=registro.get("DESC.EQUIPAMENTO", ""),
                        grupo=registro.get("GRUPO EQUIPAMENTO", "")
                    )
                
                colh = kira.colhedoras[cod_str]
                colh.horas_corte += horas_corte
                colh.horas_rtk += horas_rtk
                colh.area_trabalhada += area
                
                if colh.horas_corte > 0:
                    colh.produtividade_ha_h = colh.area_trabalhada / colh.horas_corte
                
                if tipo == "PRÓPRIA":
                    proprias.add(cod_str)
                else:
                    fretistas.add(cod_str)
                
                total_area += area
                total_horas_corte += horas_corte
                total_horas_rtk += horas_rtk
            
            # ========== CAMINHÕES ==========
            elif cod_str.startswith("31") or cod_str.startswith("91"):
                tipo = "PRÓPRIO" if cod_str.startswith("31") else "TERCEIRO"
                
                if cod_str not in kira.caminhoes:
                    kira.caminhoes[cod_str] = Caminhao(id=cod_str, tipo=tipo)
                
                cam = kira.caminhoes[cod_str]
                cam.viagens += 1 if horas_motor > 0 else 0
                cam.horas_motor += horas_motor
                
                if tipo == "PRÓPRIO":
                    caminhoes_proprios.add(cod_str)
                else:
                    caminhoes_terceiros.add(cod_str)
            
            # ========== TRANSBORDOS ==========
            elif cod_str.startswith("92"):
                if cod_str not in kira.transbordos:
                    kira.transbordos[cod_str] = Transbordo(id=cod_str)
                
                trans = kira.transbordos[cod_str]
                trans.horas_motor += horas_motor
                trans.horas_operacionais += get_float("HRS OPERACIONAIS")
                transbordos_set.add(cod_str)
                    
        except Exception as e:
            continue
    
    # Atualiza estatísticas
    kira.estatisticas["colhedoras_proprias"] = len(proprias)
    kira.estatisticas["colhedoras_fretistas"] = len(fretistas)
    kira.estatisticas["total_area_ha"] = total_area
    kira.estatisticas["total_horas_corte"] = total_horas_corte
    kira.estatisticas["total_horas_rtk"] = total_horas_rtk
    kira.estatisticas["adesao_rtk"] = (total_horas_rtk / total_horas_corte * 100) if total_horas_corte > 0 else 0
    kira.estatisticas["caminhoes_proprios"] = len(caminhoes_proprios)
    kira.estatisticas["caminhoes_terceiros"] = len(caminhoes_terceiros)
    kira.estatisticas["transbordos"] = len(transbordos_set)

# ============================================================
# CARREGAMENTO DO FIREBASE
# ============================================================
async def carregar_dados_firebase():
    """Carrega todos os dados do Firebase"""
    
    if not db:
        kira.estatisticas["firebase_conectado"] = False
        kira.insights = ["❌ Firebase não conectado - verifique FIREBASE_CRED_JSON"]
        return False
    
    todos_dados = []
    colecoes_com_dados = []
    
    for colecao in COLECOES:
        try:
            docs = db.collection(colecao).limit(3000).get()
            dados_colecao = []
            for doc in docs:
                dados = doc.to_dict()
                if dados:
                    dados["_colecao"] = colecao
                    dados_colecao.append(dados)
                    todos_dados.append(dados)
            
            if dados_colecao:
                colecoes_com_dados.append(colecao)
                kira.tabelas_info[colecao] = {"documentos": len(dados_colecao)}
                log.info(f"✅ {colecao}: {len(dados_colecao)} documentos")
                
        except Exception as e:
            log.error(f"❌ Erro em {colecao}: {e}")
    
    if todos_dados:
        kira.dados = todos_dados
        kira.estatisticas["total_registros"] = len(todos_dados)
        kira.estatisticas["colecoes_carregadas"] = colecoes_com_dados
        kira.estatisticas["ultima_sincronizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        processar_dados_tpl(todos_dados)
        
        # Gera insights
        kira.insights = [
            f"✅ Firebase: {kira.estatisticas['total_registros']} registros processados",
            f"🚜 {kira.estatisticas['colhedoras_proprias']} colhedoras próprias, {kira.estatisticas['colhedoras_fretistas']} fretistas",
            f"📊 Área trabalhada: {kira.estatisticas['total_area_ha']:,.0f} hectares",
            f"🛰️ RTK: {kira.estatisticas['adesao_rtk']:.1f}% de adesão",
            f"🚛 {kira.estatisticas['caminhoes_proprios']} caminhões próprios, {kira.estatisticas['caminhoes_terceiros']} terceiros",
            f"📁 {len(colecoes_com_dados)} tabelas carregadas"
        ]
        
        log.info("=" * 50)
        log.info("✅ SINCRONIZAÇÃO CONCLUÍDA!")
        log.info(f"   Registros: {kira.estatisticas['total_registros']}")
        log.info(f"   Área: {kira.estatisticas['total_area_ha']:,.0f} ha")
        log.info(f"   RTK: {kira.estatisticas['adesao_rtk']:.1f}%")
        log.info("=" * 50)
        
        return True
    
    kira.insights = ["⚠️ Nenhum dado encontrado no Firebase"]
    return False

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(title="KIRA - Analista TPL", version="11.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await carregar_dados_firebase()

# ============================================================
# ENDPOINTS DA API
# ============================================================
@app.get("/api/status")
async def status():
    """Status do sistema e dados carregados"""
    return {
        "status": "online",
        "versao": "11.0",
        "firebase_conectado": kira.estatisticas["firebase_conectado"],
        "total_registros": kira.estatisticas["total_registros"],
        "colecoes_carregadas": kira.estatisticas["colecoes_carregadas"],
        "colhedoras_proprias": kira.estatisticas["colhedoras_proprias"],
        "colhedoras_fretistas": kira.estatisticas["colhedoras_fretistas"],
        "area_total_ha": kira.estatisticas["total_area_ha"],
        "total_horas_corte": kira.estatisticas["total_horas_corte"],
        "adesao_rtk": kira.estatisticas["adesao_rtk"],
        "caminhoes_proprios": kira.estatisticas["caminhoes_proprios"],
        "caminhoes_terceiros": kira.estatisticas["caminhoes_terceiros"],
        "transbordos": kira.estatisticas["transbordos"],
        "ultima_sincronizacao": kira.estatisticas["ultima_sincronizacao"],
        "insights": kira.insights
    }

@app.get("/api/tabelas")
async def listar_tabelas():
    """Lista todas as tabelas carregadas"""
    return {
        "total": len(kira.tabelas_info),
        "tabelas": [
            {"nome": nome, "documentos": info["documentos"]}
            for nome, info in kira.tabelas_info.items()
        ]
    }

@app.get("/api/colhedoras")
async def listar_colhedoras():
    """Lista todas as colhedoras com métricas"""
    return {
        "total": len(kira.colhedoras),
        "colhedoras": [
            {
                "id": c.id,
                "tipo": c.tipo,
                "modelo": c.modelo,
                "grupo": c.grupo,
                "area_ha": c.area_trabalhada,
                "horas_corte": c.horas_corte,
                "produtividade_ha_h": c.produtividade_ha_h,
                "horas_rtk": c.horas_rtk,
                "adesao_rtk": (c.horas_rtk / c.horas_corte * 100) if c.horas_corte > 0 else 0
            }
            for c in sorted(kira.colhedoras.values(), key=lambda x: x.area_trabalhada, reverse=True)[:100]
        ]
    }

@app.get("/api/caminhoes")
async def listar_caminhoes():
    """Lista todos os caminhões"""
    return {
        "total": len(kira.caminhoes),
        "caminhoes": [
            {
                "id": c.id,
                "tipo": c.tipo,
                "viagens": c.viagens,
                "horas_motor": c.horas_motor
            }
            for c in sorted(kira.caminhoes.values(), key=lambda x: x.viagens, reverse=True)[:100]
        ]
    }

@app.post("/api/transcribe")
async def transcrever_audio(audio: UploadFile = File(...)):
    """Transcreve áudio usando Groq Whisper"""
    
    if not GROQ_KEY:
        raise HTTPException(500, "GROQ_KEY não configurada")
    
    conteudo = await audio.read()
    
    if len(conteudo) < 1000:
        raise HTTPException(400, "Áudio muito curto")
    
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(conteudo)
        tmp_path = tmp.name
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(tmp_path, "rb") as audio_file:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"},
                    files={"file": ("audio.webm", audio_file, "audio/webm")},
                    data={"model": "whisper-large-v3-turbo", "language": "pt"}
                )
        
        if response.status_code != 200:
            raise HTTPException(502, "Falha na transcrição")
        
        texto = response.json().get("text", "").strip()
        return {"text": texto}
        
    finally:
        Path(tmp_path).unlink(missing_ok=True)

@app.post("/api/chat")
async def chat(text: str = Form(...), session_id: str = Form(default="default")):
    """Chat com IA usando Groq Llama"""
    
    if not GROQ_KEY:
        raise HTTPException(500, "GROQ_KEY não configurada")
    
    # Aprendizado ativo
    if any(p in text.lower() for p in ["aprenda", "grave", "memorize", "ensine"]):
        kira.aprender(text)
        return {"answer": "Memorizado, Senhor.", "session_id": session_id}
    
    contexto = kira.obter_contexto(text)
    
    system_prompt = f"""Você é KIRA, Analista Operacional Sênior da Usina Pitangueiras.

DADOS CARREGADOS DO FIREBASE:
{contexto}

REGRAS DE NEGÓCIO:
- Colhedoras: prefixo 80 = PRÓPRIA, 93 = FRETISTA
- Caminhões: prefixo 31 = PRÓPRIO, 91 = TERCEIRO
- Transbordos: prefixo 92
- RTK é piloto automático - meta de adesão: 80%
- Frentes válidas: FRENTE 08, 10, 11, 13, 14, 15, 30, 33, 34, 36, 120

INSTRUÇÕES DE RESPOSTA:
- Seja formal, séria e objetiva (estilo secretária executiva)
- Trate o usuário como "Senhor"
- Respostas curtas e diretas (máximo 15 palavras)
- NÃO use markdown, asteriscos ou formatação especial
- Use {{CARD:TÍTULO|VALOR|UNIDADE}} para métricas importantes

RESPOSTA:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        
        if response.status_code != 200:
            raise HTTPException(502, "Falha no chat")
        
        resposta = response.json()["choices"][0]["message"]["content"].strip()
        return {"answer": resposta, "session_id": session_id}
        
    except Exception as e:
        raise HTTPException(500, f"Erro: {str(e)}")

@app.post("/api/sync")
async def forcar_sincronizacao():
    """Força sincronização manual com Firebase"""
    await carregar_dados_firebase()
    return {
        "status": "sincronizado",
        "registros": kira.estatisticas["total_registros"],
        "colecoes": kira.estatisticas["colecoes_carregadas"]
    }

@app.get("/")
async def root():
    """Interface principal"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
        <title>KIRA - Analista Operacional Sênior</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                background: linear-gradient(135deg, #0a0a0f 0%, #1a1a2e 100%);
                color: #e2e8f0; 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace; 
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 40px; }
            .logo { 
                font-size: 4rem; 
                font-weight: 800;
                background: linear-gradient(135deg, #ec4899, #f472b6, #a855f7);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                letter-spacing: 4px;
            }
            .subtitle { color: #94a3b8; margin-top: 10px; letter-spacing: 2px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 20px; }
            .card { 
                background: rgba(26, 26, 46, 0.9);
                backdrop-filter: blur(10px);
                border-radius: 16px; 
                padding: 24px; 
                border-left: 4px solid #ec4899;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                transition: transform 0.2s;
            }
            .card:hover { transform: translateY(-2px); }
            .card h3 { color: #ec4899; margin-bottom: 16px; font-size: 1.1rem; letter-spacing: 1px; }
            .metric { 
                display: inline-block; 
                background: rgba(10, 10, 15, 0.8);
                padding: 8px 16px; 
                border-radius: 8px; 
                margin: 4px;
                font-size: 0.9rem;
            }
            .metric-value { 
                font-size: 1.3rem; 
                font-weight: bold; 
                color: #ec4899;
                display: block;
            }
            button {
                background: linear-gradient(135deg, #ec4899, #f472b6);
                border: none;
                padding: 12px 28px;
                border-radius: 40px;
                color: white;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                margin: 5px;
                transition: all 0.3s;
                font-family: monospace;
            }
            button:hover { transform: scale(1.05); box-shadow: 0 0 20px rgba(236,72,153,0.5); }
            .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; animation: pulse 2s infinite; }
            .online { background: #10b981; box-shadow: 0 0 8px #10b981; }
            .offline { background: #ef4444; }
            .transcript-area { 
                background: rgba(10, 10, 15, 0.8);
                padding: 16px; 
                border-radius: 12px; 
                margin: 15px 0; 
                min-height: 80px;
                font-size: 0.9rem;
                border: 1px solid rgba(236,72,153,0.3);
            }
            .insights-list { list-style: none; padding-left: 0; }
            .insights-list li { padding: 8px 0; border-bottom: 1px solid rgba(236,72,153,0.2); }
            .insights-list li:before { content: "💡 "; color: #ec4899; }
            a { color: #ec4899; text-decoration: none; }
            a:hover { text-decoration: underline; }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            @media (max-width: 768px) {
                .logo { font-size: 2.5rem; }
                .grid { grid-template-columns: 1fr; }
                button { padding: 10px 20px; font-size: 14px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">🤖 KIRA</div>
                <div class="subtitle">ANALISTA OPERACIONAL SÊNIOR | USINA PITANGUEIRAS</div>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>📡 STATUS DO SISTEMA</h3>
                    <div id="status-content">Carregando...</div>
                </div>
                
                <div class="card">
                    <h3>💡 INSIGHTS ESTRATÉGICOS</h3>
                    <ul class="insights-list" id="insights-list"></ul>
                </div>
            </div>
            
            <div class="card">
                <h3>🎤 COMANDOS DE VOZ</h3>
                <button onclick="startRecording()">🎙️ FALAR AGORA</button>
                <button onclick="toggleHandsFree()">✋ MÃOS LIVRES</button>
                <div class="transcript-area" id="transcript">👉 Clique no botão e fale com a KIRA</div>
                <div class="transcript-area" id="response" style="color: #ec4899; min-height: 60px;"></div>
            </div>
            
            <div class="card">
                <h3>📊 ACESSO RÁPIDO AOS DADOS</h3>
                <p>
                    <a href="/api/status" target="_blank">📡 Status Completo</a> | 
                    <a href="/api/tabelas" target="_blank">📁 Tabelas Carregadas</a> |
                    <a href="/api/colhedoras" target="_blank">🚜 Colhedoras</a> |
                    <a href="/api/caminhoes" target="_blank">🚛 Caminhões</a> |
                    <a href="/api/docs" target="_blank">📖 API Docs</a>
                </p>
            </div>
        </div>
        
        <script>
            let mediaRecorder = null;
            let audioChunks = [];
            let isRecording = false;
            let handsFreeMode = false;
            
            async function loadStatus() {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();
                    
                    const statusHtml = `
                        <p><span class="status-dot ${data.firebase_conectado ? 'online' : 'offline'}"></span>
                        <strong>Firebase:</strong> ${data.firebase_conectado ? '✅ CONECTADO' : '❌ DESCONECTADO'}</p>
                        <div class="metric"><span class="metric-value">${data.total_registros.toLocaleString()}</span> registros</div>
                        <div class="metric"><span class="metric-value">${data.colecoes_carregadas.length}</span> tabelas</div>
                        <div class="metric"><span class="metric-value">${data.colhedoras_proprias + data.colhedoras_fretistas}</span> colhedoras</div>
                        <div class="metric"><span class="metric-value">${data.area_total_ha.toLocaleString()}</span> hectares</div>
                        <div class="metric"><span class="metric-value">${data.adesao_rtk.toFixed(1)}%</span> RTK</div>
                        <div class="metric"><span class="metric-value">${data.caminhoes_proprios + data.caminhoes_terceiros}</span> caminhões</div>
                        <p style="margin-top: 12px; font-size: 0.8rem; color: #94a3b8;">
                        ⏱️ Última sincronização: ${data.ultima_sincronizacao || 'Nunca'}
                        </p>
                    `;
                    document.getElementById('status-content').innerHTML = statusHtml;
                    
                    const insightsList = document.getElementById('insights-list');
                    insightsList.innerHTML = data.insights.map(i => `<li>${i}</li>`).join('');
                    
                } catch (error) {
                    document.getElementById('status-content').innerHTML = '<p>❌ Erro ao carregar status</p>';
                }
            }
            
            async function startRecording() {
                if (isRecording) {
                    if (mediaRecorder && mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                    }
                    isRecording = false;
                    document.querySelector('button[onclick="startRecording()"]').innerHTML = '🎙️ FALAR AGORA';
                    document.getElementById('transcript').innerHTML = '🎙️ Processando áudio...';
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
                        
                        document.getElementById('transcript').innerHTML = '🎙️ Transcrevendo...';
                        
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
                            document.getElementById('transcript').innerHTML = '❌ Erro ao processar áudio';
                        }
                        
                        if (handsFreeMode) {
                            setTimeout(startRecording, 1000);
                        }
                    };
                    
                    mediaRecorder.start();
                    isRecording = true;
                    document.querySelector('button[onclick="startRecording()"]').innerHTML = '⏹️ PARAR';
                    document.getElementById('transcript').innerHTML = '🎙️ Ouvindo... Fale agora';
                    
                } catch (error) {
                    alert('❌ Permissão do microfone negada. Verifique as configurações do navegador.');
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
                    btn.style.background = 'linear-gradient(135deg, #ec4899, #f472b6)';
                    if (isRecording) {
                        mediaRecorder.stop();
                        isRecording = false;
                    }
                }
            }
            
            loadStatus();
            setInterval(loadStatus, 30000);
        </script>
    </body>
    </html>
    """)