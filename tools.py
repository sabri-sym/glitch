import base64
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

# Workspace dédié aux créations / exécutions de GLITCH
WORKSPACE = Path("workspace")
WORKSPACE.mkdir(exist_ok=True)

# Détection Piper TTS
PIPER_MODEL_PATH = "fr_FR-siwis-medium.onnx"
voice = None
if Path(PIPER_MODEL_PATH).exists():
    try:
        from piper import PiperVoice
        voice = PiperVoice.load(PIPER_MODEL_PATH)
    except Exception as e:
        print(f"[WARN] Erreur chargement modèle Piper : {e}")


def lister_fichiers(path: str = ".") -> dict:
    """Liste le contenu d'un répertoire dans le workspace."""
    try:
        cible = (WORKSPACE / path).resolve()
        if not str(cible).startswith(str(WORKSPACE.resolve())):
            return {"erreur": "Accès refusé : hors du périmètre workspace."}
        if not cible.exists():
            return {"erreur": f"Le chemin '{path}' n'existe pas."}

        elements = []
        for elem in cible.iterdir():
            elements.append(
                {
                    "nom": elem.name,
                    "type": "dossier" if elem.is_dir() else "fichier",
                    "taille_octets": elem.stat().st_size if elem.is_file() else 0,
                }
            )
        return {"chemin": str(cible), "elements": elements}
    except Exception as e:
        return {"erreur": str(e)}


def lire_fichier(chemin: str) -> dict:
    """Lit le contenu d'un fichier texte dans le workspace."""
    try:
        cible = (WORKSPACE / chemin).resolve()
        if not str(cible).startswith(str(WORKSPACE.resolve())):
            return {"erreur": "Accès refusé : hors du périmètre workspace."}
        if not cible.exists() or not cible.is_file():
            return {"erreur": f"Fichier '{chemin}' introuvable."}

        contenu = cible.read_text(encoding="utf-8", errors="ignore")
        return {"chemin": chemin, "contenu": contenu}
    except Exception as e:
        return {"erreur": f"Impossible de lire le fichier : {e}"}


def ecrire_fichier(chemin: str, contenu: str) -> dict:
    """Écrit ou écrase un fichier dans le workspace."""
    try:
        cible = (WORKSPACE / chemin).resolve()
        if not str(cible).startswith(str(WORKSPACE.resolve())):
            return {"erreur": "Accès refusé : hors du périmètre workspace."}

        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(contenu, encoding="utf-8")
        return {"status": "Succès", "chemin": chemin, "message": f"Fichier '{chemin}' écrit avec succès."}
    except Exception as e:
        return {"erreur": f"Échec d'écriture : {e}"}


def supprimer_element(chemin: str) -> dict:
    """Supprime un fichier ou un dossier dans le workspace."""
    try:
        cible = (WORKSPACE / chemin).resolve()
        if not str(cible).startswith(str(WORKSPACE.resolve())):
            return {"erreur": "Accès refusé : hors du périmètre workspace."}
        if not cible.exists():
            return {"erreur": f"Élément '{chemin}' introuvable."}

        if cible.is_file():
            cible.unlink()
        else:
            shutil.rmtree(cible)
        return {"status": "Succès", "supprime": chemin}
    except Exception as e:
        return {"erreur": f"Échec de suppression : {e}"}


def executer_command_shell(commande: str) -> dict:
    """Exécute une commande PowerShell au sein du workspace."""
    try:
        res = subprocess.run(
            ["powershell", "-Command", commande],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
        return {
            "commande": commande,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
            "code_retour": res.returncode,
            "statut": "OK" if res.returncode == 0 else "ERREUR"
        }
    except subprocess.TimeoutExpired:
        return {"erreur": "Timeout : la commande a dépassé le temps limite de 120 secondes."}
    except Exception as e:
        return {"erreur": f"Erreur d'exécution shell : {e}"}


def encoder_image_base64(chemin_image: str) -> str:
    """Convertit une image locale en chaîne Base64."""
    path = Path(chemin_image)
    if not path.is_absolute():
        path = WORKSPACE / chemin_image

    if not path.exists():
        return ""

    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def generer_vocal(texte: str, output_wav: str = "bibliotheque/response.wav") -> str:
    """Génère la synthèse vocale via Piper-TTS de manière ultra-robuste sous Windows."""
    texte_clean = re.sub(r"[\*\`\#\_]", "", texte).strip()
    if not texte_clean:
        return ""

    output_path = Path(output_wav)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Tentative via le binding Python de Piper
    if voice:
        try:
            with wave.open(str(output_path), "wb") as wav_file:
                voice.synthesize(texte_clean, wav_file)

            if output_path.exists() and output_path.stat().st_size > 1000:
                return str(output_path)
        except Exception as e:
            print(f"[WARN] Synthèse Python Piper échouée : {e}")

    # 2. Fallback via la CLI Piper (avec encodage UTF-8 explicite sous Windows)
    try:
        process = subprocess.run(
            ["piper", "--model", PIPER_MODEL_PATH, "--output_file", str(output_path)],
            input=texte_clean.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        if process.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            return str(output_path)
        else:
            err_msg = process.stderr.decode("utf-8", errors="ignore")
            print(f"[WARN] Synthèse CLI Piper échouée : {err_msg}")
    except Exception as e2:
        print(f"[WARN] Erreur exécution CLI Piper : {e2}")

    return ""