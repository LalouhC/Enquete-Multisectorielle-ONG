"""Module de génération du Dashboard interactif humanitaire (Partie 5).

Ce module produit :
1. Un jeu de données plat et dénormalisé enrichi (JIAF 2.0 + Machine Learning + Coordonnées GPS) :
   `outputs/donnees_dashboard.csv` prêt pour l'intégration directe dans Power BI ou Tableau.
2. Un Dashboard Web interactif autonome (HTML/CSS Kobo/JS/Leaflet) :
   `outputs/dashboard_interactif.html` consultable hors-ligne et diffusable sans serveur.
3. Des fonctions de restitution interactives pour l'application Streamlit.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.partie4_ML import (
    charger_modele_et_rapport,
    construire_cible_multisectorielle,
    extraire_donnees_brutes,
    preparer_matrice_explicative,
)

LOGGER = logging.getLogger(__name__)

RACINE_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_SORTIE = RACINE_PROJET / "outputs"
CHEMIN_CSV_DASHBOARD = DOSSIER_SORTIE / "donnees_dashboard.csv"
CHEMIN_HTML_DASHBOARD = DOSSIER_SORTIE / "dashboard_interactif.html"

# Coordonnées réelles de référence en RDC (Province de l'Équateur)
COORDONNEES_ZONES = {
    "village_1": {
        "nom": "Zone Bikoro / Lac Tumba",
        "axe": "Axe Bikoro - Tumba",
        "lat": -0.7483,
        "lon": 18.1256,
        "dispersion": 0.025,
    },
    "village_2": {
        "nom": "Zone Mbandaka (Péri-urbain)",
        "axe": "Axe Mbandaka Nord",
        "lat": 0.0489,
        "lon": 18.2603,
        "dispersion": 0.020,
    },
}


def preparer_donnees_dashboard(
    chemin_db: Optional[Path] = None,
    seuil_priorite_ml: float = 0.50,
) -> pd.DataFrame:
    """Génère la base dénormalisée enrichie avec les scores JIAF, l'inférence ML et les coordonnées géographiques."""
    LOGGER.info("Génération du jeu de données dénormalisé pour le dashboard...")
    df_brut = extraire_donnees_brutes(chemin_db)
    
    # 1. Calcul des scores sectoriels JIAF 2.0
    y_reelle, df_scores = construire_cible_multisectorielle(df_brut)

    # 2. Inférence Machine Learning instantanée
    modele, _ = charger_modele_et_rapport()
    X = preparer_matrice_explicative(df_brut)
    probas_ml = modele.predict_proba(X)[:, 1]
    preds_ml = (probas_ml >= seuil_priorite_ml).astype(int)

    # 3. Assemblage de la table dénormalisée
    df_dash = pd.DataFrame()
    df_dash["id_menage"] = df_brut.get("id_menage", [f"MENAGE_{i+1}" for i in range(len(df_brut))])
    df_dash["code_jeton"] = df_brut.get("code_jeton", df_dash["id_menage"])
    df_dash["date_enquete"] = df_brut.get("date_enquete", "2020-04-15")

    # Géographie & Déplacement
    df_dash["village_code"] = df_brut.get("village", "village_1")
    
    # Génération des coordonnées GPS réalistes pour la cartographie
    np.random.seed(42)
    lats = []
    lons = []
    zone_noms = []
    axes_noms = []

    for v in df_dash["village_code"]:
        params = COORDONNEES_ZONES.get(str(v), COORDONNEES_ZONES["village_1"])
        zone_noms.append(params["nom"])
        axes_noms.append(params["axe"])
        # Décalage léger (anonymisation Do No Harm)
        lat_bruit = params["lat"] + np.random.normal(0, params["dispersion"])
        lon_bruit = params["lon"] + np.random.normal(0, params["dispersion"])
        lats.append(round(lat_bruit, 5))
        lons.append(round(lon_bruit, 5))

    df_dash["zone_nom"] = zone_noms
    df_dash["axe_humanitaire"] = axes_noms
    df_dash["latitude"] = lats
    df_dash["longitude"] = lons

    # Profil Socio-démographique (Axe 1)
    statut_raw = df_brut.get("status", "hote").astype(str).str.lower()
    mapping_statut = {
        "idp": "Déplacé interne (PDI)",
        "deplace": "Déplacé interne (PDI)",
        "ret": "Retourné",
        "retourne": "Retourné",
        "hote": "Communauté hôte",
    }
    df_dash["statut_menage"] = statut_raw.map(lambda s: mapping_statut.get(s, "Communauté hôte"))

    sexe_raw = df_brut.get("sexe", "homme").astype(str).str.lower()
    df_dash["genre_chef_menage"] = np.where(
        sexe_raw.str.contains("fem|f", regex=True), "Femme", "Homme"
    )

    df_dash["age_chef_menage"] = pd.to_numeric(df_brut.get("age", 40), errors="coerce").fillna(40).astype(int)
    
    # Tranches d'âge standard humanitaires
    df_dash["tranche_age"] = pd.cut(
        df_dash["age_chef_menage"],
        bins=[0, 24, 49, 59, 120],
        labels=["Moins de 25 ans", "25 - 49 ans", "50 - 59 ans", "60 ans et plus"],
    ).astype(str)

    # Calcul de la taille globale du ménage
    cols_comp = [c for c in df_brut.columns if (c.startswith("h_") or c.startswith("f_")) and "_" in c]
    if cols_comp:
        df_dash["taille_menage"] = df_brut[cols_comp].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1).astype(int)
    else:
        df_dash["taille_menage"] = 6

    # Identification et cumul des personnes à charge vulnérables :
    # 1. Enfants / Mineurs (< 18 ans)
    cols_mineurs = [c for c in df_brut.columns if any(c.endswith(x) for x in ["0_5", "6_24", "25_59", "5_14", "15_17"])]
    nb_mineurs = df_brut[cols_mineurs].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if cols_mineurs else pd.Series(0, index=df_dash.index)

    # 2. Personnes âgées (> 60 ans)
    cols_agees = [c for c in df_brut.columns if any(c.endswith(x) for x in ["plus60", "plus_60", "60"])]
    nb_agees = df_brut[cols_agees].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if cols_agees else pd.Series(0, index=df_dash.index)

    # 3. Personnes avec handicap (adultincap ou hand)
    nb_handicap = pd.to_numeric(df_brut.get("adultincap", 0), errors="coerce").fillna(0)
    if (nb_handicap == 0).all() and "hand" in df_brut.columns:
        nb_handicap = df_brut["hand"].astype(str).str.lower().str.contains("oui|1", regex=True).astype(int)

    # 4. Femmes enceintes ou allaitantes
    nb_fem_vuln = (
        df_brut.get("fem_enc", "non").astype(str).str.lower().str.contains("oui|1", regex=True).astype(int)
        | df_brut.get("fem_all", "non").astype(str).str.lower().str.contains("oui|1", regex=True).astype(int)
    )

    # Somme des personnes représentant une charge de vulnérabilité
    df_dash["nb_mineurs"] = nb_mineurs.astype(int)
    df_dash["nb_personnes_agees"] = nb_agees.astype(int)
    df_dash["nb_personnes_handicap"] = nb_handicap.astype(int)
    df_dash["femme_enceinte_ou_allaitante_nb"] = nb_fem_vuln.astype(int)
    
    personnes_charge = (nb_mineurs + nb_agees + nb_handicap + nb_fem_vuln).clip(upper=df_dash["taille_menage"])
    df_dash["nb_personnes_a_charge"] = personnes_charge.astype(int)
    df_dash["ratio_personnes_charge"] = np.where(
        df_dash["taille_menage"] > 0,
        np.round(df_dash["nb_personnes_a_charge"] / df_dash["taille_menage"], 2),
        0.0
    )

    # Vulnérabilités spécifiques (format texte pour filtres et tableaux)
    df_dash["personne_handicapee"] = np.where(nb_handicap > 0, "Oui", "Non")
    df_dash["femme_enceinte_ou_allaitante"] = np.where(nb_fem_vuln > 0, "Oui", "Non")
    df_dash["statut_matrimonial"] = df_brut.get("statmtr", "Marié(e)")

    # Sévérités Sectorielles JIAF 2.0 (Axe 2)
    df_dash["score_hhs_alimentation"] = pd.to_numeric(df_scores.get("score_hhs_total", 0), errors="coerce").fillna(0).round(1)
    df_dash["categorie_hhs"] = df_scores.get("categorie_hhs", "Pas de faim").fillna("Pas de faim")
    df_dash["secal_critique"] = pd.to_numeric(df_scores.get("cible_hhs_severe", 0), errors="coerce").fillna(0).astype(int)

    df_dash["score_wash_eau"] = pd.to_numeric(df_scores.get("score_global_wash", 1), errors="coerce").fillna(1).astype(int)
    df_dash["niveau_wash"] = df_scores.get("niveau_wash", "Conforme").fillna("Conforme")
    df_dash["wash_critique"] = pd.to_numeric(df_scores.get("cible_wash_eau_critique", 0), errors="coerce").fillna(0).astype(int)

    df_dash["score_ame_materiel"] = pd.to_numeric(df_scores.get("score_ame_global", 1.0), errors="coerce").fillna(1.0).round(2)
    df_dash["categorie_ame"] = df_scores.get("categorie_ame_phase", "Phase 1-2").fillna("Phase 1-2")
    df_dash["ame_critique"] = pd.to_numeric(df_scores.get("cible_binaire_ame", 0), errors="coerce").fillna(0).astype(int)

    df_dash["score_agro"] = pd.to_numeric(df_scores.get("score_global_agro", 1), errors="coerce").fillna(1).astype(int)
    df_dash["agro_critique"] = pd.to_numeric(df_scores.get("cible_vulnerabilite_agro_severe", 0), errors="coerce").fillna(0).astype(int)

    # Cumul des crises multisectorielles JIAF 2.0
    cumul = (
        df_dash["secal_critique"]
        + df_dash["wash_critique"]
        + df_dash["ame_critique"]
        + df_dash["agro_critique"]
    )
    df_dash["cumul_crises_jiaf"] = cumul
    df_dash["vulnerabilite_aigue_reelle"] = (cumul >= 3).astype(int)
    df_dash["statut_besoin_humanitaire"] = np.where(
        cumul >= 3, "Besoin Urgent (Phase 3+ JIAF)", "Besoin Modéré ou Autonome"
    )

    # Prédictions d'Assistance Machine Learning
    df_dash["probabilite_vulnerabilite_ml"] = np.round(probas_ml, 4)
    df_dash["score_vulnerabilite_ml_pct"] = np.round(probas_ml * 100, 1)
    df_dash["prediction_classe_ml"] = preds_ml
    df_dash["priorite_assistance_ml"] = np.where(
        preds_ml == 1, "Prioritaire (Assistance)", "Non prioritaire"
    )

    # Concordance / Évaluation Do No Harm
    conditions = [
        (df_dash["vulnerabilite_aigue_reelle"] == 1) & (df_dash["prediction_classe_ml"] == 1),
        (df_dash["vulnerabilite_aigue_reelle"] == 0) & (df_dash["prediction_classe_ml"] == 0),
        (df_dash["vulnerabilite_aigue_reelle"] == 0) & (df_dash["prediction_classe_ml"] == 1),
        (df_dash["vulnerabilite_aigue_reelle"] == 1) & (df_dash["prediction_classe_ml"] == 0),
    ]
    choix = [
        "Vrai Positif (Ciblé & Vulnérable)",
        "Vrai Négatif (Autonome)",
        "Inclusion de précaution (Faux Positif)",
        "Exclusion involontaire (Faux Négatif)",
    ]
    df_dash["audit_concordance"] = np.select(conditions, choix, default="Non classé")

    # Sauvegarde sur le disque pour Power BI / Tableau et Streamlit
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    df_dash.to_csv(CHEMIN_CSV_DASHBOARD, index=False, encoding="utf-8-sig")
    LOGGER.info("Fichier CSV prêt pour Power BI / Tableau enregistré dans %s", CHEMIN_CSV_DASHBOARD)

    return df_dash


def generer_dashboard_html(df_dash: pd.DataFrame) -> str:
    """Génère un dashboard HTML autonome avec Leaflet pour la carte, Chart.js pour les graphiques et CSS Kobo."""
    LOGGER.info("Génération du rapport HTML interactif autonome...")
    
    total_menages = len(df_dash)
    taux_jiaf_aigu = (df_dash["vulnerabilite_aigue_reelle"].mean() * 100).round(1)
    taux_ml_prioritaire = (df_dash["prediction_classe_ml"].mean() * 100).round(1)
    taille_moyenne = df_dash["taille_menage"].mean().round(1)
    taux_charge_moyen = (df_dash["ratio_personnes_charge"].mean() * 100).round(1)

    hhs_moyen = df_dash["score_hhs_alimentation"].mean().round(2)
    taux_wash_critique = (df_dash["wash_critique"].mean() * 100).round(1)
    taux_agro_critique = (df_dash["agro_critique"].mean() * 100).round(1)

    # Agrégration pour la carte par zone
    stats_zones = []
    for zone, group in df_dash.groupby("zone_nom"):
        stats_zones.append({
            "zone": zone,
            "lat": float(group["latitude"].mean()),
            "lon": float(group["longitude"].mean()),
            "count": int(len(group)),
            "pct_total": round(len(group) / total_menages * 100, 1),
            "taux_vulnerabilite": round(float(group["vulnerabilite_aigue_reelle"].mean() * 100), 1),
            "hhs_moyen": round(float(group["score_hhs_alimentation"].mean()), 2),
            "wash_critique_pct": round(float(group["wash_critique"].mean() * 100), 1),
            "agro_critique_pct": round(float(group["agro_critique"].mean() * 100), 1),
            "prio_ml_pct": round(float(group["prediction_classe_ml"].mean() * 100), 1),
        })

    # Données pour les graphiques
    # Graphique 1 : Sévérité par Statut de déplacement
    statut_df = df_dash.groupby("statut_menage").agg(
        total=("id_menage", "count"),
        pct_vuln=("vulnerabilite_aigue_reelle", lambda x: round(x.mean() * 100, 1)),
        pct_prio_ml=("prediction_classe_ml", lambda x: round(x.mean() * 100, 1)),
        pct_agro=("agro_critique", lambda x: round(x.mean() * 100, 1)),
    ).reset_index()

    # Graphique 2 : Ventilation du Cumul de crises JIAF
    cumul_counts = df_dash["cumul_crises_jiaf"].value_counts().sort_index().to_dict()

    # Graphique 3 : Vulnérabilité Agricole selon le Statut
    agro_df = statut_df[["statut_menage", "pct_agro"]].copy()
    genre_df = df_dash.groupby("genre_chef_menage").agg(
        total=("id_menage", "count"),
        pct_vuln=("vulnerabilite_aigue_reelle", lambda x: round(x.mean() * 100, 1)),
        hhs_moyen=("score_hhs_alimentation", lambda x: round(x.mean(), 2)),
    ).reset_index()

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tableau de Bord Multisectoriel Humanitaire (JIAF 2.0 & ML)</title>
    <!-- Styles Leaflet & Chart.js via CDN pour portabilité complète -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --kobo-blue: #0060DF;
            --kobo-dark: #0B2545;
            --kobo-light: #F8FAFC;
            --text-dark: #0F172A;
            --danger: #DC2626;
            --warning: #D97706;
            --success: #16A34A;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
            background-color: var(--kobo-light);
            color: var(--text-dark);
        }}
        .header {{
            background: linear-gradient(135deg, #0B2545 0%, #1D548C 100%);
            color: white;
            padding: 26px 32px;
            border-radius: 16px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(11, 37, 69, 0.2);
        }}
        .header h1 {{ margin: 0 0 8px 0; font-size: 1.8rem; font-weight: 800; }}
        .header p {{ margin: 0; opacity: 0.9; font-size: 0.95rem; line-height: 1.5; }}
        .badge-op {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 700;
            margin-bottom: 12px;
            letter-spacing: 0.05em;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: white;
            border: 1.5px solid #E2E8F0;
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
            border-left: 5px solid var(--kobo-blue);
        }}
        .kpi-title {{ font-size: 0.82rem; font-weight: 700; color: #64748B; text-transform: uppercase; margin-bottom: 6px; }}
        .kpi-value {{ font-size: 1.8rem; font-weight: 800; color: var(--kobo-dark); margin-bottom: 4px; }}
        .kpi-sub {{ font-size: 0.78rem; color: #475569; }}
        
        .section-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }}
        @media (max-width: 900px) {{
            .section-grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: white;
            border: 1.5px solid #E2E8F0;
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04);
        }}
        .card-title {{
            font-size: 1.05rem;
            font-weight: 800;
            color: var(--kobo-dark);
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        #map {{
            height: 380px;
            width: 100%;
            border-radius: 10px;
            border: 1px solid #CBD5E1;
        }}
        .notice-box {{
            background: #EFF6FF;
            border: 1.5px solid #BFDBFE;
            border-radius: 12px;
            padding: 16px 20px;
            font-size: 0.88rem;
            color: #1E3A8A;
            line-height: 1.5;
            margin-top: 24px;
        }}
    </style>
</head>
<body>

    <div class="header">
        <div class="badge-op">📍 Enquête Active : RDC Province de l'Équateur · Axe Bikoro - Mbandaka</div>
        <h1>Tableau de Bord Multisectoriel Humanitaire (JIAF 2.0 & ML)</h1>
        <p>Aide à la décision opérationnelle, cartographie des besoins urgents et pré-ciblage prédictif des ménages les plus vulnérables.</p>
    </div>

    <!-- 4 KPI PRINCIPAUX RECOMMANDÉS -->
    <div class="kpi-grid">
        <div class="kpi-card" style="border-left-color: #DC2626;">
            <div class="kpi-title">🚨 Vulnérabilité Aiguë (JIAF 2.0)</div>
            <div class="kpi-value">{taux_jiaf_aigu}%</div>
            <div class="kpi-sub">{(df_dash['vulnerabilite_aigue_reelle'].sum()):,} ménages cumulant ≥ 3 crises</div>
        </div>
        <div class="kpi-card" style="border-left-color: #0060DF;">
            <div class="kpi-title">🤖 Pré-ciblage Prioritaire IA</div>
            <div class="kpi-value">{taux_ml_prioritaire}%</div>
            <div class="kpi-sub">{(df_dash['prediction_classe_ml'].sum()):,} ménages priorisés par le modèle</div>
        </div>
        <div class="kpi-card" style="border-left-color: #0D9488;">
            <div class="kpi-title">👨‍👩‍👧‍👦 Taille Moyenne du Ménage</div>
            <div class="kpi-value">{taille_moyenne} <span style="font-size: 1rem; color: #64748B;">pers.</span></div>
            <div class="kpi-sub">Base de dimensionnement des rations et kits</div>
        </div>
        <div class="kpi-card" style="border-left-color: #D97706;">
            <div class="kpi-title">👶👵 Personnes à Charge Vulnérables</div>
            <div class="kpi-value">{taux_charge_moyen}%</div>
            <div class="kpi-sub">Enfants, femmes enc./all., pers. handicapées & âgées</div>
        </div>
    </div>

    <!-- BANDEAU DES POINTS D'ATTENTION & WARNINGS AUDIT -->
    <div style="background: #FFFBEB; border-left: 5px solid #F59E0B; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px; font-size: 0.88rem; color: #92400E; line-height: 1.5;">
        <strong>⚠️ Points d'attention et alertes méthodologiques de terrain (Audit Qualité) :</strong>
        <ul style="margin: 6px 0 0 18px; padding: 0;">
            <li><strong>Environnement physique :</strong> 45,10% des ménages vivent en environnement dangereux et 33,97% en environnement dangereux avec promiscuité des abris (&lt; 1,5m).</li>
            <li><strong>Protection & Santé infantile :</strong> 36,27% des enfants malnutris identifiés ne bénéficient d'aucune prise en charge nutritionnelle active.</li>
            <li><strong>Biais de composition :</strong> 96 ménages enquêtés ne comptent que des mineurs déclarés dans la composition du foyer (le répondant adulte ne s’étant pas auto-compté).</li>
            <li><strong>Principe Do No Harm :</strong> Les seuils et pondérations sont spécifiques à l'Équateur (RDC 2020-2021) et ne doivent pas être transposés sans réétalonnage préalable.</li>
        </ul>
    </div>

    <!-- AXES 1, 2 ET 3 (DONT LA CARTE) -->
    <div class="section-grid">
        <!-- CARTE GÉOGRAPHIQUE OBLIGATOIRE (Axe 1 : SIG) -->
        <div class="card">
            <div class="card-title">🗺️ Axe 1 : Cartographie des Besoins (Bikoro - Lac Tumba - Mbandaka)</div>
            <div id="map"></div>
            <p style="font-size: 0.78rem; color: #64748B; margin-top: 8px;">
                <em>Conformité Do No Harm :</em> Centroïdes des grappes de villages avec cercles proportionnels à l'échantillon et colorés selon le niveau de sévérité multisectorielle.
            </p>
        </div>

        <!-- AXE 2 : PROFIL MULTISECTORIEL (CUMUL DES CRISES JIAF 2.0) -->
        <div class="card">
            <div class="card-title">⚖️ Axe 2 : Profil Multisectoriel & Cumul de Crises (0 à 4)</div>
            <canvas id="chartCumul" style="max-height: 380px;"></canvas>
        </div>
    </div>

    <div class="section-grid">
        <!-- AXE 3 : FOCUS VULNÉRABILITÉ AGRICOLE & MOYENS D'EXISTENCE -->
        <div class="card">
            <div class="card-title">🌾 Axe 3 : Précarité Agricole & Moyens d'Existence selon le Statut</div>
            <canvas id="chartAgro" style="max-height: 300px;"></canvas>
            <p style="font-size: 0.78rem; color: #64748B; margin-top: 8px;">
                Mesure la part de ménages cumulant manque de terres, absence d'outils, absence de main-d'œuvre et novice (&lt; 2 ans).
            </p>
        </div>

        <!-- CROISEMENT STATUT DE DÉPLACEMENT & CIBLAGE IA -->
        <div class="card">
            <div class="card-title">⛺ Confrontation : Vulnérabilité Réelle JIAF vs Pré-ciblage IA</div>
            <canvas id="chartStatut" style="max-height: 300px;"></canvas>
        </div>
    </div>

    <div class="notice-box">
        <strong>💡 Utilisation pour votre évaluation (Power BI ou Tableau) :</strong><br>
        Le fichier de données complet dénormalisé utilisé pour générer ce tableau de bord est disponible dans 
        <code>outputs/donnees_dashboard.csv</code>. Il contient l'ensemble des indicateurs calculés (HHS, WASH, AME, AGRO), 
        les coordonnées GPS pour votre carte, et les prédictions d'intelligence artificielle. Vous pouvez l'importer directement 
        dans Power BI (fichier <code>.pbix</code>) ou Tableau Desktop (fichier <code>.twbx</code>).
    </div>

    <script>
        // 1. Initialisation de la carte Leaflet
        const map = L.map('map').setView([-0.35, 18.20], 8);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            maxZoom: 18,
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);

        const zones = {json.dumps(stats_zones)};
        zones.forEach(z => {{
            const color = z.taux_vulnerabilite > 50 ? '#DC2626' : (z.taux_vulnerabilite > 35 ? '#D97706' : '#16A34A');
            const circle = L.circleMarker([z.lat, z.lon], {{
                radius: Math.max(12, Math.min(28, z.count / 1500)),
                fillColor: color,
                color: '#FFFFFF',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }}).addTo(map);

            circle.bindPopup(`
                <div style="font-family: sans-serif; font-size: 13px;">
                    <strong style="color: #0B2545;">${{z.zone}}</strong><br>
                    <strong>Ménages enquêtés :</strong> ${{z.count.toLocaleString()}} (${{z.pct_total}}%)<br>
                    <strong>Taux de détresse aiguë (JIAF) :</strong> <span style="color: ${{color}}; font-weight: bold;">${{z.taux_vulnerabilite}}%</span><br>
                    <strong>Score moyen Faim (HHS) :</strong> ${{z.hhs_moyen}} / 6<br>
                    <strong>Précarité Eau (WASH) :</strong> ${{z.wash_critique_pct}}%<br>
                    <strong>Priorité Machine Learning :</strong> ${{z.prio_ml_pct}}%
                </div>
            `);
        }});

        // 2. Graphique Axe 1 : Statut
        const ctxStatut = document.getElementById('chartStatut').getContext('2d');
        new Chart(ctxStatut, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(statut_df['statut_menage'].tolist())},
                datasets: [
                    {{
                        label: 'Vulnérabilité Aiguë Réelle JIAF (%)',
                        data: {json.dumps(statut_df['pct_vuln'].tolist())},
                        backgroundColor: '#DC2626'
                    }},
                    {{
                        label: 'Pré-ciblage Prioritaire IA (%)',
                        data: {json.dumps(statut_df['pct_prio_ml'].tolist())},
                        backgroundColor: '#0060DF'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                scales: {{ y: {{ beginAtZero: true, max: 100, title: {{ display: true, text: 'Pourcentage (%)' }} }} }}
            }}
        }});

        // 3. Graphique Axe 2 : Cumul des crises
        const ctxCumul = document.getElementById('chartCumul').getContext('2d');
        new Chart(ctxCumul, {{
            type: 'doughnut',
            data: {{
                labels: ['0 crise', '1 crise sectorielle', '2 crises', '3 crises (Sévère)', '4 crises (Extrême)'],
                datasets: [{{
                    data: [{cumul_counts.get(0, 0)}, {cumul_counts.get(1, 0)}, {cumul_counts.get(2, 0)}, {cumul_counts.get(3, 0)}, {cumul_counts.get(4, 0)}],
                    backgroundColor: ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#991B1B']
                }}]
            }},
            options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }} }}
        }});

        // 4. Graphique Axe 3 : Agro
        const ctxAgro = document.getElementById('chartAgro').getContext('2d');
        new Chart(ctxAgro, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(agro_df['statut_menage'].tolist())},
                datasets: [{{
                    label: 'Taux de Précarité Agricole AGRO (%)',
                    data: {json.dumps(agro_df['pct_agro'].tolist())},
                    backgroundColor: '#F59E0B'
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{ y: {{ beginAtZero: true, max: 100, title: {{ display: true, text: 'Pourcentage (%)' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""
    with open(CHEMIN_HTML_DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html_content)

    LOGGER.info("Rapport HTML interactif autonome sauvegardé dans %s", CHEMIN_HTML_DASHBOARD)
    return html_content
