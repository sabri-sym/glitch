import json
import os
import re
import subprocess
import time
import unicodedata
import uuid
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import requests

# ── Imports modules locaux SYM / GLITCH ──
try:
    from stt import transcrire_audio
    STT_AVAILABLE = True
except Exception as e:
    print(f"[WARN] Module STT indisponible : {e}")
    STT_AVAILABLE = False

try:
    from tools import (
        generer_vocal,
        lister_fichiers,
        lire_fichier,
        ecrire_fichier,
        supprimer_element,
        executer_command_shell
    )
    TTS_AVAILABLE = True
except Exception as e:
    print(f"[WARN] Module Tools indisponible : {e}")
    TTS_AVAILABLE = False

# ── FastAPI init ──
app = FastAPI(title="GLITCH OS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BIBLIO_DIR = os.path.join(os.path.dirname(__file__), "bibliotheque")
os.makedirs(BIBLIO_DIR, exist_ok=True)
app.mount("/bibliotheque", StaticFiles(directory=BIBLIO_DIR), name="bibliotheque")

# ── Ollama config ──
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
_ollama_model = None

PREFERRED_MODELS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder",
    "qwen2.5:7b",
    "deepseek-r1:7b",
    "deepseek-r1",
    "llama3.1:8b",
    "llama3.1"
]


def detect_ollama_model() -> str:
    """Détecte automatiquement le meilleur modèle disponible chez Ollama."""
    global _ollama_model
    if _ollama_model:
        return _ollama_model
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=5)
        r.raise_for_status()
        installed_models = [m["name"] for m in r.json().get("models", [])]
        
        for pref in PREFERRED_MODELS:
            for inst in installed_models:
                if pref in inst:
                    _ollama_model = inst
                    print(f"[INFO] Modèle de prédilection Ollama sélectionné : {_ollama_model}")
                    return _ollama_model

        if installed_models:
            _ollama_model = installed_models[0]
            print(f"[INFO] Modèle Ollama par défaut sélectionné : {_ollama_model}")
            return _ollama_model
    except Exception as e:
        print(f"[WARN] Détection modèle Ollama échouée : {e}")

    _ollama_model = "qwen2.5-coder:7b"
    print(f"[INFO] Fallback modèle Ollama : {_ollama_model}")
    return _ollama_model


# ── Mémoire conversationnelle & Prompt ──
conversation_history = []

SYSTEM_PROMPT = (
    "Tu es GLITCH, l'agent informatique local et totalement autonome de SYM OS.\n"
    "Ton but principal est d'exécuter concrètement les demandes : créer/modifier des fichiers, "
    "coder, lancer des commandes PowerShell, tester et corriger les erreurs jusqu'à résolution complète.\n\n"
    "RÈGLES D'ACTION ET D'OUTILS :\n"
    "1. Si l'utilisateur te demande une action technique (créer un fichier, exécuter du code, lister un dossier), "
    "UTILISE DIRECTEMENT LES OUTILS MIS À TA DISPOSITION.\n"
    "2. Sois concis, direct et réponds toujours en français.\n"
    "3. Si une commande renvoie une erreur, analyse le problème, modifie le fichier ou la commande, et retente l'exécution."
)

GLITCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lister_fichiers",
            "description": "Liste les fichiers et dossiers dans un répertoire du workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin relatif du dossier (ex: '.' ou 'mon_projet')"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lire_fichier",
            "description": "Lit le contenu textuel d'un fichier dans le workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chemin": {"type": "string", "description": "Chemin relatif du fichier à lire"}
                },
                "required": ["chemin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ecrire_fichier",
            "description": "Crée ou écrase un fichier dans le workspace avec le contenu donné.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chemin": {"type": "string", "description": "Chemin relatif du fichier (ex: 'app.py')"},
                    "contenu": {"type": "string", "description": "Contenu complet du fichier"}
                },
                "required": ["chemin", "contenu"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "supprimer_element",
            "description": "Supprime un fichier ou un dossier complet du workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chemin": {"type": "string", "description": "Chemin relatif du fichier ou dossier à supprimer"}
                },
                "required": ["chemin"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "executer_command_shell",
            "description": "Exécute une commande PowerShell dans le dossier workspace (ex: 'python app.py', 'pip install ...', 'dir').",
            "parameters": {
                "type": "object",
                "properties": {
                    "commande": {"type": "string", "description": "Commande PowerShell à exécuter"}
                },
                "required": ["commande"]
            }
        }
    }
]


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("’", "'").replace("”", '"').replace("“", '"')
    return text.strip()


def execute_local_tool(tool_name: str, arguments: dict) -> dict:
    try:
        if tool_name == "lister_fichiers":
            return lister_fichiers(arguments.get("path", "."))
        elif tool_name == "lire_fichier":
            return lire_fichier(arguments.get("chemin", ""))
        elif tool_name == "ecrire_fichier":
            return ecrire_fichier(arguments.get("chemin", ""), arguments.get("contenu", ""))
        elif tool_name == "supprimer_element":
            return supprimer_element(arguments.get("chemin", ""))
        elif tool_name == "executer_command_shell":
            return executer_command_shell(arguments.get("commande", ""))
        else:
            return {"erreur": f"Outil inconnu : {tool_name}"}
    except Exception as e:
        return {"erreur": f"Erreur lors de l'exécution de l'outil {tool_name} : {str(e)}"}


def run_agent_loop(messages: list, max_turns: int = 5) -> str:
    model_name = detect_ollama_model()

    for turn in range(max_turns):
        payload = {
            "model": model_name,
            "messages": messages,
            "tools": GLITCH_TOOLS,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
            },
        }

        r = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()

        response_message = data.get("message", {})
        tool_calls = response_message.get("tool_calls", [])

        messages.append(response_message)

        if not tool_calls:
            return response_message.get("content", "")

        for tool_call in tool_calls:
            func_info = tool_call.get("function", {})
            func_name = func_info.get("name")
            raw_args = func_info.get("arguments", {})

            if isinstance(raw_args, str):
                try:
                    func_args = json.loads(raw_args)
                except Exception:
                    func_args = {}
            else:
                func_args = raw_args

            print(f"[AGENT TOOL] Turn {turn+1} -> Exécution de {func_name} avec {func_args}")
            tool_result = execute_local_tool(func_name, func_args)

            messages.append({
                "role": "tool",
                "content": json.dumps(tool_result, ensure_ascii=False)
            })

    return "La limite de boucles d'exécution autonome a été atteinte."


# ── Routes FastAPI ──

@app.get("/")
async def root():
    html_path = os.path.join(os.path.dirname(__file__), "interface.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="interface.html introuvable.")
    return FileResponse(html_path)


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Fichier audio vide reçu.")

        process = subprocess.Popen(
            [
                "ffmpeg",
                "-y", "-i", "pipe:0",
                "-ar", "16000", "-ac", "1",
                "-c:a", "pcm_s16le", "-f", "wav",
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wav_data, stderr = process.communicate(input=audio_bytes)

        if process.returncode != 0:
            err = stderr.decode("utf-8", errors="ignore")
            print(f"[ERROR] FFmpeg : {err}")
            return JSONResponse(status_code=400, content={"error": "Échec conversion FFmpeg", "texte": ""})

        temp_wav = os.path.join(BIBLIO_DIR, f"temp_{uuid.uuid4().hex[:8]}.wav")
        with open(temp_wav, "wb") as f:
            f.write(wav_data)

        if STT_AVAILABLE:
            raw_text = transcrire_audio(temp_wav)
        else:
            raw_text = "[STT indisponible]"

        clean_result = clean_text(raw_text)

        try:
            os.remove(temp_wav)
        except Exception:
            pass

        return JSONResponse(
            content={"texte": clean_result},
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    except Exception as e:
        print(f"[ERROR] /api/transcribe : {e}")
        return JSONResponse(status_code=500, content={"error": str(e), "texte": ""})


@app.post("/api/chat")
async def chat(payload: dict):
    global conversation_history

    user_msg = clean_text(payload.get("message", ""))
    if not user_msg:
        return JSONResponse(content={"response": "Aucun message reçu.", "audio_url": None})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history[-8:])
    messages.append({"role": "user", "content": user_msg})

    try:
        bot_response = run_agent_loop(messages, max_turns=6)
        bot_response_clean = clean_text(bot_response)
    except Exception as e:
        print(f"[ERROR] Agent Exec : {e}")
        bot_response_clean = f"[Erreur GLITCH Agent] {str(e)}"

    conversation_history.append({"role": "user", "content": user_msg})
    conversation_history.append({"role": "assistant", "content": bot_response_clean})
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]

    audio_url = None
    unique_id = uuid.uuid4().hex[:8]
    audio_filename = f"response_{unique_id}.wav"
    audio_path = os.path.join(BIBLIO_DIR, audio_filename)

    try:
        if TTS_AVAILABLE and bot_response_clean and not bot_response_clean.startswith("[Erreur"):
            result = generer_vocal(bot_response_clean, audio_path)
            if result and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                audio_url = f"/bibliotheque/{audio_filename}"
            else:
                _generate_silence(audio_path)
                if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                    audio_url = f"/bibliotheque/{audio_filename}"
        else:
            _generate_silence(audio_path)
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                audio_url = f"/bibliotheque/{audio_filename}"
    except Exception as e:
        print(f"[ERROR] TTS : {e}")

    return JSONResponse(
        content={"response": bot_response_clean, "audio_url": audio_url},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


def _generate_silence(output_path: str, duration_sec: int = 1):
    import wave
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * (22050 * duration_sec))


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_name = clean_text(file.filename)
    content = await file.read()
    
    workspace_path = os.path.join(os.path.dirname(__file__), "workspace", file_name)
    os.makedirs(os.path.dirname(workspace_path), exist_ok=True)
    with open(workspace_path, "wb") as f:
        f.write(content)

    apercu = f"Fichier '{file_name}' déposé dans le workspace ({len(content)} octets)."
    return JSONResponse(
        content={"apercu": apercu},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )


@app.delete("/api/memory")
async def clear_memory():
    global conversation_history
    conversation_history = []
    for f in os.listdir(BIBLIO_DIR):
        if f.startswith("response_") or f.startswith("temp_"):
            try:
                os.remove(os.path.join(BIBLIO_DIR, f))
            except Exception:
                pass
    return JSONResponse(content={"status": "Mémoire réinitialisée"})


if __name__ == "__main__":
    import uvicorn
    # Option no-reload activée pour éviter les crashs de multiprocessing sous Python 3.14
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)