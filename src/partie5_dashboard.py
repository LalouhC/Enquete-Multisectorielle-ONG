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
    def _libelle_statut(valeur):
        texte = str(valeur).casefold()
        if "fugi" in texte or "dépla" in texte and "non" not in texte:
            return "Réfugié / déplacé"
        if "non famille" in texte:
            return "Autochtone hors famille d'accueil"
        if "famille" in texte:
            return "Autochtone en famille d'accueil"
        return "Statut non renseigné"

    df_dash["statut_menage"] = statut_raw.map(_libelle_statut)

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


LIBELLE_TOUS = "Tous les ménages"

MODELE_HTML_DASHBOARD = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tableau de bord décisionnel - Enquête multisectorielle</title>
<style>__LEAFLET_CSS__</style>
<script>__LEAFLET_JS__</script>
<script>__CHART_JS__</script>
<style>
:root{--navy:#1F2A44;--slate:#475569;--muted:#64748B;--line:#E2E8F0;--bg:#F1F4F8;--card:#FFFFFF;
--c1:#3E5C82;--c2:#6B8CAE;--c3:#7FB38F;--c4:#E3B04B;--c5:#C8605C;--c6:#8A94A6;--vert:#7FB38F;--jaune:#EBCB6B;--orange:#E2985A;--rouge:#C8605C;--eau:#5B9BC9}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--bg);color:var(--navy);font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;background:var(--navy);color:#fff;border-radius:10px;padding:14px 20px}
.header h1{margin:0;font-size:1.25rem;font-weight:700}
.header p{margin:2px 0 0;font-size:.8rem;color:#C5CEDB}
.seg{display:flex;gap:6px;flex-wrap:wrap}
.seg button{border:1px solid #51607E;background:transparent;color:#DCE3EE;padding:7px 14px;border-radius:6px;font-size:.82rem;cursor:pointer;font-family:inherit}
.seg button:hover{background:#2C3A5C}
.seg button.actif{background:#fff;color:var(--navy);border-color:#fff;font-weight:700}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-top:3px solid var(--c1);border-radius:8px;padding:12px 16px}
.kpi .t{font-size:.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.kpi .v{font-size:1.7rem;font-weight:700;margin:4px 0 2px}
.kpi .s{font-size:.74rem;color:var(--slate)}
.alertes{margin-top:12px;background:#FBF7EE;border:1px solid #E7DCC2;border-left:4px solid var(--c4);border-radius:8px;padding:10px 16px;font-size:.8rem;color:#5B4A2A}
.alertes ul{margin:4px 0 0 16px;padding:0}.alertes li{margin:2px 0}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;min-width:0}
.card h3{margin:0 0 8px;font-size:.88rem;font-weight:700}
.card .note{font-size:.7rem;color:var(--muted);margin-top:6px}
.span2{grid-column:span 2}
#carte{height:300px;border-radius:6px;border:1px solid var(--line);background:#E9EDF2}
.cv{position:relative;height:250px}
.pied{margin-top:12px;font-size:.72rem;color:var(--muted)}
@media(max-width:900px){.kpis{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.span2{grid-column:span 1}}
</style>
</head>
<body>
<div class="header">
  <div><h1>__TITRE__</h1><p>__SOUS_TITRE__</p></div>
  <div class="seg" id="segments"></div>
</div>
<div class="kpis">
  <div class="kpi" style="border-top-color:#C8605C"><div class="t">Vulnérabilité aiguë (JIAF 2.0)</div><div class="v" id="k1">-</div><div class="s" id="k1s"></div></div>
  <div class="kpi" style="border-top-color:#3E5C82"><div class="t">Pré-ciblage prioritaire (IA)</div><div class="v" id="k2">-</div><div class="s" id="k2s"></div></div>
  <div class="kpi" style="border-top-color:#8A94A6"><div class="t">Taille moyenne du ménage</div><div class="v" id="k3">-</div><div class="s" id="k3s"></div></div>
  <div class="kpi" style="border-top-color:#E2985A"><div class="t">Personnes à charge vulnérables</div><div class="v" id="k4">-</div><div class="s" id="k4s"></div></div>
</div>
<div class="alertes"><strong>Points d'attention (audit qualité et terrain)</strong>
  <ul>
    <li>45,10 % des ménages vivent en environnement dangereux, dont 33,97 % avec promiscuité des abris (&lt; 1,5 m).</li>
    <li>36,27 % des enfants malnutris identifiés ne bénéficient d'aucune prise en charge.</li>
    <li><em>96 ménages ne déclarent que des mineurs : le répondant adulte ne s'est probablement pas compté dans le foyer.</em></li>
    <li>Seuils et modèle calibrés sur la province de l'Équateur (RDC, 2020) : tout autre contexte exige un réétalonnage par l'équipe technique.</li>
  </ul>
</div>
<div class="grid">
  <div class="card span2"><h3>Axe 1 - Répartition géographique des besoins</h3><div id="carte"></div>
    <div class="note">Cercles proportionnels au nombre de ménages. Couleur selon la vulnérabilité aiguë : vert (moins de 25 %), jaune (25 à 35 %), orange (35 à 50 %), rouge (50 % et plus). Positions anonymisées (Do No Harm).</div></div>
  <div class="card"><h3>Axe 2 - Cumul de crises sectorielles</h3><div class="cv"><canvas id="gCumul"></canvas></div>
    <div class="note">Secteurs critiques simultanés : vert (aucun), jaune (1), orange (2), rouge (3 et plus = urgence).</div></div>
  <div class="card"><h3>Axe 2 - Profil par secteur (% de ménages critiques)</h3><div class="cv"><canvas id="gSecteurs"></canvas></div><div class="note">Vert : moins de 40 %. Jaune : 40 à 60 %. Orange : 60 à 80 %. Rouge : 80 % et plus.</div></div>
  <div class="card"><h3>Axe 3 - Précarité agricole selon la zone et le genre du chef</h3><div class="cv"><canvas id="gAgro"></canvas></div>
    <div class="note">Part de ménages en vulnérabilité agricole sévère. Femmes en rose, hommes en bleu.</div></div>
  <div class="card"><h3>Vulnérabilité réelle et pré-ciblage IA par statut</h3><div class="cv"><canvas id="gStatut"></canvas></div>
    <div class="note">Barres : vulnérabilité aiguë réelle. Courbe : pré-ciblage IA. Les trois statuts sont toujours affichés.</div></div>
</div>
<div class="pied">Jeu de données dénormalisé : outputs/donnees_dashboard.csv ({N_TOTAL} ménages) - utilisable dans Power BI Desktop ou Tableau.</div>
<script>
const DATA = __DATA__;
const COULEURS = {c1:'#3E5C82',c2:'#6B8CAE',c3:'#7FB38F',c4:'#E2985A',c5:'#C8605C',c6:'#8A94A6'};
const fmt = (x,d=1) => Number(x).toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
Chart.defaults.font.family = '"Segoe UI",Roboto,Arial,sans-serif';
Chart.defaults.font.size = 11;
Chart.defaults.color = '#475569';
const carte = L.map('carte').setView([-0.35,18.2],8);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap (si connecté)'}).addTo(carte);
const couche = L.layerGroup().addTo(carte);
const optionsPct = {responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{boxWidth:10}}},
  scales:{y:{beginAtZero:true,max:100,ticks:{callback:v=>v+' %'},grid:{color:'#EEF1F5'}},x:{grid:{display:false}}}};
const graphiques = {
  cumul:new Chart('gCumul',{type:'bar',data:{labels:['0','1','2','3','4'],datasets:[{label:'Ménages',data:[],backgroundColor:['#7FB38F','#EBCB6B','#E2985A','#C8605C','#A94442']}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#EEF1F5'}},x:{grid:{display:false},title:{display:true,text:'Nombre de crises'}}}}}),
  secteurs:new Chart('gSecteurs',{type:'bar',data:{labels:['Faim (HHS)','Eau (WASH)','Biens (AME)','Agriculture'],datasets:[{label:'% critiques',data:[],backgroundColor:['#B8935A','#5B9BC9','#8A94A6','#8FA66B']}]},
    options:{...optionsPct,indexAxis:'y',plugins:{legend:{display:false}},scales:{x:optionsPct.scales.y,y:{grid:{display:false}}}}}),
  agro:new Chart('gAgro',{type:'bar',data:{labels:[],datasets:[]},options:optionsPct}),
  statut:new Chart('gStatut',{type:'bar',data:{labels:DATA.statuts.map(s=>s.nom),datasets:[
    {label:'Vulnérabilité aiguë réelle',data:DATA.statuts.map(s=>s.vuln),backgroundColor:COULEURS.c5},
    {type:'line',label:'Pré-ciblage IA',data:DATA.statuts.map(s=>s.prio),borderColor:COULEURS.c1,backgroundColor:COULEURS.c1,borderWidth:2.5,pointRadius:5,tension:.25}]},options:optionsPct})
};
function teinteSecteur(v){return v>=80?'#C8605C':(v>=60?'#E2985A':(v>=40?'#EBCB6B':'#7FB38F'));}
function teinte(v){return v>=50?'#C8605C':(v>=35?'#E2985A':(v>=25?'#EBCB6B':'#7FB38F'));}
function afficher(cle){
  const d = DATA.segments[cle];
  document.querySelectorAll('#segments button').forEach(b=>b.classList.toggle('actif',b.dataset.cle===cle));
  document.getElementById('k1').textContent = fmt(d.vuln)+' %';
  document.getElementById('k1s').textContent = fmt(d.nb_vuln,0)+' ménages avec 3 crises ou plus';
  document.getElementById('k2').textContent = fmt(d.prio)+' %';
  document.getElementById('k2s').textContent = fmt(d.nb_prio,0)+' ménages recommandés par le modèle';
  document.getElementById('k3').textContent = fmt(d.taille)+' pers.';
  document.getElementById('k3s').textContent = fmt(d.n,0)+' ménages dans la sélection';
  document.getElementById('k4').textContent = fmt(d.charge)+' %';
  document.getElementById('k4s').textContent = 'Mineurs, aînés, handicap, femmes enceintes ou allaitantes';
  couche.clearLayers();
  const bornes = [];
  d.zones.forEach(z=>{
    const c = teinte(z.vuln);
    L.circleMarker([z.lat,z.lon],{radius:Math.max(10,Math.min(30,Math.sqrt(z.n)/3)),fillColor:c,color:'#fff',weight:2,fillOpacity:.8}).addTo(couche)
      .bindTooltip(z.nom,{permanent:true,direction:'top',offset:[0,-8]}).bindPopup('<strong>'+z.nom+'</strong><br>Ménages : '+fmt(z.n,0)+'<br>Vulnérabilité aiguë : '+fmt(z.vuln)+' %<br>Pré-ciblage IA : '+fmt(z.prio)+' %<br>Précarité eau : '+fmt(z.wash)+' %');
    bornes.push([z.lat,z.lon]);
  });
  if(bornes.length>1){carte.fitBounds(bornes,{padding:[60,60]});} else if(bornes.length===1){carte.setView(bornes[0],10);}
  graphiques.cumul.data.datasets[0].data = d.cumul; graphiques.cumul.update();
  graphiques.secteurs.data.datasets[0].data = d.secteurs; graphiques.secteurs.data.datasets[0].backgroundColor = d.secteurs.map(teinteSecteur); graphiques.secteurs.update();
  graphiques.agro.data.labels = d.agro.zones;
  graphiques.agro.data.datasets = d.agro.series.map((s,i)=>({label:s.nom,data:s.valeurs,backgroundColor:/femme/i.test(s.nom)?'#D98BA8':'#5B8DB8'}));
  graphiques.agro.update();
}
const conteneur = document.getElementById('segments');
Object.keys(DATA.segments).forEach(cle=>{
  const b = document.createElement('button'); b.textContent = cle; b.dataset.cle = cle;
  b.addEventListener('click',()=>afficher(cle)); conteneur.appendChild(b);
});
afficher(DATA.defaut);
</script>
</body>
</html>
"""


def _pct(serie: pd.Series) -> float:
    return round(float(serie.mean() * 100), 1) if len(serie) else 0.0


def _charger_segment(sous_df: pd.DataFrame, zones_ref: list[str]) -> dict:
    zones = []
    for nom, groupe in sous_df.groupby("zone_nom"):
        zones.append({
            "nom": str(nom),
            "lat": float(groupe["latitude"].mean()),
            "lon": float(groupe["longitude"].mean()),
            "n": int(len(groupe)),
            "vuln": _pct(groupe["vulnerabilite_aigue_reelle"]),
            "prio": _pct(groupe["prediction_classe_ml"]),
            "wash": _pct(groupe["wash_critique"]),
        })
    cumul = sous_df["cumul_crises_jiaf"].value_counts()
    series_agro = []
    for genre in ("Femme", "Homme"):
        valeurs = []
        for zone in zones_ref:
            cible = sous_df[(sous_df["zone_nom"] == zone) & (sous_df["genre_chef_menage"] == genre)]
            valeurs.append(_pct(cible["agro_critique"]))
        series_agro.append({"nom": f"Chef de ménage : {genre.lower()}", "valeurs": valeurs})
    return {
        "n": int(len(sous_df)),
        "vuln": _pct(sous_df["vulnerabilite_aigue_reelle"]),
        "nb_vuln": int(sous_df["vulnerabilite_aigue_reelle"].sum()),
        "prio": _pct(sous_df["prediction_classe_ml"]),
        "nb_prio": int(sous_df["prediction_classe_ml"].sum()),
        "taille": round(float(sous_df["taille_menage"].mean()), 1) if len(sous_df) else 0.0,
        "charge": _pct(sous_df["ratio_personnes_charge"]),
        "zones": zones,
        "cumul": [int(cumul.get(i, 0)) for i in range(5)],
        "secteurs": [
            _pct(sous_df["secal_critique"]),
            _pct(sous_df["wash_critique"]),
            _pct(sous_df["ame_critique"]),
            _pct(sous_df["agro_critique"]),
        ],
        "agro": {"zones": zones_ref, "series": series_agro},
    }


def _lire_asset(nom: str) -> str:
    """Bibliothèque embarquée dans le HTML pour un usage hors connexion."""
    return (Path(__file__).parent / "assets" / nom).read_text(encoding="utf-8").replace("</script", "<\\/script")


def generer_dashboard_html(df_dash: pd.DataFrame, titre: Optional[str] = None, sous_titre: Optional[str] = None) -> str:
    """Génère le dashboard décisionnel autonome (une seule page, segments filtrants côté navigateur)."""
    LOGGER.info("Génération du dashboard HTML interactif autonome...")
    if not titre or not sous_titre:
        try:
            projet = json.loads((DOSSIER_SORTIE / "projet_actif.json").read_text(encoding="utf-8"))
            titre = titre or str(projet.get("id_projet", "")).replace("_", " ") or projet.get("nom_affiche")
            sous_titre = sous_titre or " · ".join(
                str(projet[cle]) for cle in ("pays", "province_region", "axe") if projet.get(cle)
            )
        except (OSError, ValueError):
            pass
    zones_ref = sorted(df_dash["zone_nom"].dropna().unique().tolist())
    segments = {LIBELLE_TOUS: _charger_segment(df_dash, zones_ref)}
    for statut in sorted(df_dash["statut_menage"].dropna().unique()):
        segments[str(statut)] = _charger_segment(df_dash[df_dash["statut_menage"] == statut], zones_ref)

    statuts = [
        {
            "nom": str(nom),
            "vuln": _pct(groupe["vulnerabilite_aigue_reelle"]),
            "prio": _pct(groupe["prediction_classe_ml"]),
        }
        for nom, groupe in df_dash.groupby("statut_menage")
    ]
    donnees = {"defaut": LIBELLE_TOUS, "segments": segments, "statuts": statuts}

    contenu = (
        MODELE_HTML_DASHBOARD
        .replace("__LEAFLET_CSS__", _lire_asset("leaflet.css"))
        .replace("__LEAFLET_JS__", _lire_asset("leaflet.js"))
        .replace("__CHART_JS__", _lire_asset("chart.umd.min.js"))
        .replace("__TITRE__", titre or "Tableau de bord décisionnel - Enquête multisectorielle")
        .replace("__SOUS_TITRE__", sous_titre or "Vulnérabilité multisectorielle (JIAF 2.0) et pré-ciblage des ménages")
        .replace("{N_TOTAL}", f"{len(df_dash):,}".replace(",", " "))
        .replace("__DATA__", json.dumps(donnees, ensure_ascii=False))
    )
    CHEMIN_HTML_DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_HTML_DASHBOARD.write_text(contenu, encoding="utf-8")
    LOGGER.info("Dashboard HTML sauvegardé dans %s", CHEMIN_HTML_DASHBOARD)
    return contenu








