from __future__ import annotations

import argparse
import ctypes
import getpass
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


RACINE_PROJET = Path(__file__).resolve().parent.parent
FICHIER_MODE = RACINE_PROJET / "cache" / "mode_vscode.json"
URL_API = "http://127.0.0.1:8000"
URL_STREAMLIT = "http://127.0.0.1:8501"
DELAI_DEMARRAGE = 45


def lire_cle_windows() -> str:
    if os.name != "nt":
        return ""

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ
        ) as cle:
            valeur, _ = winreg.QueryValueEx(cle, "M_E_API_KEY")
    except FileNotFoundError:
        return ""
    except OSError as erreur:
        raise RuntimeError(
            "Impossible de lire la variable M_E_API_KEY du compte Windows."
        ) from erreur
    return str(valeur).strip()


def ecrire_cle_windows(valeur: str) -> None:
    if os.name != "nt":
        raise RuntimeError(
            "La configuration automatique est prévue pour un poste Windows."
        )

    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_SET_VALUE,
        ) as cle:
            winreg.SetValueEx(cle, "M_E_API_KEY", 0, winreg.REG_SZ, valeur)
    except OSError as erreur:
        raise RuntimeError(
            "Impossible d'enregistrer M_E_API_KEY dans les variables du compte Windows."
        ) from erreur


def configurer_cle_windows() -> str:
    cle_existante = lire_cle_windows()
    if cle_existante:
        print("Une clé API est déjà configurée pour ce compte Windows.")
        return cle_existante

    cle = os.environ.get("M_E_API_KEY", "").strip()
    if cle:
        confirmation = input(
            "Une clé est disponible dans ce terminal. "
            "L'enregistrer pour ce compte Windows ? [O/n] "
        ).strip().lower()
        if confirmation in {"n", "non"}:
            raise RuntimeError(
                "La clé doit être enregistrée dans le compte Windows "
                "pour le démarrage automatique."
            )
    else:
        cle = getpass.getpass("Saisir la clé API (saisie masquée) : ").strip()
        confirmation = getpass.getpass("Confirmer la clé API : ").strip()
        if not cle or cle != confirmation:
            raise ValueError("Les deux saisies de clé API doivent être identiques.")

    ecrire_cle_windows(cle)
    print("Clé API enregistrée dans les variables de ce compte Windows.")
    return cle


def lire_mode() -> str:
    if not FICHIER_MODE.is_file():
        return "technique"
    try:
        configuration = json.loads(FICHIER_MODE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        raise RuntimeError(
            f"Le fichier de configuration locale est illisible : {FICHIER_MODE}"
        ) from erreur

    if not isinstance(configuration, dict):
        raise ValueError("Le fichier de configuration locale doit contenir un objet JSON.")
    mode = configuration.get("mode")
    if mode not in {"technique", "agent_non_technique"}:
        raise ValueError(
            "Le mode local doit être 'technique' ou 'agent_non_technique'."
        )
    return mode


def enregistrer_mode(mode: str) -> None:
    FICHIER_MODE.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER_MODE.with_suffix(".tmp")
    temporaire.write_text(
        json.dumps({"mode": mode}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporaire.replace(FICHIER_MODE)


def configurer_mode() -> None:
    print("Choisir l'utilisation prévue de ce poste :")
    print("1. Utilisation technique dans VS Code")
    print("2. Interface Streamlit pour un agent non technique")
    choix = input("Votre choix [1/2] : ").strip()

    if choix == "1":
        enregistrer_mode("technique")
        print("Mode technique enregistré; l'interface ne démarrera pas à l'ouverture.")
        return
    if choix != "2":
        raise ValueError("Choix invalide : saisir 1 ou 2.")

    cle = configurer_cle_windows()
    enregistrer_mode("agent_non_technique")
    os.environ["M_E_API_KEY"] = cle
    print(
        "Mode Streamlit enregistré. À la prochaine ouverture du dossier, "
        "l'API et l'interface démarreront automatiquement."
    )


def requete_api_pret(cle_api: str) -> bool:
    requete = urllib.request.Request(
        f"{URL_API}/enquetes?limite=1",
        headers={"x-api-key": cle_api},
    )
    try:
        with urllib.request.urlopen(requete, timeout=2) as reponse:
            return reponse.status == 200
    except urllib.error.HTTPError as erreur:
        if erreur.code in {403, 503}:
            raise RuntimeError(
                "Une API répond déjà sur le port 8000, mais n'accepte pas "
                "la clé configurée. Arrêter cette API puis rouvrir le projet."
            ) from erreur
        if erreur.code >= 500:
            raise RuntimeError(
                f"L'API répond avec l'erreur HTTP {erreur.code}. "
                "Consulter son journal de démarrage."
            ) from erreur
        return False
    except (urllib.error.URLError, TimeoutError):
        return False


def requete_streamlit_pret() -> bool:
    try:
        with urllib.request.urlopen(
            f"{URL_STREAMLIT}/_stcore/health", timeout=2
        ) as reponse:
            return reponse.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def demarrer_processus(
    commande: list[str], environnement: dict[str, str], journal: Path
) -> subprocess.Popen:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as sortie:
        options = {
            "cwd": RACINE_PROJET,
            "env": environnement,
            "stdin": subprocess.DEVNULL,
            "stdout": sortie,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if os.name == "nt":
            options["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        return subprocess.Popen(commande, **options)


def attendre_service(
    nom: str,
    verifier,
    processus: subprocess.Popen,
    journal: Path,
) -> None:
    echeance = time.monotonic() + DELAI_DEMARRAGE
    while time.monotonic() < echeance:
        if processus.poll() is not None:
            extraits = journal.read_text(encoding="utf-8", errors="replace").splitlines()
            detail = "\n".join(extraits[-12:])
            raise RuntimeError(
                f"{nom} s'est arrêté pendant le démarrage. "
                f"Journal : {journal}\n{detail}"
            )
        if verifier():
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"{nom} n'a pas répondu après {DELAI_DEMARRAGE} secondes. "
        f"Consulter le journal : {journal}"
    )


def demarrer_application() -> None:
    if os.name != "nt":
        raise RuntimeError("Le démarrage automatique est prévu pour Windows.")

    cle_api = lire_cle_windows() or os.environ.get("M_E_API_KEY", "").strip()
    if not cle_api:
        raise RuntimeError(
            "La clé M_E_API_KEY n'est pas configurée pour ce compte Windows. "
            "Relancer la tâche de configuration dans VS Code."
        )

    environnement_api = os.environ.copy()
    environnement_api["M_E_API_KEY"] = cle_api
    environnement_api["PYTHONDONTWRITEBYTECODE"] = "1"
    environnement_app = environnement_api.copy()
    environnement_app["M_E_MODE_NON_TECHNIQUE"] = "1"

    dossier_journaux = RACINE_PROJET / "outputs" / "logs"
    journal_api = dossier_journaux / "api.log"
    journal_streamlit = dossier_journaux / "streamlit.log"
    python = sys.executable

    if not requete_api_pret(cle_api):
        processus_api = demarrer_processus(
            [
                python,
                "-m",
                "uvicorn",
                "src.opt_api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            environnement_api,
            journal_api,
        )
        attendre_service(
            "L'API", lambda: requete_api_pret(cle_api), processus_api, journal_api
        )

    if not requete_streamlit_pret():
        processus_streamlit = demarrer_processus(
            [
                python,
                "-m",
                "streamlit",
                "run",
                str(RACINE_PROJET / "src" / "opt_app.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                "8501",
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            environnement_app,
            journal_streamlit,
        )
        attendre_service(
            "Streamlit",
            requete_streamlit_pret,
            processus_streamlit,
            journal_streamlit,
        )

    if not webbrowser.open_new_tab(URL_STREAMLIT):
        raise RuntimeError(
            f"L'application fonctionne, mais le navigateur n'a pas pu s'ouvrir. "
            f"Ouvrir manuellement {URL_STREAMLIT}."
        )


def afficher_erreur(message: str) -> None:
    print(message, file=sys.stderr)
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(
                None, message, "Démarrage de l'outil M&E", 0x10
            )
        except (AttributeError, OSError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configurer le démarrage local de Streamlit dans VS Code (étape 00)."
    )
    parser.add_argument(
        "--configurer",
        action="store_true",
        help="choisir le mode technique ou le démarrage automatique de Streamlit",
    )
    arguments = parser.parse_args()

    if arguments.configurer:
        try:
            configurer_mode()
        except (EOFError, OSError, RuntimeError, ValueError) as erreur:
            print(f"Configuration impossible : {erreur}", file=sys.stderr)
            return 1
        return 0

    try:
        if lire_mode() != "agent_non_technique":
            return 0
        demarrer_application()
    except (OSError, RuntimeError, ValueError) as erreur:
        afficher_erreur(str(erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
