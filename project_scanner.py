"""
GLITCH â€” Project Scanner & Diagnostic
======================================

Mission :
- DÃ©couvrir automatiquement le dossier maÃ®tre GLITCH.
- Scanner rÃ©cursivement le projet.
- Identifier les incohÃ©rences et problÃ¨mes potentiels.
- Produire un inventaire + diagnostic.
- NE MODIFIE AUCUN FICHIER.

Dossier maÃ®tre attendu :
    C:\\Users\\HAPPY\\Desktop\\glitch

Le chemin n'est jamais remplacÃ© par un nouveau projet.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_NAME = "glitch"

# RÃ©pertoires/fichiers Ã  ignorer
IGNORED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
    ".sql",
    ".xml",
}

MAX_TEXT_SIZE = 2 * 1024 * 1024  # 2 MB


# ============================================================
# DÃ‰COUVERTE DU DOSSIER MAÃŽTRE
# ============================================================

def discover_master_directory() -> Path:
    """
    DÃ©couvre automatiquement le dossier maÃ®tre GLITCH.

    PrioritÃ© :
    1. Variable d'environnement GLITCH_HOME
    2. Desktop\\glitch de l'utilisateur Windows courant
    3. Recherche de dossiers candidats connus

    Aucun dossier n'est crÃ©Ã©.
    """

    # 1. Variable explicite
    env_path = os.environ.get("GLITCH_HOME")

    if env_path:
        candidate = Path(env_path).expanduser().resolve()

        if candidate.is_dir():
            return candidate

        raise RuntimeError(
            f"GLITCH_HOME pointe vers un dossier inexistant : {candidate}"
        )

    # 2. Desktop de l'utilisateur courant
    home = Path.home()

    candidates = [
        home / "Desktop" / "glitch",
        home / "Bureau" / "glitch",
    ]

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()

    # 3. Recherche limitÃ©e dans Desktop
    desktop_candidates = [
        home / "Desktop",
        home / "Bureau",
    ]

    for desktop in desktop_candidates:
        if not desktop.is_dir():
            continue

        for child in desktop.iterdir():
            if child.is_dir() and child.name.lower() == PROJECT_NAME:
                return child.resolve()

    raise FileNotFoundError(
        "Impossible de trouver le dossier maÃ®tre GLITCH.\n"
        "Dossier recherchÃ© : Desktop\\glitch\n"
        "Aucun dossier n'a Ã©tÃ© crÃ©Ã© automatiquement."
    )


# ============================================================
# IDENTIFICATION DU PROJET
# ============================================================

def identify_project(root: Path) -> dict[str, Any]:
    """
    DÃ©termine si le dossier ressemble rÃ©ellement Ã  un projet GLITCH.
    """

    indicators = {
        "python_files": 0,
        "glitch_mentions": 0,
        "ollama_mentions": 0,
        "agent_files": 0,
        "config_files": 0,
    }

    important_files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.name in IGNORED_FILES:
            continue

        suffix = path.suffix.lower()

        if suffix == ".py":
            indicators["python_files"] += 1

        if suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
            indicators["config_files"] += 1

        lower_name = path.name.lower()

        if any(
            token in lower_name
            for token in ("agent", "orchestr", "engine", "manager")
        ):
            indicators["agent_files"] += 1

        if suffix not in TEXT_EXTENSIONS:
            continue

        try:
            if path.stat().st_size > MAX_TEXT_SIZE:
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()

            indicators["glitch_mentions"] += text.count("glitch")
            indicators["ollama_mentions"] += text.count("ollama")

        except (OSError, UnicodeError):
            continue

    score = 0

    if indicators["glitch_mentions"] > 0:
        score += 3

    if indicators["ollama_mentions"] > 0:
        score += 2

    if indicators["python_files"] > 0:
        score += 2

    if indicators["agent_files"] > 0:
        score += 2

    if indicators["config_files"] > 0:
        score += 1

    return {
        "project_name": root.name,
        "root": str(root),
        "confidence_score": score,
        "likely_glitch_project": score >= 3,
        "indicators": indicators,
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# HASH DES FICHIERS
# ============================================================

def sha256_file(path: Path) -> str | None:
    """
    Calcule le SHA-256 d'un fichier.
    """

    try:
        digest = hashlib.sha256()

        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    except (OSError, PermissionError):
        return None


# ============================================================
# ANALYSE PYTHON
# ============================================================

def analyze_python_file(path: Path) -> list[dict[str, Any]]:
    """
    Analyse statique lÃ©gÃ¨re d'un fichier Python.
    """

    problems = []

    try:
        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        tree = ast.parse(source, filename=str(path))

    except SyntaxError as exc:
        problems.append({
            "type": "python_syntax_error",
            "severity": "critical",
            "file": str(path),
            "line": exc.lineno,
            "message": exc.msg,
        })

        return problems

    except Exception as exc:
        problems.append({
            "type": "python_analysis_error",
            "severity": "warning",
            "file": str(path),
            "message": str(exc),
        })

        return problems

    # DÃ©tection des imports inutilisÃ©s trÃ¨s basique
    imports = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.asname or alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports.append(alias.asname or alias.name)

    # DÃ©tection de TODO/FIXME
    for line_number, line in enumerate(source.splitlines(), start=1):

        if "TODO" in line.upper():
            problems.append({
                "type": "todo",
                "severity": "info",
                "file": str(path),
                "line": line_number,
                "message": line.strip(),
            })

        if "FIXME" in line.upper():
            problems.append({
                "type": "fixme",
                "severity": "warning",
                "file": str(path),
                "line": line_number,
                "message": line.strip(),
            })

    # DÃ©tection de subprocess potentiellement dangereux
    if "subprocess" in source:
        problems.append({
            "type": "system_command_execution",
            "severity": "warning",
            "file": str(path),
            "message": (
                "Le fichier utilise subprocess. "
                "GLITCH devra contrÃ´ler et journaliser les commandes systÃ¨me."
            ),
        })

    # DÃ©tection d'URLs codÃ©es en dur
    urls = re.findall(r'https?://[^\s"\']+', source)

    if urls:
        problems.append({
            "type": "hardcoded_urls",
            "severity": "info",
            "file": str(path),
            "count": len(urls),
            "message": "URL(s) dÃ©tectÃ©e(s) directement dans le code.",
        })

    return problems


# ============================================================
# ANALYSE TEXTE
# ============================================================

def analyze_text_file(path: Path) -> list[dict[str, Any]]:
    problems = []

    try:
        if path.stat().st_size > MAX_TEXT_SIZE:
            return problems

        text = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except (OSError, PermissionError):
        return problems

    lines = text.splitlines()

    for line_number, line in enumerate(lines, start=1):

        upper = line.upper()

        if "TODO" in upper:
            problems.append({
                "type": "todo",
                "severity": "info",
                "file": str(path),
                "line": line_number,
                "message": line.strip(),
            })

        if "FIXME" in upper:
            problems.append({
                "type": "fixme",
                "severity": "warning",
                "file": str(path),
                "line": line_number,
                "message": line.strip(),
            })

    return problems


# ============================================================
# SCAN PRINCIPAL
# ============================================================

def scan_project(root: Path) -> dict[str, Any]:

    files = []
    directories = []

    extension_counter = Counter()
    duplicate_hashes = defaultdict(list)
    problems = []

    total_size = 0

    for current_root, dirnames, filenames in os.walk(root):

        # Ignorer certains dossiers
        dirnames[:] = [
            name
            for name in dirnames
            if name not in IGNORED_DIRS
        ]

        current_path = Path(current_root)

        for dirname in dirnames:

            directory_path = current_path / dirname

            directories.append(
                str(directory_path.relative_to(root))
            )

        for filename in filenames:

            if filename in IGNORED_FILES:
                continue

            path = current_path / filename

            try:
                stat = path.stat()

            except (OSError, PermissionError):
                problems.append({
                    "type": "unreadable_file",
                    "severity": "warning",
                    "file": str(path),
                    "message": "Impossible de lire les mÃ©tadonnÃ©es.",
                })

                continue

            relative = path.relative_to(root)

            suffix = path.suffix.lower() or "[sans_extension]"

            extension_counter[suffix] += 1
            total_size += stat.st_size

            file_info = {
                "path": str(relative),
                "absolute_path": str(path),
                "name": filename,
                "extension": suffix,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat(),
            }

            file_hash = sha256_file(path)

            if file_hash:
                file_info["sha256"] = file_hash
                duplicate_hashes[file_hash].append(str(relative))

            files.append(file_info)

            # Analyse Python
            if suffix == ".py":
                problems.extend(
                    analyze_python_file(path)
                )

            # Analyse texte
            elif suffix in TEXT_EXTENSIONS:
                problems.extend(
                    analyze_text_file(path)
                )

    # DÃ©tection des doublons
    for file_hash, paths in duplicate_hashes.items():

        if len(paths) > 1:

            problems.append({
                "type": "duplicate_files",
                "severity": "info",
                "files": paths,
                "sha256": file_hash,
                "message": (
                    f"{len(paths)} fichiers possÃ¨dent exactement "
                    "le mÃªme contenu."
                ),
            })

    return {
        "scan_timestamp": datetime.now().isoformat(),
        "root": str(root),
        "summary": {
            "directories": len(directories),
            "files": len(files),
            "total_size_bytes": total_size,
            "extensions": dict(extension_counter),
            "problems": len(problems),
            "critical": sum(
                1 for p in problems
                if p.get("severity") == "critical"
            ),
            "warnings": sum(
                1 for p in problems
                if p.get("severity") == "warning"
            ),
            "info": sum(
                1 for p in problems
                if p.get("severity") == "info"
            ),
        },
        "directories": directories,
        "files": files,
        "problems": problems,
    }


# ============================================================
# RAPPORT HUMAIN
# ============================================================

def generate_report(
    identity: dict[str, Any],
    scan: dict[str, Any],
) -> str:

    summary = scan["summary"]

    lines = []

    lines.append("=" * 70)
    lines.append("GLITCH â€” DIAGNOSTIC INITIAL DU PROJET")
    lines.append("=" * 70)

    lines.append("")
    lines.append(f"Dossier maÃ®tre : {scan['root']}")
    lines.append(f"Date : {scan['scan_timestamp']}")

    lines.append("")
    lines.append("IDENTIFICATION")
    lines.append("-" * 70)
    lines.append(
        f"Projet dÃ©tectÃ© comme GLITCH : "
        f"{identity['likely_glitch_project']}"
    )
    lines.append(
        f"Score de confiance : "
        f"{identity['confidence_score']}/10"
    )

    lines.append("")
    lines.append("INVENTAIRE")
    lines.append("-" * 70)
    lines.append(
        f"Dossiers : {summary['directories']}"
    )
    lines.append(
        f"Fichiers : {summary['files']}"
    )
    lines.append(
        f"Taille totale : {summary['total_size_bytes']:,} octets"
    )

    lines.append("")
    lines.append("PROBLÃˆMES DÃ‰TECTÃ‰S")
    lines.append("-" * 70)
    lines.append(
        f"Critiques : {summary['critical']}"
    )
    lines.append(
        f"Avertissements : {summary['warnings']}"
    )
    lines.append(
        f"Informations : {summary['info']}"
    )

    if scan["problems"]:

        lines.append("")
        lines.append("DÃ‰TAILS")
        lines.append("-" * 70)

        for index, problem in enumerate(
            scan["problems"],
            start=1,
        ):

            severity = problem.get(
                "severity",
                "info"
            ).upper()

            file_path = problem.get(
                "file",
                ""
            )

            message = problem.get(
                "message",
                ""
            )

            line = problem.get(
                "line"
            )

            location = file_path

            if line:
                location += f":{line}"

            lines.append(
                f"[{severity}] {location}"
            )

            if message:
                lines.append(
                    f"    {message}"
                )

            if "files" in problem:
                for duplicate in problem["files"]:
                    lines.append(
                        f"    - {duplicate}"
                    )

    lines.append("")
    lines.append("=" * 70)
    lines.append(
        "FIN DU DIAGNOSTIC â€” AUCUNE MODIFICATION EFFECTUÃ‰E"
    )
    lines.append("=" * 70)

    return "\n".join(lines)


# ============================================================
# SAUVEGARDE DU DIAGNOSTIC
# ============================================================

def save_diagnostic(
    root: Path,
    identity: dict[str, Any],
    scan: dict[str, Any],
) -> tuple[Path, Path]:

    diagnostics_dir = root / ".glitch" / "diagnostics"

    # CrÃ©ation uniquement du dossier technique de diagnostic.
    # Aucun fichier existant du projet n'est modifiÃ©.
    diagnostics_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    json_path = (
        diagnostics_dir
        / f"diagnostic_{timestamp}.json"
    )

    report_path = (
        diagnostics_dir
        / f"rapport_{timestamp}.txt"
    )

    data = {
        "identity": identity,
        "scan": scan,
    }

    json_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = generate_report(
        identity,
        scan,
    )

    report_path.write_text(
        report,
        encoding="utf-8",
    )

    return json_path, report_path


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print(" GLITCH â€” PROJECT SCANNER")
    print("=" * 70)
    print("")

    try:

        print("[1/4] Recherche du dossier maÃ®tre...")

        root = discover_master_directory()

        print(f"      âœ“ {root}")

        print("")
        print("[2/4] Identification du projet...")

        identity = identify_project(root)

        print(
            f"      âœ“ GLITCH probable : "
            f"{identity['likely_glitch_project']}"
        )

        print("")
        print("[3/4] Scan rÃ©cursif...")

        scan = scan_project(root)

        print(
            f"      âœ“ {scan['summary']['files']} fichiers"
        )

        print(
            f"      âœ“ {scan['summary']['directories']} dossiers"
        )

        print(
            f"      âœ“ {scan['summary']['problems']} "
            f"problÃ¨mes potentiels"
        )

        print("")
        print("[4/4] GÃ©nÃ©ration du diagnostic...")

        json_path, report_path = save_diagnostic(
            root,
            identity,
            scan,
        )

        print(f"      âœ“ JSON : {json_path}")
        print(f"      âœ“ Rapport : {report_path}")

        print("")
        print("=" * 70)
        print(" DIAGNOSTIC TERMINÃ‰")
        print("=" * 70)
        print("")
        print(
            "IMPORTANT : aucun fichier existant du projet "
            "n'a Ã©tÃ© modifiÃ©."
        )

        print("")
        print(
            generate_report(
                identity,
                scan,
            )
        )

        return 0

    except Exception as exc:

        print("")
        print("[ERREUR GLITCH]")
        print(str(exc))
        print("")

        return 1


if __name__ == "__main__":
    sys.exit(main())

