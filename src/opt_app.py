"""Point d'entrée Streamlit de l'interface locale."""

import streamlit as st
import requests
import pandas as pd
import os
import json
import hashlib
from pathlib import Path
import streamlit.components.v1 as components

st.set_page_config(page_title="Interface M&E - Gestion des Enquêtes", page_icon="👥", layout="wide")

# =========================================================
# GESTION DYNAMIQUE DU PROJET ACTIF & MÉTADONNÉES OPÉRATIONNELLES
# =========================================================
FICHIER_CONFIG_PROJET = os.path.join("outputs", "projet_actif.json")
CONFIG_PAR_DEFAUT = {
    "id_projet": "Enquete_test_RDC_2020",
    "nom_affiche": "Enquête Multisectorielle RDC 2020",
    "pays": "République Démocratique du Congo (RDC)",
    "province_region": "Province de l'Équateur",
    "axe": "Axe Bikoro - Mbandaka",
    "periode": "Année 2020 - 2021",
    "profil_menages": "Familles déplacées internes, retournées et communautés hôtes",
    "echantillon": "~3 000 ménages réels de terrain (extrapolés à 50 000 en base d'essai)",
    "cadre_evaluation": "Standards JIAF 2.0 (Scores sectoriels HHS, WASH, AME, AGRO)",
    "avertissement_ethique": (
        "Les modèles prédictifs et les seuils de sévérité sont strictement calibrés sur le profil socio-démographique "
        "et de crise de la Province de l'Équateur (RDC). Tout déploiement sur une crise humanitaire différente (ex: Yémen, "
        "sécheresse sahélienne) exige impérativement un réétalonnage préalable par le staff technique, les facteurs de vulnérabilité "
        "et les chocs vécus étant substantiellement distincts."
    )
}

def charger_config_projet() -> dict:
    if os.path.exists(FICHIER_CONFIG_PROJET):
        try:
            with open(FICHIER_CONFIG_PROJET, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**CONFIG_PAR_DEFAUT, **cfg}
        except Exception:
            return CONFIG_PAR_DEFAUT
    return CONFIG_PAR_DEFAUT

def sauvegarder_config_projet(nouvelle_config: dict):
    os.makedirs(os.path.dirname(FICHIER_CONFIG_PROJET), exist_ok=True)
    with open(FICHIER_CONFIG_PROJET, "w", encoding="utf-8") as f:
        json.dump(nouvelle_config, f, ensure_ascii=False, indent=2)

config_projet = charger_config_projet()

# Dictionnaire de vulgarisation des livrables (Noms compréhensibles pour le terrain)
DICT_LABELS_LIVRABLES = {
    "donnees_nettoyees.csv": {
        "label": "📊 Données nettoyées",
        "desc": "Données Kobo complètes après audit, dédoublonnage et corrections de validité.",
        "technique": False,
    },
    "rapport_execution_m_e.md": {
        "label": "📋 Rapport de nettoyage",
        "desc": "Anomalies détectées, doublons supprimés et taux de consentement.",
        "technique": False,
    },
    "rapport_nettoyage_console.txt": {
        "label": "📝 Journal de nettoyage",
        "desc": "Trace détaillée des règles appliquées lors du nettoyage.",
        "technique": False,
    },
    "eda_rapport.html": {
        "label": "🌐 Rapport d'analyse",
        "desc": "Diagnostic statistique des vulnérabilités (HHS, WASH, AME, agriculture).",
        "technique": False,
    },
    "menages_prioritaires.csv": {
        "label": "🎯 Ménages prioritaires",
        "desc": "Ménages ciblés par le modèle avec leurs scores de vulnérabilité.",
        "technique": False,
    },
    "menages_prioritaires_assistance.csv": {
        "label": "🎯 Ménages prioritaires",
        "desc": "Ménages ciblés par le modèle avec leurs scores de vulnérabilité.",
        "technique": False,
    },
    "dashboard_interactif.html": {
        "label": "🖥️ Dashboard interactif",
        "desc": "Tableau de bord d'une page, utilisable hors connexion : carte, KPI et graphiques.",
        "technique": False,
    },
    "template_dashboard.pbix": {
        "label": "📐 Modèle Power BI",
        "desc": "Modèle Power BI Desktop : à télécharger puis à ouvrir avec Power BI Desktop.",
        "technique": False,
    },
    "apercu_template_powerbi.png": {
        "label": "🖼️ Aperçu Power BI",
        "desc": "Capture d'écran du modèle Power BI.",
        "technique": True,
    },
    "edna_mode_capit.json": {
        "label": "🧠 Base d'apprentissage de l'agent",
        "desc": "Incohérences du XLSForm et conseils pour la prochaine enquête.",
        "technique": True,
    },
    "alertes_dashboard.csv": {
        "label": "🚨 Alertes du dashboard",
        "desc": "Alertes recalculées à chaque génération du dashboard.",
        "technique": True,
    },
    "donnees_dashboard.csv": {
        "label": "📈 Données du dashboard",
        "desc": "Base enrichie (indicateurs, GPS, prédictions) pour Power BI et Tableau.",
        "technique": True,
    },
    "enquete_ms.db": {
        "label": "🗄️ Base SQLite",
        "desc": "Base relationnelle organisée par rubriques sectorielles.",
        "technique": True,
    },
    "modele_vulnerabilite.joblib": {
        "label": "🤖 Modèle de ciblage",
        "desc": "Pipeline scikit-learn entraîné pour l'aide à la décision.",
        "technique": True,
    },
    "rapport_modelisation.json": {
        "label": "📉 Performances du modèle",
        "desc": "Métriques de validation et variables les plus influentes.",
        "technique": True,
    },
    "projet_actif.json": {
        "label": "⚙️ Fiche de l'enquête",
        "desc": "Identité de l'enquête active et contexte géographique.",
        "technique": True,
    },
}

# CSS professionnel inspiré de KoboToolbox et du design Agentic Data Quality
st.markdown("""
    <style>
    /* 1. Typographie générale et fond */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    
    .stApp {
        background: linear-gradient(180deg, #F8FAFC 0%, #EEF2F6 100%);
    }

    /* 2. Barre latérale (Sidebar) Bleu Nuit Humanitaire */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0A192F 0%, #0F2544 100%) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3, 
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] p {
        color: #FFFFFF !important;
    }
    [data-testid="stSidebar"] .stCaption p {
        color: #94A3B8 !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255, 255, 255, 0.15) !important;
    }

    /* Dans la sidebar, les inputs DOIVENT être sur fond blanc avec texte bleu foncé très lisible */
    [data-testid="stSidebar"] input {
        color: #0F2544 !important;
        -webkit-text-fill-color: #0F2544 !important;
        background-color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    /* Badge de projet dans la sidebar */
    .sidebar-badge {
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(16, 185, 129, 0.15);
        border: 1px solid rgba(16, 185, 129, 0.4);
        padding: 6px 12px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #34D399 !important;
        margin-top: 10px;
        margin-bottom: 12px;
    }

    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 0 16px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.15);
        margin-bottom: 18px;
    }
    .sidebar-brand-icon {
        background: linear-gradient(135deg, #0060DF 0%, #0098FF 100%);
        width: 40px;
        height: 40px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        box-shadow: 0 4px 12px rgba(0, 96, 223, 0.35);
    }

    /* 3. Hero Banner Kobo / M&E */
    .hero-container {
        background: linear-gradient(135deg, #0B2545 0%, #133E68 60%, #1D548C 100%);
        border-radius: 18px;
        padding: 30px 34px;
        color: #FFFFFF !important;
        margin-bottom: 20px;
        box-shadow: 0 12px 30px -10px rgba(11, 37, 69, 0.25);
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    .hero-container * {
        color: #FFFFFF !important;
    }
    .hero-badge {
        display: inline-block;
        background: rgba(255, 255, 255, 0.18);
        backdrop-filter: blur(8px);
        padding: 5px 14px;
        border-radius: 20px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #93C5FD !important;
        margin-bottom: 12px;
        border: 1px solid rgba(255, 255, 255, 0.25);
    }
    .hero-title {
        font-size: 2.0rem;
        font-weight: 800;
        line-height: 1.25;
        margin: 0 0 10px 0;
        color: #FFFFFF !important;
        letter-spacing: -0.03em;
    }
    .hero-subtitle {
        font-size: 0.95rem;
        line-height: 1.55;
        color: #E2E8F0 !important;
        max-width: 860px;
        margin: 0;
    }

    /* 4. Cartes piliers de réassurance / features */
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 16px;
        margin-bottom: 20px;
    }
    .feature-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
        word-break: normal;
        overflow-wrap: break-word;
        hyphens: auto;
    }
    .feature-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 18px rgba(0, 0, 0, 0.06);
        border-color: #0060DF;
    }
    .feature-title {
        font-weight: 700;
        font-size: 0.92rem;
        color: #0F2544 !important;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 8px;
        word-break: normal;
    }
    .feature-desc {
        font-size: 0.82rem;
        color: #334155 !important;
        line-height: 1.45;
        margin: 0;
        word-break: normal;
    }

    /* 5. Titres de section modernisés (Plus de gris vieillot) */
    h1, h2, h3 {
        color: #0B2545 !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em !important;
    }

    /* 6. Boutons stylisés façon SaaS / KoboToolbox */
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0060DF 0%, #004BB5 100%) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        border: none !important;
        padding: 8px 20px !important;
        box-shadow: 0 4px 12px rgba(0, 96, 223, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="primary"]:hover {
        box-shadow: 0 6px 16px rgba(0, 96, 223, 0.38) !important;
        transform: translateY(-1px) !important;
    }
    div.stButton > button[kind="secondary"] {
        background: #FFFFFF !important;
        color: #0B2545 !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: #0060DF !important;
        color: #0060DF !important;
    }

    /* 7. Champs de saisie (Inputs & File Uploaders) dans la page principale */
    div[data-testid="stTextInputRootElement"],
    div[data-baseweb="input"], 
    div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 8px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
    }
    div[data-testid="stTextInputRootElement"] input,
    input[data-testid="stTextInputField"],
    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input {
        background-color: #FFFFFF !important;
        color: #0B2545 !important;
        -webkit-text-fill-color: #0B2545 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }
    div[data-testid="stTextInputRootElement"]:focus-within,
    div[data-baseweb="input"]:focus-within {
        border-color: #0060DF !important;
        box-shadow: 0 0 0 3px rgba(0, 96, 223, 0.15) !important;
    }
    input::placeholder {
        color: #64748B !important;
        -webkit-text-fill-color: #64748B !important;
        font-weight: 400 !important;
    }

    /* Labels de formulaire toujours très lisibles en bleu marine foncé */
    section.main label, 
    section.main [data-testid="stWidgetLabel"] p {
        color: #0B2545 !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
    }

    /* Zone de dépôt de fichiers Kobo (File Uploader) bien claire et nette */
    [data-testid="stFileUploader"] {
        background-color: #FFFFFF !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background-color: #FFFFFF !important;
        border: 2px dashed #CBD5E1 !important;
        border-radius: 12px !important;
        padding: 24px !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.02) !important;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #0060DF !important;
        background-color: #F8FAFC !important;
    }
    [data-testid="stFileUploaderDropzone"] * {
        color: #0B2545 !important;
    }
    [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stFileUploaderDropzoneInstructions"] {
        color: #475569 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
    }
    [data-testid="stFileUploaderDropzone"] button {
        background: linear-gradient(135deg, #0060DF 0%, #004BB5 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 8px 18px !important;
        box-shadow: 0 2px 8px rgba(0, 96, 223, 0.3) !important;
    }
    [data-testid="stFileUploaderDropzone"] button * {
        color: #FFFFFF !important;
    }

    /* 8. Métriques / Cartouches KPI */
    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        color: #475569 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 800 !important;
        color: #0B2545 !important;
    }

    /* 9. Expanders ultra modernes (Plus de gris vieillot / ardoise terne) */
    [data-testid="stExpander"] {
        background: #FFFFFF !important;
        border: 1.5px solid #CBD5E1 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03) !important;
        overflow: hidden !important;
    }
    [data-testid="stExpander"] > details > summary {
        background: linear-gradient(90deg, #F1F5F9 0%, #E2E8F0 100%) !important;
        color: #0B2545 !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        padding: 12px 18px !important;
        border-bottom: 1px solid #CBD5E1 !important;
        transition: background 0.2s ease !important;
    }
    [data-testid="stExpander"] > details > summary:hover {
        background: #E2E8F0 !important;
        color: #0060DF !important;
    }
    [data-testid="stExpander"] > details > div {
        background: #FFFFFF !important;
        padding: 16px 20px !important;
        color: #0F172A !important;
    }

    /* 10. Tags de code en ligne : badge moderne bleu roi (fini le gris vieillot aux écritures vertes) */
    code, .stMarkdown code {
        background-color: #EFF6FF !important;
        color: #0052CC !important;
        border: 1px solid #BFDBFE !important;
        border-radius: 6px !important;
        padding: 3px 8px !important;
        font-weight: 600 !important;
        font-size: 0.9em !important;
        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- FONCTION UTILITAIRE : GESTION DES ERREURS EN FRANÇAIS POUR LE TERRAIN ---
def afficher_erreur_terrain(e: Exception, contexte: str = "une action"):
    """Convertit n'importe quelle erreur technique en message clair et rassurant pour les agents."""
    erreur_str = str(e).lower()
    
    if "connection refused" in erreur_str or "failed to establish" in erreur_str or "connexion" in erreur_str:
        st.error(f"❌ **Impossible de joindre le serveur :** Vérifiez que l'API est bien lancée et que l'URL est correcte.")
    elif "401" in erreur_str or "forbidden" in erreur_str or "unauthorized" in erreur_str:
        st.error(f"❌ **Accès refusé :** Votre clé d'API (x-api-key) est incorrecte ou non reconnue.")
    elif "404" in erreur_str:
        st.error(f"❌ **Élément introuvable :** La ressource demandée ou le ménage spécifié n'existe pas dans le système.")
    else:
        st.error(f"❌ **Erreur lors de {contexte} :** Une anomalie technique est survenue. Veuillez contacter le support si le problème persiste.")

# =========================================================
# 1. BARRE LATÉRALE & AUTHENTIFICATION BLOQUANTE
# =========================================================
with st.sidebar:
    st.markdown("""
        <div class="sidebar-brand">
            <div class="sidebar-brand-icon">🌐</div>
            <div>
                <div style="font-weight: 700; font-size: 1.05rem; color: #FFFFFF; line-height: 1.2;">Kobo M&E Hub</div>
                <div style="font-size: 0.72rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em;">Humanitarian Data Engine</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
        <div class="sidebar-badge">
            <span style="font-size: 10px;">●</span> {config_projet.get('nom_affiche', 'Enquête Multisectorielle')}
        </div>
    """, unsafe_allow_html=True)

st.sidebar.header("⚙️ Configuration & Sécurité")
API_URL = st.sidebar.text_input("URL de l'API", value="http://127.0.0.1:8000")

# Barrière d'authentification stricte
API_KEY_ATTENDUE = os.environ.get("M_E_API_KEY", "").strip()
if os.environ.get("M_E_MODE_NON_TECHNIQUE") == "1":
    API_KEY = API_KEY_ATTENDUE
    st.sidebar.caption("Connexion locale configurée par le responsable technique.")
else:
    API_KEY = st.sidebar.text_input("Clé d'API (x-api-key)", value="", type="password")

if not API_KEY_ATTENDUE:
    st.sidebar.error(
        "La clé API n'est pas configurée dans ce terminal. "
        "Arrêtez Streamlit et définissez M_E_API_KEY avant de le relancer."
    )
    st.stop()

if not API_KEY:
    st.sidebar.info("ℹ️ Veuillez saisir votre clé de sécurité pour déverrouiller l'application.")
    st.warning("🔒 Accès restreint. Veuillez entrer le jeton de sécurité dans la barre latérale ci-contre.")
    st.stop()
elif API_KEY != API_KEY_ATTENDUE:
    st.sidebar.error("❌ Clé d'API incorrecte.")
    st.stop()

st.sidebar.success("✅ Authentifié avec succès")
headers = {"x-api-key": API_KEY}

st.sidebar.markdown("---")
st.sidebar.markdown("""
    <div style="font-weight: 700; font-size: 0.85rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">
        📌 Navigation
    </div>
""", unsafe_allow_html=True)

menu = st.sidebar.radio(
    "Choisir une action :",
    (
        "➕ Importer / Ajouter des enquêtes",
        "📋 Lister les enquêtes (CSV propre)",
        "🔍 Consulter par Code Jeton",
        "✏️ Modifier une enquête (Non technique)",
        "🗑️ Supprimer un ménage",
        "📊 Analyser les données",
        "🤖 Ciblage & Machine Learning",
        "📖 Guides & Documentation",
    ),
    label_visibility="collapsed",
)

# ---------------------------------------------------------
# EXPLORATEUR DE LIVRABLES DU PROJET (Sidebar)
# ---------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("""
    <div style="font-weight: 700; font-size: 0.85rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">
        📦 Livrables du Projet
    </div>
""", unsafe_allow_html=True)

outputs_dir = "outputs" if os.path.exists("outputs") and os.listdir("outputs") else "outputs_demo"
if os.path.exists(outputs_dir):
    fichiers_dispos = []
    for root, dirs, files in os.walk(outputs_dir):
        for f in files:
            if not f.endswith(".tmp") and not f.endswith(".pyc") and not f.endswith(".gitignore"):
                fichiers_dispos.append(os.path.relpath(os.path.join(root, f), outputs_dir))
    
    if fichiers_dispos:
        def infos_livrable(relpath: str) -> dict:
            nom_f = os.path.basename(relpath)
            if nom_f in DICT_LABELS_LIVRABLES:
                return DICT_LABELS_LIVRABLES[nom_f]
            emoji = {".csv": "📊", ".html": "🌐", ".json": "⚙️", ".md": "📋", ".txt": "📝", ".db": "🗄️", ".png": "🖼️"}.get(os.path.splitext(nom_f)[1].lower(), "📄")
            return {"label": f"{emoji} {nom_f}", "desc": "Fichier généré par le projet.", "technique": True}

        def formater_livrable(relpath: str) -> str:
            return infos_livrable(relpath)["label"]

        # Ordre logique de travail : nettoyage, analyse, ciblage, dashboard, puis fichiers techniques
        ordre_livrables = list(DICT_LABELS_LIVRABLES)
        def cle_tri_livrable(f: str):
            nom_f = os.path.basename(f)
            rang = ordre_livrables.index(nom_f) if nom_f in ordre_livrables else len(ordre_livrables)
            return (infos_livrable(f).get('technique', True), rang, nom_f)

        afficher_techniques = st.sidebar.toggle(
            "Afficher les fichiers techniques", value=False, key="toggle_livrables_techniques"
        )
        fichiers_visibles = [
            f for f in fichiers_dispos if afficher_techniques or not infos_livrable(f).get("technique")
        ] or fichiers_dispos
        fichier_choisi = st.sidebar.selectbox(
            "Sélectionner un livrable :",
            sorted(fichiers_visibles, key=cle_tri_livrable),
            format_func=formater_livrable,
            key="select_output_sidebar",
        )
        chemin_complet = os.path.join(outputs_dir, fichier_choisi)
        taille_ko = os.path.getsize(chemin_complet) / 1024
        nom_base = os.path.basename(fichier_choisi)
        info_l = DICT_LABELS_LIVRABLES.get(nom_base, {"label": nom_base, "desc": "Fichier généré"})
        
        st.sidebar.caption(f"ℹ️ *{info_l['desc']}*")
        st.sidebar.caption(f"📁 Fichier : `{nom_base}` · Taille : **{taille_ko:.1f} Ko**")
        
        col_side_view, col_side_dl = st.sidebar.columns(2)
        with col_side_view:
            if st.button("👁️ Consulter", key="btn_consulter_sidebar", use_container_width=True):
                st.session_state["fichier_a_consulter"] = chemin_complet
                st.rerun()

        with col_side_dl:
            try:
                with open(chemin_complet, "rb") as f_dl:
                    donnees_bytes = f_dl.read()
                
                mime_type = "application/octet-stream"
                if fichier_choisi.endswith(".csv"): mime_type = "text/csv"
                elif fichier_choisi.endswith(".html"): mime_type = "text/html"
                elif fichier_choisi.endswith(".json"): mime_type = "application/json"
                elif fichier_choisi.endswith(".md"): mime_type = "text/markdown"
                elif fichier_choisi.endswith(".txt"): mime_type = "text/plain"
                elif fichier_choisi.endswith(".png"): mime_type = "image/png"
                elif fichier_choisi.endswith(".db"): mime_type = "application/vnd.sqlite3"
                elif fichier_choisi.endswith((".pbix", ".pbit")): mime_type = "application/octet-stream"
                
                st.download_button(
                    label="⬇️ Télécharger",
                    data=donnees_bytes,
                    file_name=nom_base,
                    mime=mime_type,
                    key=f"dl_btn_{hashlib.md5(fichier_choisi.encode()).hexdigest()[:8]}",
                    use_container_width=True,
                )
            except Exception as e_f:
                st.caption(f"Lecture impossible : {e_f}")
    else:
        st.sidebar.info("Aucun livrable généré pour l'instant.")
else:
    st.sidebar.info("Dossier outputs vide.")

# =========================================================
# BANDEAU HERO GÉNÉRAL & CARTES PILIERS (Style Agentic Data Quality)
# =========================================================
# Un changement d'action dans le menu ferme l'aperçu en cours
if st.session_state.get("menu_precedent") != menu:
    if "menu_precedent" in st.session_state:
        st.session_state["fichier_a_consulter"] = None
    st.session_state["menu_precedent"] = menu

# Fichier à consulter en direct (depuis la barre latérale)
fichier_a_consulter = st.session_state.get("fichier_a_consulter")
if fichier_a_consulter and os.path.exists(fichier_a_consulter):
    nom_base = os.path.basename(fichier_a_consulter)
    info_livrable = infos_livrable(os.path.relpath(fichier_a_consulter, outputs_dir))
    
    st.markdown(f"""
        <div style="background: #F0FDF4; border: 1.5px solid #86EFAC; border-left: 5px solid #16A34A; border-radius: 12px; padding: 16px 20px; margin-bottom: 20px;">
            <div style="font-weight: 800; font-size: 1.1rem; color: #14532D; margin-bottom: 4px;">
                👁️ Visualisation du Livrable : {info_livrable['label']}
            </div>
            <div style="font-size: 0.85rem; color: #166534;">
                {info_livrable['desc']} · <em>Fichier source : outputs/{nom_base}</em>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    col_close, _ = st.columns([1, 5])
    with col_close:
        if st.button("❌ Fermer l'aperçu du livrable", key="close_consultation_top"):
            st.session_state["fichier_a_consulter"] = None
            st.rerun()

    try:
        if fichier_a_consulter.endswith(".csv"):
            df_vue = pd.read_csv(fichier_a_consulter, low_memory=False)
            st.dataframe(df_vue.head(200), use_container_width=True)
            st.caption(f"Affichage interactif des {min(200, len(df_vue))} premières lignes sur un total de {len(df_vue):,} enregistrements.")
        elif fichier_a_consulter.endswith(".md"):
            with open(fichier_a_consulter, "r", encoding="utf-8") as f_vue:
                st.markdown(f_vue.read())
        elif fichier_a_consulter.endswith(".txt"):
            with open(fichier_a_consulter, "r", encoding="utf-8") as f_vue:
                st.code(f_vue.read(), language="text")
        elif fichier_a_consulter.endswith(".json"):
            with open(fichier_a_consulter, "r", encoding="utf-8") as f_vue:
                st.json(json.load(f_vue))
        elif fichier_a_consulter.endswith(".html"):
            with open(fichier_a_consulter, "r", encoding="utf-8") as f_vue:
                st.components.v1.html(f_vue.read(), height=750, scrolling=True)
        elif fichier_a_consulter.endswith((".pbix", ".pbit")):
            st.info("Ce modèle Power BI s'ouvre avec **Power BI Desktop** (gratuit, version hors ligne). Téléchargez-le avec le bouton ci-dessous, ouvrez-le, puis cliquez sur **Actualiser** pour charger les dernières données (`donnees_dashboard.csv` et `alertes_dashboard.csv`).")
            with open(fichier_a_consulter, "rb") as f_pbi:
                st.download_button("⬇️ Télécharger le modèle Power BI", data=f_pbi.read(), file_name=nom_base, mime="application/octet-stream", key="dl_pbi_consultation")
            apercu_pbi = Path("outputs") / "apercu_template_powerbi.png"
            if apercu_pbi.exists():
                st.image(str(apercu_pbi), caption="Aperçu du modèle Power BI", use_container_width=True)
        elif fichier_a_consulter.endswith(".png"):
            st.image(fichier_a_consulter, use_container_width=True)
        elif fichier_a_consulter.endswith(".db"):
            st.info("Ce livrable est une base de données relationnelle SQLite (`.db`). Utilisez l'onglet « Consulter par Code Jeton » ou « Lister les enquêtes » pour explorer son contenu avec le moteur SQL.")
    except Exception as e_v:
        st.error(f"Erreur lors de la lecture du fichier : {e_v}")
    st.stop()

st.markdown(f"""
    <div class="hero-container">
        <div class="hero-badge">Projet : {config_projet.get('id_projet', 'Enquete_test_RDC_2020')} · {config_projet.get('province_region', 'RDC')} · {config_projet.get('cadre_evaluation', 'JIAF 2.0')}</div>
        <div class="hero-title">Plateforme de Suivi Multisectoriel & Ciblage IA</div>
        <p class="hero-subtitle">
            Plateforme humanitaire dédiée au suivi, à la vérification de la qualité des données collectées sur KoboToolbox 
            et à l'analyse des vulnérabilités des ménages, garantissant une aide équitable et le respect du principe <em>Do No Harm</em>.
        </p>
    </div>
    
    <div class="feature-grid">
        <div class="feature-card">
            <div class="feature-title">📥 1. Ingestion & Rangement</div>
            <p class="feature-desc">Contrôle qualité des exports Kobo, dédoublonnage automatique et archivage des données.</p>
        </div>
        <div class="feature-card">
            <div class="feature-title">🌐 2. Analyse des Vulnérabilités</div>
            <p class="feature-desc">Évaluation des détresses selon les standards humanitaires (Alimentation, Eau, Biens essentiels).</p>
        </div>
        <div class="feature-card">
            <div class="feature-title">🤖 3. Priorisation & Aide au Ciblage</div>
            <p class="feature-desc">Pré-repérage rapide des foyers à risque élevé et audit transparent des décisions d'assistance.</p>
        </div>
    </div>

    <!-- CARTOUCHE DE CONTEXTE OPÉRATIONNEL & GÉOGRAPHIQUE TRÈS VISIBLE -->
    <div style="background: #FFFFFF; border: 1.5px solid #CBD5E1; border-left: 5px solid #0060DF; border-radius: 14px; padding: 18px 24px; margin-bottom: 26px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div style="font-weight: 800; font-size: 1.05rem; color: #0B2545;">
                📍 Fiche d'Identité & Précisions Géographiques de l'Enquête Active
            </div>
            <span style="background: #EFF6FF; color: #0060DF; font-weight: 700; font-size: 0.78rem; padding: 4px 12px; border-radius: 20px; border: 1px solid #BFDBFE;">
                ID Enquête : {config_projet.get('id_projet', 'Enquete_test_RDC_2020')}
            </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; font-size: 0.88rem; color: #1E293B; margin-bottom: 14px;">
            <div><strong>🌍 Pays & Province :</strong> {config_projet.get('pays', 'RDC')} · {config_projet.get('province_region', 'Province de l’Équateur')}</div>
            <div><strong>📍 Axe géographique :</strong> {config_projet.get('axe', 'Axe Bikoro - Mbandaka')}</div>
            <div><strong>📅 Période de collecte :</strong> {config_projet.get('periode', '2020 - 2021')}</div>
            <div><strong>👥 Profil des ménages :</strong> {config_projet.get('profil_menages', 'Déplacés et hôtes')}</div>
            <div><strong>📊 Échantillon de travail :</strong> {config_projet.get('echantillon', '~3 000 ménages')}</div>
            <div><strong>🌐 Cadre d'évaluation :</strong> {config_projet.get('cadre_evaluation', 'Standards JIAF 2.0')}</div>
        </div>
        <div style="background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 8px; padding: 12px 16px; font-size: 0.83rem; color: #92400E; line-height: 1.5;">
            ⚠️ <strong>Avertissement éthique de transposabilité géographique :</strong> {config_projet.get('avertissement_ethique', '')}
        </div>
    </div>
""", unsafe_allow_html=True)

# =========================================================
# 4. IMPORTER / AJOUTER
# =========================================================
if menu == "➕ Importer / Ajouter des enquêtes":
    st.header("➕ Ajouter ou réhabiliter une enquête")
    mode_ajout = st.radio(
        "Choisir le parcours :",
        ("Nouvel export Kobo", "Réhabiliter une enquête supprimée"),
        horizontal=True,
    )

    if mode_ajout == "Nouvel export Kobo":
        st.info(
            "📋 **Démarche à suivre pour importer et nettoyer vos données :**\n\n"
            "1. **Définir la mission / enquête :** Renseignez le nom, la zone géographique et l'année de l'enquête pour mettre à jour la plateforme.\n"
            "2. **Déposer les fichiers :** Fournissez l'export brut issu de Kobo (CSV ou XLSX) et le questionnaire XLSForm correspondant (XLSX).\n"
            "3. **Vérifier les colonnes et dates :** Ajustez si besoin les noms de colonnes et dates officielles, puis cliquez sur **« Vérifier les fichiers avant nettoyage »**.\n"
            "4. **Lancer le nettoyage :** Validez le bilan pour générer les fichiers propres et les rapports d'audit dans `outputs/`.\n"
            "5. **Charger en base SQL :** Validez l'affectation des rubriques pour alimenter la base de données relationnelle."
        )

        with st.expander("📍 Définir les paramètres & contexte géographique de l'enquête", expanded=True):
            col_id1, col_id2 = st.columns(2)
            with col_id1:
                nom_mission = st.text_input(
                    "Identifiant / Nom court de la mission :",
                    value=config_projet.get("id_projet", "Enquete_test_RDC_2020"),
                    help="Exemple : Enquete_Nord_Kivu_2024 ou Enquete_Yemen_2025"
                )
                pays_mission = st.text_input(
                    "Pays :",
                    value=config_projet.get("pays", "République Démocratique du Congo (RDC)"),
                )
                region_mission = st.text_input(
                    "Province / Région :",
                    value=config_projet.get("province_region", "Province de l'Équateur"),
                )
            with col_id2:
                axe_mission = st.text_input(
                    "Axe / Zone de collecte :",
                    value=config_projet.get("axe", "Axe Bikoro - Mbandaka"),
                )
                periode_mission = st.text_input(
                    "Période de collecte :",
                    value=config_projet.get("periode", "Année 2020 - 2021"),
                )
                profil_mission = st.text_input(
                    "Profil des ménages ciblés :",
                    value=config_projet.get("profil_menages", "Familles déplacées internes, retournées et communautés hôtes"),
                )
            if st.button("💾 Enregistrer ces informations pour l'enquête active"):
                cfg_maj = {
                    **config_projet,
                    "id_projet": nom_mission.strip(),
                    "nom_affiche": f"Enquête {pays_mission.strip()} {periode_mission.strip()}",
                    "pays": pays_mission.strip(),
                    "province_region": region_mission.strip(),
                    "axe": axe_mission.strip(),
                    "periode": periode_mission.strip(),
                    "profil_menages": profil_mission.strip(),
                }
                sauvegarder_config_projet(cfg_maj)
                st.success("✅ Informations de l'enquête enregistrées ! L'affichage du projet est actualisé.")
                st.rerun()

        uploaded_file = st.file_uploader(
            "Export brut Kobo (CSV ou XLSX)",
            type=["csv", "xlsx"],
            key="nouvel_export_kobo",
        )
        uploaded_questionnaire = st.file_uploader(
            "Questionnaire XLSForm de cette enquête (XLSX)",
            type=["xlsx"],
            key="questionnaire_nouvel_export",
        )
        uploaded_catalogue = st.file_uploader(
            "Catalogue de choix CSV (facultatif)",
            type=["csv"],
            key="catalogue_nouvel_export",
        )
        col_identifiant = st.text_input(
            "Nom technique de la colonne d'identifiant", value="code_jeton"
        )
        col_consentement = st.text_input(
            "Nom technique de la colonne de consentement", value="volont"
        )
        col_date = st.text_input(
            "Nom technique de la colonne de date d'enquête (facultatif)",
            value="date_enquete",
        )
        date_debut = st.text_input(
            "Date officielle de début (JJ-MM-AAAA)", placeholder="Ex. 01-04-2025"
        )
        date_fin = st.text_input(
            "Date officielle de fin (JJ-MM-AAAA)", placeholder="Ex. 30-04-2025"
        )
        if uploaded_file is not None and uploaded_questionnaire is not None and st.button(
            "Vérifier les fichiers avant nettoyage"
        ):
            st.session_state.pop("resultat_nettoyage", None)
            st.session_state.pop("import_nettoye", None)
            fichiers = {
                "file": (
                    uploaded_file.name,
                    uploaded_file.getvalue(),
                    uploaded_file.type,
                ),
                "questionnaire": (
                    uploaded_questionnaire.name,
                    uploaded_questionnaire.getvalue(),
                    uploaded_questionnaire.type,
                ),
            }
            if uploaded_catalogue is not None:
                fichiers["catalogue"] = (
                    uploaded_catalogue.name,
                    uploaded_catalogue.getvalue(),
                    uploaded_catalogue.type,
                )
            donnees_formulaire = {
                "colonne_identifiant": col_identifiant,
                "colonne_consentement": col_consentement,
                "colonne_date": col_date,
                "date_debut": date_debut,
                "date_fin": date_fin,
            }
            empreinte_fichiers = {
                cle: hashlib.sha256(contenu).hexdigest()
                for cle, (_, contenu, _) in fichiers.items()
            }
            with st.spinner("Vérification des fichiers et des colonnes..."):
                try:
                    res = requests.post(
                        f"{API_URL}/enquetes/previsualiser-nettoyage",
                        files=fichiers,
                        data=donnees_formulaire,
                        headers=headers,
                        timeout=300,
                    )
                    if res.status_code == 200:
                        st.session_state["previsualisation_nettoyage"] = {
                            "fichiers": fichiers,
                            "donnees": donnees_formulaire,
                            "bilan": res.json(),
                            "empreinte_fichiers": empreinte_fichiers,
                        }
                    else:
                        try:
                            detail = res.json().get("detail", res.text)
                        except Exception:
                            detail = res.text
                        st.session_state.pop("previsualisation_nettoyage", None)
                        st.error(f"Vérification impossible : {detail}")
                except Exception as e:
                    afficher_erreur_terrain(e, "la vérification des fichiers")

        previsualisation = st.session_state.get("previsualisation_nettoyage")
        if previsualisation:
            bilan = previsualisation["bilan"]
            fichiers_actuels = {
                "file": uploaded_file,
                "questionnaire": uploaded_questionnaire,
            }
            if uploaded_catalogue is not None:
                fichiers_actuels["catalogue"] = uploaded_catalogue
            empreinte_actuelle = {
                cle: hashlib.sha256(fichier.getvalue()).hexdigest()
                for cle, fichier in fichiers_actuels.items()
                if fichier is not None
            }
            previsualisation_a_jour = (
                empreinte_actuelle == previsualisation["empreinte_fichiers"]
                and {
                    "colonne_identifiant": col_identifiant,
                    "colonne_consentement": col_consentement,
                    "colonne_date": col_date,
                    "date_debut": date_debut,
                    "date_fin": date_fin,
                }
                == previsualisation["donnees"]
            )
            if not previsualisation_a_jour:
                st.warning(
                    "Les fichiers ou les paramètres ont changé. Relancez la vérification "
                    "avant de pouvoir traiter ces données."
                )
            st.subheader("Bilan avant traitement")
            st.write(
                f"Export : **{bilan['lignes_brutes']:,} lignes** et "
                f"**{bilan['colonnes_brutes']} colonnes**. Le XLSForm contient "
                f"**{bilan['questions_xlsform']} questions**, dont "
                f"**{bilan['questions_textuelles_libres']} en texte libre**."
            )
            if bilan["variables_absentes"]:
                with st.expander(
                    f"Questions du XLSForm absentes de l'export ({len(bilan['variables_absentes'])})"
                ):
                    st.write(", ".join(bilan["variables_absentes"]))
            if bilan["colonnes_inconnues"]:
                with st.expander(
                    f"Colonnes absentes du XLSForm ({len(bilan['colonnes_inconnues'])})"
                ):
                    st.write(", ".join(bilan["colonnes_inconnues"]))
            for avertissement in bilan["avertissements"]:
                st.warning(avertissement)
            if bilan["variables_sql_non_gerees"]:
                with st.expander(
                    f"Questions à ranger dans une rubrique SQL après le nettoyage "
                    f"({len(bilan['variables_sql_non_gerees'])})"
                ):
                    st.write(", ".join(bilan["variables_sql_non_gerees"]))

            confirmation = st.checkbox(
                "J'ai vérifié le bilan, le XLSForm et les avertissements."
            )
            if st.button(
                "Nettoyer l'export et préparer son rangement SQL",
                type="primary",
                disabled=not confirmation or not previsualisation_a_jour,
            ):
                with st.spinner("Nettoyage de l'export en cours..."):
                    try:
                        res = requests.post(
                            f"{API_URL}/enquetes/nettoyer-pour-import",
                            files=previsualisation["fichiers"],
                            data=previsualisation["donnees"],
                            headers=headers,
                            timeout=600,
                        )
                        if res.status_code == 200:
                            st.session_state["import_nettoye"] = {
                                **res.json(),
                                "empreinte_fichiers": previsualisation[
                                    "empreinte_fichiers"
                                ],
                                "donnees": previsualisation["donnees"],
                            }
                            st.rerun()
                        else:
                            try:
                                detail = res.json().get("detail", res.text)
                            except Exception:
                                detail = res.text
                            st.error(f"Nettoyage impossible : {detail}")
                    except Exception as e:
                        afficher_erreur_terrain(e, "le nettoyage")

        import_nettoye = st.session_state.get("import_nettoye")
        if import_nettoye:
            bilan_actuel = st.session_state.get("previsualisation_nettoyage")
            import_a_jour = (
                bilan_actuel is not None
                and bilan_actuel["empreinte_fichiers"]
                == import_nettoye["empreinte_fichiers"]
                and bilan_actuel["donnees"] == import_nettoye["donnees"]
                and previsualisation_a_jour
            )
            st.subheader("Nettoyage terminé")
            st.success(import_nettoye["message"])
            st.metric("Lignes nettoyées", import_nettoye["lignes_nettoyees"])
            st.caption(
                "Le fichier propre est conservé dans "
                f"`{import_nettoye['fichier_nettoye']}`. Le rapport console, le rapport "
                "M&E et les fichiers de capitalisation sont également enregistrés dans "
                "`outputs/`."
            )
            with st.expander("Rapport console du nettoyage"):
                if import_nettoye.get("rapport_console_tronque"):
                    st.warning(
                        "L'affichage est limité. Le rapport complet est enregistré "
                        "dans outputs/rapport_nettoyage_console.txt."
                    )
                st.code(
                    import_nettoye.get("rapport_console", ""), language="text"
                )
            with st.expander("Rapport d'exécution M&E"):
                st.markdown(import_nettoye.get("rapport_execution", ""))
            if import_nettoye["variables_sql_a_classer"]:
                st.info(
                    "Le nettoyage est terminé. Avant le chargement SQL, rangez chaque "
                    "nouvelle question dans la rubrique qui lui correspond. Une colonne "
                    "sera créée dans la table choisie."
                )
            elif import_a_jour:
                st.info(
                    "Toutes les questions correspondent déjà au schéma SQL. Vous pouvez "
                    "confirmer le chargement."
                )

            labels_tables = {
                "MENAGE": "Ménage",
                "STATUT_MENAGE": "Statut du ménage",
                "COMPOSITION_MENAGE": "Composition du ménage",
                "VULNERABILITE_SANTE": "Santé et handicap",
                "ECONOMIE_REVENU": "Économie et revenus",
                "SECURITE_ALIMENTAIRE": "Sécurité alimentaire (SECAL)",
                "BIENS_AME": "Biens AME",
                "WASH_EAU": "Eau, hygiène et assainissement (WASH)",
                "AGRICULTURE": "Agriculture",
                "PROTECTION": "Protection et déplacements",
            }
            affectations = {table: [] for table in labels_tables}
            choix_non_renseignes = []
            if import_a_jour:
                for variable in import_nettoye["variables_sql_a_classer"]:
                    choix = ["— Choisir une rubrique —", *labels_tables.values()]
                    selection = st.selectbox(
                        f"Dans quelle rubrique ranger « {variable} » ?",
                        choix,
                        key=f"rubrique_{import_nettoye['import_id']}_{variable}",
                    )
                    if selection == choix[0]:
                        choix_non_renseignes.append(variable)
                    else:
                        table = next(
                            code
                            for code, label in labels_tables.items()
                            if label == selection
                        )
                        affectations[table].append(variable)

                confirmation_sql = st.checkbox(
                    "Je confirme les rubriques choisies et le chargement des données.",
                    disabled=not import_a_jour or bool(choix_non_renseignes),
                )
                if st.button(
                    "Charger les données dans SQL",
                    type="primary",
                    disabled=(
                        not import_a_jour
                        or bool(choix_non_renseignes)
                        or not confirmation_sql
                    ),
                ):
                    with st.spinner(
                        "Chargement dans les tables SQL et mise à jour du CSV..."
                    ):
                        try:
                            res = requests.post(
                                f"{API_URL}/enquetes/ingrer-import-prepare",
                                json={
                                    "import_id": import_nettoye["import_id"],
                                    "variables_par_table": {
                                        table: variables
                                        for table, variables in affectations.items()
                                        if variables
                                    },
                                },
                                headers=headers,
                                timeout=600,
                            )
                            if res.status_code == 200:
                                st.session_state["resultat_nettoyage"] = res.json()
                                st.session_state.pop("import_nettoye", None)
                                st.session_state.pop(
                                    "previsualisation_nettoyage", None
                                )
                                st.rerun()
                            else:
                                try:
                                    detail = res.json().get("detail", res.text)
                                except Exception:
                                    detail = res.text
                                st.error(f"Chargement SQL impossible : {detail}")
                        except Exception as e:
                            afficher_erreur_terrain(e, "le chargement SQL")
            if choix_non_renseignes:
                st.warning(
                    "Choisissez une rubrique pour chaque question avant de charger "
                    "dans SQL."
                )

        resultat_nettoyage = st.session_state.get("resultat_nettoyage")
        if resultat_nettoyage:
            st.success(resultat_nettoyage["message"])
            st.metric("Lignes nettoyées et intégrées", resultat_nettoyage["lignes_traitees"])
            st.metric(
                "Ménages consentants",
                resultat_nettoyage["lignes_consentantes"],
            )
            st.caption(
                "Lignes enregistrées par table : "
                + ", ".join(
                    f"{table} : {nombre}"
                    for table, nombre in resultat_nettoyage["lignes_par_table"].items()
                )
            )
            with st.expander("Rapport console du nettoyage"):
                if resultat_nettoyage.get("rapport_console_tronque"):
                    st.warning(
                        "L'affichage est limité. Le rapport complet est dans "
                        "outputs/rapport_nettoyage_console.txt."
                    )
                st.code(resultat_nettoyage.get("rapport_console", ""), language="text")
            with st.expander("Rapport d'exécution M&E"):
                st.markdown(resultat_nettoyage.get("rapport_execution", ""))
            st.caption(
                "Fichiers enregistrés dans outputs/ : "
                + ", ".join(
                    os.path.basename(chemin)
                    for chemin in resultat_nettoyage.get("fichiers_generes", [])
                )
            )
    else:
        st.caption(
            "Une archive de suppression contient déjà les données nettoyées. "
            "Elle est restaurée dans SQLite et le CSV propre sans rejouer le pipeline."
        )
        archives = []
        chargement_archives_ok = False
        try:
            reponse_archives = requests.get(
                f"{API_URL}/enquetes/archives-suppressions",
                headers=headers,
                timeout=10,
            )
            reponse_archives.raise_for_status()
            archives = reponse_archives.json().get("archives", [])
            chargement_archives_ok = True
        except Exception as e:
            afficher_erreur_terrain(e, "le chargement des archives")

        if archives:
            archives_par_nom = {
                archive["nom_fichier"]: archive for archive in archives
            }
            nom_archive = st.selectbox(
                "Enquête supprimée à restaurer :",
                options=list(archives_par_nom),
                format_func=lambda nom: (
                    f"ID {archives_par_nom[nom]['id_menage']} — "
                    f"jeton {archives_par_nom[nom]['code_jeton']} — {nom}"
                ),
            )
            confirmation_restauration = st.checkbox(
                "Je confirme la réintégration de cette enquête dans la base."
            )
            if st.button(
                "Réhabiliter l'enquête",
                type="primary",
                disabled=not confirmation_restauration,
            ):
                with st.spinner("Restauration de l'enquête archivée dans SQL et le CSV..."):
                    try:
                        res = requests.post(
                            f"{API_URL}/enquetes/restaurer-archive",
                            json={"nom_fichier": nom_archive},
                            headers=headers,
                            timeout=60,
                        )
                        if res.status_code == 200:
                            resultat = res.json()
                            st.success(
                                f"✅ Réhabilitation confirmée : {resultat.get('message')}"
                            )
                            if resultat.get("archive_supprimee"):
                                st.info("L'archive a été retirée du cache.")
                            elif resultat.get("avertissement"):
                                st.warning(resultat["avertissement"])
                            st.info(
                                "La réhabilitation est journalisée dans "
                                "`outputs/rapport_execution_m_e.md`."
                            )
                        else:
                            try:
                                detail = res.json().get("detail", res.text)
                            except Exception:
                                detail = res.text
                            st.error(f"❌ Erreur de réhabilitation : {detail}")
                    except Exception as e:
                        afficher_erreur_terrain(e, "la réhabilitation de l'enquête")
        elif chargement_archives_ok:
            st.info("Aucune archive de suppression n'est disponible.")

# =========================================================
# 2. LISTER LES ENQUÊTES
# =========================================================
elif menu == "📋 Lister les enquêtes (CSV propre)":
    st.header("📋 Liste des enquêtes validées")
    limite = st.slider("Nombre de lignes", 1, 200, 50)

    if st.button("Charger les données propres"):
        with st.spinner("Chargement..."):
            try:
                res = requests.get(f"{API_URL}/enquetes?limite={limite}", headers=headers)
                if res.status_code == 200:
                    data = res.json().get("donnees", [])
                    if data:
                        df = pd.DataFrame(data)
                        df = df.rename(columns=lambda c: str(c).replace("_", " ").capitalize())
                        st.success(f"{len(df)} enquêtes chargées.")
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("Base vide.")
                else:
                    try:
                        err_detail = res.json().get("detail", res.text)
                    except Exception:
                        err_detail = res.text
                    st.error(f"❌ Erreur lors du chargement : {err_detail}")
            except Exception as e:
                afficher_erreur_terrain(e, "le chargement des enquêtes")

# =========================================================
# 3. CONSULTER PAR CODE JETON (AVEC LES VRAIS LABELS DE L'API)
# =========================================================
elif menu == "🔍 Consulter par Code Jeton":
    st.header("🔍 Consultation par Code Jeton")
    
    with st.form("form_consultation_jeton"):
        jeton = st.text_input("Code Jeton de l'enquête :", placeholder="Saisissez le jeton...")
        submit_consult = st.form_submit_button("Rechercher le profil")

    if submit_consult and jeton:
        with st.spinner("Recherche..."):
            try:
                res = requests.get(f"{API_URL}/menages/jeton/{jeton}/profil", headers=headers)
                if res.status_code == 200:
                    res_json = res.json()
                    profil = res_json.get("profil_complet", {})
                    labels_mapping = res_json.get("labels", {})
                    
                    st.success(f"Profil trouvé pour le jeton : {jeton}")
                    
                    for table, contenu in profil.items():
                        with st.expander(f"📋 Module : {table.upper()}", expanded=True):
                            if isinstance(contenu, list):
                                df_sat = pd.DataFrame(contenu)
                                df_sat = df_sat.rename(columns=lambda c: labels_mapping.get(str(c).strip(), str(c).replace("_", " ").capitalize()))
                                st.dataframe(df_sat, use_container_width=True)
                            elif isinstance(contenu, dict):
                                for k, v in contenu.items():
                                    libelle_affiche = labels_mapping.get(str(k).strip(), str(k).replace("_", " ").capitalize())
                                    st.markdown(f"- **{libelle_affiche}** : `{v}`")
                elif res.status_code == 404:
                    st.warning("⚠️ Aucun ménage ne correspond à ce code jeton.")
                else:
                    st.error(f"❌ Erreur de récupération du profil.")
            except Exception as e:
                afficher_erreur_terrain(e, "la consultation du profil")

# =========================================================
# 5. MODIFICATION NON TECHNIQUE SÉCURISÉE (FORMULAIRE INTUITIF)
# =========================================================
elif menu == "✏️ Modifier une enquête (Non technique)":
    st.header("✏️ Modification ciblée d'un champ")
    st.info(
        "Choix de la colonne et du type selon le questionnaire original - "
        "les recommandations du nettoyage ne sont pas prises en compte à ce niveau"
    )
    jeton_mod = st.text_input(
        "Code Jeton ou ID du ménage à modifier :", placeholder="Ex: 12345"
    )
    champs_modifiables = []
    chargement_champs_ok = False
    try:
        reponse_champs = requests.get(
            f"{API_URL}/enquetes/champs-modifiables",
            headers=headers,
            timeout=10,
        )
        reponse_champs.raise_for_status()
        champs_modifiables = reponse_champs.json().get("champs", [])
        chargement_champs_ok = True
    except Exception as e:
        afficher_erreur_terrain(e, "le chargement des champs modifiables")

    if champs_modifiables:
        champ_par_nom = {champ["name"]: champ for champ in champs_modifiables}
        colonne_cible = st.selectbox(
            "Sélectionner la question à modifier (nom XLSForm) :",
            options=list(champ_par_nom),
            format_func=lambda nom: f"{nom} — {champ_par_nom[nom]['type']}",
        )
        champ = champ_par_nom[colonne_cible]
        type_question = champ["type"]
        choix = champ.get("choices", [])
        st.markdown(f"*Type détecté depuis le XLSForm :* `{type_question}`")

        type_base = type_question.split(maxsplit=1)[0]
        valeur_valide = True
        if type_base == "select_one":
            if choix:
                nouvelle_valeur = st.selectbox(
                    "Nouvelle réponse :", options=choix, key=f"modification_{colonne_cible}"
                )
            else:
                st.error("Aucun choix correspondant à cette liste n'a été trouvé dans l'onglet choices.")
                nouvelle_valeur = None
                valeur_valide = False
        elif type_base == "select_multiple":
            if choix:
                nouvelle_valeur = st.multiselect(
                    "Nouvelles réponses :", options=choix, key=f"modification_{colonne_cible}"
                )
            else:
                st.error("Aucun choix correspondant à cette liste n'a été trouvé dans l'onglet choices.")
                nouvelle_valeur = None
                valeur_valide = False
        elif type_base == "integer":
            nouvelle_valeur = st.number_input(
                "Nouvelle réponse (entier) :",
                step=1,
                value=0,
                format="%d",
                key=f"modification_{colonne_cible}",
            )
        elif type_base == "decimal":
            nouvelle_valeur = st.number_input(
                "Nouvelle réponse (décimale) :",
                value=0.0,
                key=f"modification_{colonne_cible}",
            )
        elif type_base == "date":
            nouvelle_valeur = st.date_input(
                "Nouvelle réponse (date) :",
                value=None,
                format="DD/MM/YYYY",
                key=f"modification_{colonne_cible}",
            )
            valeur_valide = nouvelle_valeur is not None
        elif type_base in {"start", "end", "datetime"}:
            nouvelle_valeur = st.text_input(
                "Nouvelle réponse (date et heure ISO 8601) :",
                placeholder="2026-10-07T14:30:00",
                key=f"modification_{colonne_cible}",
            )
            valeur_valide = bool(nouvelle_valeur.strip())
        elif type_base == "time":
            nouvelle_valeur = st.text_input(
                "Nouvelle réponse (heure HH:MM ou HH:MM:SS) :",
                placeholder="14:30",
                key=f"modification_{colonne_cible}",
            )
            valeur_valide = bool(nouvelle_valeur.strip())
        else:
            nouvelle_valeur = st.text_input(
                "Nouvelle réponse :", key=f"modification_{colonne_cible}"
            )
            valeur_valide = bool(nouvelle_valeur.strip())

        confirmation = st.checkbox(
            "⚠️ Êtes-vous certain(e) de vouloir modifier cette donnée ? "
            "(L'action sera journalisée)"
        )
        submit_mod = st.button(
            "Valider et appliquer la modification",
            type="primary",
            disabled=not valeur_valide,
        )
    else:
        colonne_cible = ""
        nouvelle_valeur = None
        confirmation = False
        submit_mod = False
        if chargement_champs_ok:
            st.info("Aucun champ du questionnaire n'est actuellement modifiable dans la base.")

    if submit_mod:
        if not jeton_mod or not colonne_cible:
            st.warning("⚠️ Veuillez renseigner le code jeton et le nom de la colonne à modifier.")
        elif not confirmation:
            st.warning("⚠️ Veuillez cocher la case de confirmation pour autoriser la modification.")
        else:
            with st.spinner("Application de la modification et écriture du rapport d'exécution..."):
                try:
                    if hasattr(nouvelle_valeur, "isoformat"):
                        valeur_api = nouvelle_valeur.isoformat()
                    elif isinstance(nouvelle_valeur, list):
                        valeur_api = nouvelle_valeur
                    else:
                        valeur_api = str(nouvelle_valeur)
                    payload = {"colonne": colonne_cible, "valeur": valeur_api}
                    res = requests.put(
                        f"{API_URL}/enquetes/modifier-champ/{jeton_mod}",
                        json=payload,
                        headers=headers,
                        timeout=30,
                    )
                    
                    if res.status_code == 200:
                        r = res.json()
                        statut = r.get("statut")
                        message = r.get("message")
                        
                        if statut == "info":
                            st.info(f"ℹ️ {message} (Valeur enregistrée : `{r.get('valeur_appliquee')}`)")
                        else:
                            st.success(f"✅ {message} (Valeur enregistrée : `{r.get('valeur_appliquee')}`)")
                            st.info("📝 Une ligne a été ajoutée au rapport d'exécution et au fichier d'apprentissage IA.")
                    else:
                        try:
                            err_detail = res.json().get("detail", "Erreur inconnue")
                        except Exception:
                            err_detail = "Erreur de communication avec le serveur."
                        st.error(f"❌ **Action impossible :** {err_detail}")
                except Exception as e:
                    afficher_erreur_terrain(e, "la modification de la donnée")

# =========================================================
# 6. SUPPRESSION
# =========================================================
elif menu == "🗑️ Supprimer un ménage":
    st.header("🗑️ Suppression en cascade")
    
    with st.form("form_suppression"):
        id_supp = st.text_input("Code Jeton ou ID du ménage à supprimer :")
        conf_supp = st.checkbox("Je confirme la suppression définitive de toutes les tables liées")
        submit_supp = st.form_submit_button("Supprimer définitivement", type="primary")

    if submit_supp:
        if not id_supp:
            st.warning("⚠️ Veuillez renseigner l'identifiant du ménage à supprimer.")
        elif not conf_supp:
            st.warning("⚠️ Veuillez cocher la case de confirmation de suppression.")
        else:
            try:
                with st.spinner(
                    "Suppression en cours : sauvegarde du ménage, "
                    "retrait de la base SQL et mise à jour du CSV..."
                ):
                    res = requests.delete(
                        f"{API_URL}/enquetes/supprimer/{id_supp}",
                        headers=headers,
                        timeout=300,
                    )
                if res.status_code == 200:
                    resultat = res.json()
                    st.success("✅ Suppression confirmée et effectuée.")
                    st.write(resultat.get("message"))
                    if resultat.get("archive_csv"):
                        st.caption(
                            f"Copie de sauvegarde créée : `{resultat['archive_csv']}`"
                        )
                    if "total_menages_restants" in resultat:
                        st.metric(
                            "Ménages restants dans la base",
                            resultat["total_menages_restants"],
                        )
                    st.info(
                        "Le ménage a été retiré de la base et du CSV propre. "
                        "L'action figure dans le rapport d'exécution."
                    )
                else:
                    try:
                        err_detail = res.json().get("detail", res.text)
                    except Exception:
                        err_detail = res.text
                    if isinstance(err_detail, dict):
                        st.error(f"❌ {err_detail.get('message', 'Suppression impossible.')}")
                        identifiants = err_detail.get("identifiants_menage", [])
                        if identifiants:
                            st.warning(
                                "Plusieurs ménages portent ce jeton. "
                                "Utilisez l’un de ces identifiants techniques dans le formulaire : "
                                + ", ".join(str(identifiant) for identifiant in identifiants)
                            )
                    else:
                        st.error(f"❌ Erreur lors de la suppression : {err_detail}")
            except Exception as e:
                afficher_erreur_terrain(e, "la suppression du ménage")

# =========================================================
# 7. ANALYSE EXPLORATOIRE (PARTIE 3)
# =========================================================
elif menu == "📊 Analyser les données":
    import streamlit.components.v1 as components

    st.header("📊 Analyser les données")
    st.caption(
        "Génère un rapport d'analyse unique à partir de la base actuelle : table principale, "
        "tables secondaires, puis liens entre scores et caractéristiques des ménages. "
        "Le calcul peut prendre plusieurs minutes."
    )
    identifiant_profil = ""
    xlsform_profil = None
    with st.expander("Autre questionnaire (variables renommées) — réservé au responsable technique"):
        st.caption(
            "Choisissez le profil de correspondance validé et joignez le questionnaire XLSForm correspondant. "
            "Laissez vide pour le questionnaire habituel."
        )
        try:
            profils = requests.get(f"{API_URL}/analyse/profils", headers=headers, timeout=15).json().get("profils", [])
        except Exception:
            profils = []
        identifiant_profil = st.selectbox("Profil", ["(questionnaire habituel)"] + profils)
        if identifiant_profil.startswith("("):
            identifiant_profil = ""
        else:
            xlsform_profil = st.file_uploader("Questionnaire XLSForm du profil (XLSX)", type=["xlsx"], key="xlsform_analyse")

    col_btn_eda, col_btn_dash = st.columns(2)
    with col_btn_eda:
        btn_lancer_eda = st.button(
            "⚡ Rapport statistique approfondi (EDA)",
            type="secondary",
            use_container_width=True,
            help="Génère le rapport statistique bivarié et multivarié détaillé (matrices de corrélation, Cramer, etc.).",
        )
    with col_btn_dash:
        btn_lancer_dash = st.button(
            "🖥️ Dashboard interactif (Power BI / Tableau / SIG)",
            type="primary",
            use_container_width=True,
            help="Génère le tableau de bord opérationnel avec carte géographique interactive, 4 KPI clés et export dénormalisé.",
        )

    if btn_lancer_eda:
        st.session_state["vue_analyse"] = "eda"
        st.session_state.pop("rapports_analyse", None)
        if identifiant_profil and xlsform_profil is None:
            st.warning("⚠️ Joignez le questionnaire XLSForm du profil choisi.")
        else:
            fichiers = {"xlsform_profil": (xlsform_profil.name, xlsform_profil.getvalue())} if xlsform_profil else None
            with st.spinner("⏳ Analyse en cours : cela peut prendre plusieurs minutes. Ne fermez pas cette page, le rapport s’affichera ici dès qu’il sera prêt."):
                try:
                    res = requests.post(
                        f"{API_URL}/analyse/lancer",
                        data={"identifiant_profil": identifiant_profil},
                        files=fichiers,
                        headers=headers,
                        timeout=900,
                    )
                    if res.status_code == 200:
                        st.session_state["rapports_analyse"] = res.json()["rapports"]
                        st.success("✅ Analyse terminée. Le rapport est aussi enregistré dans `outputs/eda_rapport.html`.")
                    else:
                        try:
                            detail = res.json().get("detail", res.text)
                        except Exception:
                            detail = res.text
                        st.error(f"❌ Analyse impossible : {detail}")
                except Exception as e:
                    afficher_erreur_terrain(e, "l'analyse des données")

    if btn_lancer_dash:
        st.session_state["vue_analyse"] = "dashboard"
        with st.spinner("⏳ Préparation des données du Dashboard, inférence IA et cartographie en cours..."):
            try:
                res = requests.post(f"{API_URL}/dashboard/generer", headers=headers, timeout=120)
                if res.status_code == 200:
                    st.success("✅ Dashboard interactif et jeu de données Power BI / Tableau prêts !")
                else:
                    # Fallback direct en local si l'API est en cours de redémarrage
                    from src.partie5_dashboard import preparer_donnees_dashboard, generer_dashboard_html
                    df_dash = preparer_donnees_dashboard()
                    generer_dashboard_html(df_dash)
                    st.success("✅ Dashboard interactif généré avec succès en mode local !")
            except Exception as e:
                try:
                    from src.partie5_dashboard import preparer_donnees_dashboard, generer_dashboard_html
                    df_dash = preparer_donnees_dashboard()
                    generer_dashboard_html(df_dash)
                    st.success("✅ Dashboard interactif généré avec succès (mode direct local) !")
                except Exception as err2:
                    afficher_erreur_terrain(err2, "la génération du dashboard interactif")

    # Détection de la vue à afficher
    vue_actuelle = st.session_state.get("vue_analyse", "dashboard")
    chemin_csv_dash = Path("outputs/donnees_dashboard.csv")
    chemin_html_dash = Path("outputs/dashboard_interactif.html")

    # Si le rapport EDA est demandé et prêt
    if vue_actuelle == "eda" and st.session_state.get("rapports_analyse"):
        rapports_analyse = st.session_state.get("rapports_analyse")
        contenu = rapports_analyse["rapport"]
        st.download_button(
            "⬇️ Télécharger le rapport statistique (HTML)",
            data=contenu.encode("utf-8"),
            file_name="eda_rapport.html",
            mime="text/html",
        )
        components.html(contenu, height=900, scrolling=True)

    # Affichage du Dashboard interactif
    elif chemin_csv_dash.exists() and chemin_html_dash.exists():
        st.markdown("---")
        components.html(chemin_html_dash.read_text(encoding="utf-8"), height=1180, scrolling=True)

        chemin_pbix = next(iter(sorted(Path("outputs").glob("*.pbix"))), None)
        with st.expander("📐 Visualiser le modèle Power BI", expanded=False):
            if chemin_pbix is not None:
                st.write(
                    "Ce modèle s'ouvre avec **Power BI Desktop** (version hors ligne). Après ouverture, "
                    "cliquez sur **Actualiser** pour charger les données de l'enquête active."
                )
                apercu_pbi = Path("outputs") / "apercu_template_powerbi.png"
                if apercu_pbi.exists():
                    st.image(str(apercu_pbi), caption="Aperçu du modèle Power BI", use_container_width=True)
                st.download_button(
                    "⬇️ Télécharger le modèle Power BI (.pbix)",
                    data=chemin_pbix.read_bytes(),
                    file_name=chemin_pbix.name,
                    mime="application/octet-stream",
                    key="dl_pbix_analyse",
                )
            else:
                st.info("Aucun modèle Power BI (.pbix) n'est présent dans le dossier outputs.")

        with st.expander("📥 Export des données et modèle Power BI / Tableau", expanded=False):
            st.write(
                "Le jeu de données plat (une ligne par ménage) alimente directement **Power BI Desktop** ou **Tableau Desktop** "
                "pour reproduire ce tableau de bord."
            )
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    "⬇️ Jeu de données (CSV)",
                    data=chemin_csv_dash.read_bytes(),
                    file_name="donnees_dashboard_humanitaire.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with col_dl2:
                st.download_button(
                    "⬇️ Tableau de bord autonome (HTML)",
                    data=chemin_html_dash.read_bytes(),
                    file_name="dashboard_interactif.html",
                    mime="text/html",
                    use_container_width=True,
                )
            st.markdown(
                "**Mesures à créer dans Power BI** (segment : `statut_menage`) :\n"
                "- Vulnérabilité aiguë : `AVERAGE(donnees_dashboard[vulnerabilite_aigue_reelle]) * 100`\n"
                "- Pré-ciblage IA : `AVERAGE(donnees_dashboard[prediction_classe_ml]) * 100`\n"
                "- Taille moyenne du ménage : `AVERAGE(donnees_dashboard[taille_menage])`\n"
                "- Personnes à charge : `AVERAGE(donnees_dashboard[ratio_personnes_charge]) * 100`\n\n"
                "Carte : `latitude` / `longitude`, couleur = vulnérabilité aiguë. Guide complet : `docs/05. notice_user_dashboard.md`."
            )

    else:
        st.info("💡 Cliquez sur **« 🖥️ Dashboard interactif »** pour générer les données enrichies, la carte SIG et les 4 KPI clés.")



# =========================================================
# 8. CIBLAGE ET MACHINE LEARNING (PARTIE 4)
# =========================================================
elif menu == "🤖 Ciblage & Machine Learning":
    st.header("🤖 Modélisation Prédictive & Ciblage des Ménages (JIAF 2.0)")
    st.caption(
        "Ce module répond à la problématique humanitaire : « Les caractéristiques socio-démographiques "
        "d'un ménage suffisent-elles à anticiper son niveau de vulnérabilité multisectorielle aiguë sans dérouler "
        "l'intégralité d'un questionnaire lourd ? »"
    )

    onglet_mode = st.radio(
        "Sélectionnez le parcours opérationnel :",
        ("🎯 Inférence & Ciblage Terrain (Agents)", "⚙️ Entraînement MLOps (Responsable Technique)"),
        horizontal=True,
    )

    # ---------------------------------------------------------
    # PARCOURS 1 : INFÉRENCE & CIBLAGE TERRAIN
    # ---------------------------------------------------------
    if onglet_mode == "🎯 Inférence & Ciblage Terrain (Agents)":
        st.subheader("🎯 Pré-ciblage instantané des ménages prioritaires")
        st.info(
            "💡 **Mode d'emploi terrain :**\n"
            "- Ce mode utilise le modèle de Machine Learning déjà validé et calibré par l'équipe technique.\n"
            "- Il estime instantanément la probabilité de vulnérabilité aiguë pour chaque ménage enregistré en base.\n"
            "- Les ménages dépassant le seuil d'intervention sont isolés et téléchargeables en CSV pour organiser les distributions."
        )

        col_seuil, col_btn = st.columns([2, 1])
        with col_seuil:
            seuil_choisi = st.slider(
                "Seuil d'intervention (probabilité minimale pour être prioritaire)",
                min_value=0.30,
                max_value=0.80,
                value=0.50,
                step=0.05,
                help="À 50%, tout ménage ayant au moins 1 chance sur 2 d'être en crise aiguë est priorisé.",
            )
        with col_btn:
            st.write("")
            st.write("")
            lancer_pred = st.button("🚀 Calculer les priorités terrain", type="primary")

        if lancer_pred:
            with st.spinner("⏳ Calcul des probabilités de vulnérabilité en cours..."):
                try:
                    res = requests.post(
                        f"{API_URL}/ml/predire",
                        data={"seuil": seuil_choisi},
                        headers=headers,
                        timeout=120,
                    )
                    if res.status_code == 200:
                        st.session_state["resultats_ml_inference"] = res.json()
                        st.success("✅ Calcul des priorités terminé avec succès !")
                    else:
                        try:
                            err = res.json().get("detail", res.text)
                        except Exception:
                            err = res.text
                        st.error(f"❌ Erreur lors de la prédiction : {err}")
                except Exception as e:
                    afficher_erreur_terrain(e, "le calcul des priorités ML")

        res_ml = st.session_state.get("resultats_ml_inference")
        if res_ml:
            st.markdown("---")
            # Contexte géographique et rappel de transposabilité
            ctx_inf = res_ml.get("contexte_operationnel", {})
            st.info(
                f"📍 **Contexte opérationnel du modèle :** Projet `{ctx_inf.get('projet', 'Enquete_test_RDC_2020')}` | "
                f"Zone de référence : `{ctx_inf.get('pays', 'RDC')}` ({ctx_inf.get('region', 'Province de l’Équateur')}) | "
                f"Période : `{ctx_inf.get('annee_collecte', '2020-2021')}`."
            )
            st.warning(
                f"⚠️ **Attention à la transposabilité :**\n"
                f"{ctx_inf.get('avertissement_transposabilite', 'Ce modèle est calibré spécifiquement sur le profil socio-démographique de la zone d’enquête initiale. Tout déploiement sur une autre crise (ex: Yémen, Sahel) exige un réétalonnage préalable par le staff technique.')}"
            )

            # 1. Cartouches d'indicateurs clés
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Ménages évalués", f"{res_ml['total_menages_evalues']:,}")
            m2.metric("Ménages prioritaires", f"{res_ml['total_menages_prioritaires']:,}")
            m3.metric("Taux de priorité", f"{res_ml['taux_priorite_pct']}%")
            m4.metric("Modèle actif", res_ml["modele_utilise"])

            # 2. Performance du modèle actuellement utilisé
            with st.expander("📈 Performances certifiées du modèle en service", expanded=True):
                perf = res_ml.get("performances_modele", {})
                metriques = perf.get("metriques_test", {})
                if metriques:
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Rappel (Recall)", f"{metriques.get('recall', 0)*100:.1f}%", help="Proportion de ménages en crise réelle détectés (vital en humanitaire).")
                    c2.metric("F2-Score", f"{metriques.get('f2_score', 0):.3f}", help="Score pondéré donnant 2x plus d'importance au Rappel.")
                    c3.metric("ROC-AUC", f"{metriques.get('roc_auc', 0):.3f}", help="Capacité globale à distinguer les ménages vulnérables des non-vulnérables.")
                    c4.metric("Précision", f"{metriques.get('precision', 0)*100:.1f}%", help="Proportion de vrais vulnérables parmi les ménages prédits prioritaires.")
                    c5.metric("Accuracy", f"{metriques.get('accuracy', 0)*100:.1f}%")

                st.caption(
                    f"**Hyperparamètres optimisés par GridSearch :** `{perf.get('meilleurs_hyperparametres', {})}` | "
                    f"Rappel moyen en validation croisée : `{perf.get('rappel_cv', 0)*100:.1f}%`"
                )

            # 3. Limites techniques et avertissements éthiques
            st.warning("⚠️ **Limites techniques et cadre méthodologique :**\n" + res_ml.get("limites_techniques", ""))
            with st.expander("🛡️ Règles humanitaires cardinales (Do No Harm & Recours)"):
                for avert in res_ml.get("avertissements_ethiques", []):
                    st.write(f"- {avert}")

            # 4. Données de prédiction et export CSV
            st.subheader("📋 Liste des ménages prioritaires pour la distribution")
            prio_data = res_ml.get("menages_prioritaires", [])
            if prio_data:
                df_prio_disp = pd.DataFrame(prio_data)
                csv_bytes = df_prio_disp.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "⬇️ Télécharger la liste des ménages prioritaires (CSV)",
                    data=csv_bytes,
                    file_name="menages_prioritaires_assistance.csv",
                    mime="text/csv",
                    type="primary",
                )
                st.dataframe(df_prio_disp.head(100), use_container_width=True)
                if len(df_prio_disp) > 100:
                    st.caption(f"Affichage limité aux 100 premiers ménages. Le fichier CSV complet contient les {len(df_prio_disp):,} ménages.")
            else:
                st.info("Aucun ménage n'atteint le seuil de priorité sélectionné.")

            # 5. Module d'explicabilité locale SHAP
            st.markdown("---")
            st.subheader("🔍 Audit transparent d'un ménage (Explicabilité SHAP)")
            st.caption("Permet d'expliquer au comité communautaire pourquoi un ménage spécifique a été priorisé ou non.")
            id_audit = st.text_input("Identifiant du ménage à auditer (ex: MENAGE_1, 21703)", value="")
            if st.button("Auditer ce ménage avec SHAP") and id_audit:
                with st.spinner(f"Calcul des valeurs de Shapley pour {id_audit}..."):
                    try:
                        res_shap = requests.get(
                            f"{API_URL}/ml/expliquer-menage/{id_audit.strip()}",
                            headers=headers,
                            timeout=30,
                        )
                        if res_shap.status_code == 200:
                            audit = res_shap.json()["audit_shap"]
                            st.write(f"**Probabilité estimée pour {id_audit} :** `{audit['probabilite_calculee']*100:.1f}%` (Valeur de référence moyenne : `{audit['valeur_de_base_modele']*100:.1f}%`)")

                            col_agg, col_prot = st.columns(2)
                            with col_agg:
                                st.markdown("🔴 **Facteurs aggravant la vulnérabilité (Tirent vers la priorité) :**")
                                for fac in audit.get("facteurs_aggravants_vulnerabilite", []):
                                    st.write(f"- `{fac['variable']}` : **+{fac['impact_shap']*100:.2f}%**")
                            with col_prot:
                                st.markdown("🔵 **Facteurs de protection (Tirent vers l'autonomie) :**")
                                for fac in audit.get("facteurs_protecteurs_autonomie", []):
                                    st.write(f"- `{fac['variable']}` : **{fac['impact_shap']*100:.2f}%**")
                        else:
                            try:
                                err_s = res_shap.json().get("detail", res_shap.text)
                            except Exception:
                                err_s = res_shap.text
                            st.error(f"Audit impossible : {err_s}")
                    except Exception as e_s:
                        afficher_erreur_terrain(e_s, "l'audit SHAP")

    # ---------------------------------------------------------
    # PARCOURS 2 : ENTRAÎNEMENT MLOPS (RESPONSABLE TECHNIQUE)
    # ---------------------------------------------------------
    else:
        st.subheader("⚙️ Réentraînement et optimisation des modèles (MLOps)")

        if os.environ.get("M_E_MODE_NON_TECHNIQUE") == "1":
            st.error("🚫 **Accès restreint :** Le réentraînement des modèles d'IA est désactivé sur ce terminal configuré pour les agents terrain.")
            st.info("Pour consulter les performances du modèle actuellement déployé, basculez sur l'onglet **Inférence & Ciblage Terrain**.")
        else:
            st.warning(
                "🔒 **Espace d'administration réservé au Responsable Technique / Data Scientist :**\n"
                "- Le réentraînement recalcule la cible multisectorielle JIAF 2.0 et compare la Régression Logistique et la Forêt Aléatoire.\n"
                "- Cette opération mobilise des ressources de calcul importantes et modifie le modèle en production."
            )

            col_secu1, col_secu2 = st.columns(2)
            with col_secu1:
                mdp_admin = st.text_input(
                    "Mot de passe administrateur / Clé API technique :",
                    type="password",
                    help="Saisissez la clé API d'administration pour déverrouiller l'action de réentraînement.",
                )
            with col_secu2:
                confirmer_action = st.checkbox(
                    "Je confirme vouloir remplacer le modèle actuellement en production",
                    value=False,
                )

            mode_rapide = st.checkbox(
                "Mode calibrage rapide (grille réduite de test)",
                value=True,
                help="Décochez pour lancer la grille exhaustive (peut durer plusieurs minutes).",
            )

            bouton_verrouille = not (confirmer_action and mdp_admin == API_KEY_ATTENDUE)
            if bouton_verrouille:
                st.caption("🔒 *Le bouton de réentraînement est verrouillé tant que le mot de passe administrateur n'est pas validé et la case de confirmation cochée.*")

            if st.button(
                "⚡ Lancer le réentraînement complet des modèles",
                type="primary",
                disabled=bouton_verrouille,
            ):
                with st.spinner("⏳ Entraînement et validation croisée en cours..."):
                    try:
                        res_train = requests.post(
                            f"{API_URL}/ml/entrainer",
                            data={"rapide": mode_rapide},
                            headers=headers,
                            timeout=900,
                        )
                        if res_train.status_code == 200:
                            st.session_state["rapport_ml_entrainement"] = res_train.json()["rapport"]
                            st.session_state.pop("resultats_ml_inference", None)
                            st.success("✅ Modèles réentraînés et sauvegardés dans `outputs/ml/modele_vulnerabilite.joblib` !")
                        else:
                            try:
                                err_t = res_train.json().get("detail", res_train.text)
                            except Exception:
                                err_t = res_train.text
                            st.error(f"❌ Échec de l'entraînement : {err_t}")
                    except Exception as e_t:
                        afficher_erreur_terrain(e_t, "l'entraînement des modèles")

        rap_train = st.session_state.get("rapport_ml_entrainement")
        if not rap_train:
            # Essai de récupération du rapport existant
            try:
                res_exist = requests.get(f"{API_URL}/ml/rapport", headers=headers, timeout=15)
                if res_exist.status_code == 200:
                    rap_train = res_exist.json().get("rapport")
            except Exception:
                pass

        if rap_train:
            st.markdown("---")
            # Contexte géographique et avertissement de transposabilité
            ctx_op = rap_train.get("contexte_operationnel", {})
            st.info(
                f"📍 **Contexte opérationnel de l'entraînement :** Enquête `{ctx_op.get('projet', 'Enquete_test_RDC_2020')}` | "
                f"Zone : `{ctx_op.get('pays', 'RDC')}` ({ctx_op.get('region', 'Province de l’Équateur')}) | "
                f"Période : `{ctx_op.get('annee_collecte', '2020-2021')}`."
            )
            st.warning(
                f"⚠️ **Avertissement de transposabilité géographique :**\n"
                f"{ctx_op.get('avertissement_transposabilite', 'Ce modèle est calibré spécifiquement sur le profil socio-démographique de la zone d’enquête initiale. Tout déploiement sur une autre crise (ex: Yémen, Sahel) exige un réétalonnage préalable par le staff technique.')}"
            )

            st.write(f"📅 **Dernier entraînement validé :** {rap_train.get('date_entrainement')}")
            st.write(f"🏆 **Modèle retenu :** `{rap_train.get('modele_retenu')}`")
            st.info(f"**Justification métier :** {rap_train.get('justification_selection')}")

            st.subheader("📊 Tableau comparatif des modèles")
            comp_data = []
            for nom, info in rap_train.get("performances_comparatives", {}).items():
                m = info.get("metriques_test", {})
                comp_data.append({
                    "Modèle": nom,
                    "Rappel (Recall)": f"{m.get('recall', 0)*100:.2f}%",
                    "F2-Score": m.get("f2_score", 0),
                    "ROC-AUC": m.get("roc_auc", 0),
                    "Précision": f"{m.get('precision', 0)*100:.2f}%",
                    "Accuracy": f"{m.get('accuracy', 0)*100:.2f}%",
                    "Rappel CV (GridSearch)": f"{info.get('rappel_cv', 0)*100:.2f}%",
                })
            st.table(pd.DataFrame(comp_data).set_index("Modèle"))

            st.subheader("⭐ Top 15 des variables socio-démographiques les plus influentes")
            top_f = rap_train.get("top_features_importance", [])
            if top_f:
                st.dataframe(pd.DataFrame(top_f).head(15), use_container_width=True)

# =========================================================
# 11. GUIDES & DOCUMENTATION UTILISATEUR
# =========================================================
elif menu == "📖 Guides & Documentation":
    st.header("📖 Guides & Notices d'Utilisation")
    st.markdown("""
        Cet espace centralise l'ensemble des notices opérationnelles et guides méthodologiques du projet. 
        Les agents de terrain et coordinateurs peuvent les consulter directement sans avoir à ouvrir l'environnement technique.
    """)

    notices = {
        "00. Guide Général — Prise en main de l'Application & API": "docs/00. notice_user_api.md",
        "01. Guide Opérationnel — Ingestion & Nettoyage Kobo (Partie 1)": "docs/01. notice_user_pipeline.md",
        "02. Guide Opérationnel — Base relationnelle SQLite 3NF (Partie 2)": "docs/02. notice_user_sql.md",
        "03. Guide Méthodologique — Diagnostic JIAF 2.0 & Profilage (Partie 3)": "docs/03. notice_user_eda.md",
        "04. Guide Décisionnel — Modélisation IA, Ciblage & Do No Harm (Partie 4)": "docs/04. notice_user_ML.md",
        "05. Guide Technique — Schéma relationnel & Dictionnaire de données": "docs/schema_rel.md",
    }

    choix_doc = st.selectbox("Sélectionnez le guide à consulter :", list(notices.keys()))
    chemin_doc = notices[choix_doc]

    if os.path.exists(chemin_doc):
        with open(chemin_doc, "r", encoding="utf-8") as f_doc:
            contenu_markdown = f_doc.read()
        
        col_down, _ = st.columns([1, 3])
        with col_down:
            st.download_button(
                "⬇️ Télécharger ce guide (Markdown)",
                data=contenu_markdown.encode("utf-8"),
                file_name=os.path.basename(chemin_doc),
                mime="text/markdown",
            )
        
        st.markdown("---")
        st.markdown(contenu_markdown)
    else:
        st.error(f"Le fichier `{chemin_doc}` est introuvable sur le disque.")



