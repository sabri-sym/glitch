from pathlib import Path
from faster_whisper import WhisperModel

MODEL_SIZE = "small"
_model = None


def get_model():
    """Charge le modèle Whisper uniquement à la première demande de transcription."""
    global _model
    if _model is None:
        print(f"Chargement du modèle Whisper '{MODEL_SIZE}'...")
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        print("Modèle Whisper prêt.")
    return _model


def transcrire_audio(chemin_audio: str) -> str:
    """Transcrit un fichier audio en texte sans couper les fin de phrases."""
    if not Path(chemin_audio).exists():
        return ""

    try:
        model = get_model()
        segments, info = model.transcribe(
            chemin_audio,
            language="fr",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.3,                 # Sensibilité VAD ajustée pour capturer les voix douces
                min_speech_duration_ms=250,    # Prise en compte des mots très courts
                min_silence_duration_ms=1200,  # Marge avant de couper l'enregistrement
                speech_pad_ms=600,             # Sécurité avant/après la parole
            ),
            no_speech_threshold=0.4,
        )
        texte = " ".join([segment.text for segment in segments]).strip()
        return texte
    except Exception as e:
        print(f"Erreur de transcription STT : {e}")
        return ""