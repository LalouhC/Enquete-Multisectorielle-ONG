"""Partie 3 : analyse exploratoire (EDA) complète, utilisable sans notebook.

Le script reprend les trois analyses de ``notebooks/03_analyse.ipynb`` :
table principale, tables secondaires et analyse bivariée/multivariée. Il lit la
base SQLite en lecture seule et écrit un rapport HTML autonome dans
``outputs/analyse/``.

Usage en ligne de commande, depuis la racine du projet :
    python -m src.partie3_eda [--db outputs/enquete_ms.db] [--xlsform fichier.xlsx]
        [--profil identifiant --xlsform-profil fichier.xlsx]

Pour une autre enquête dont les variables portent d'autres noms, voir
``docs/notice_user_eda.md`` (section « Utiliser une autre enquête »).
"""
from __future__ import annotations

import argparse
import base64
import copy
import html
import io
import json
import re
import sqlite3
import sys
import textwrap
import unicodedata
from base64 import b64encode
from contextlib import ExitStack, closing, redirect_stdout
from datetime import datetime
from html import escape
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from IPython.core.interactiveshell import InteractiveShell
from IPython.display import HTML, display
from IPython.utils.capture import capture_output
from scipy.stats import chi2_contingency

RACINE_PROJET = Path(__file__).resolve().parent.parent
if str(RACINE_PROJET) not in sys.path:
    sys.path.insert(0, str(RACINE_PROJET))

from src.tech_scores import (  # noqa: E402
    calculer_empreinte_questionnaire,
    calculer_scores,
    charger_profil_questionnaire,
    proposer_correspondances,
    verifier_profil_questionnaire,
)

DB_PAR_DEFAUT = RACINE_PROJET / "outputs" / "enquete_ms.db"
DOSSIER_SORTIE = RACINE_PROJET / "outputs" / "analyse"
NOTIONS_CONTEXTE = ("status", "sexe_repondant", "age_repondant")

# Les graphiques sont capturés (format PNG intégré au HTML), sans fenêtre.
_BACKEND_INLINE = "module://matplotlib_inline.backend_inline"


def _preparer_environnement_graphique():
    from matplotlib_inline.backend_inline import configure_inline_support

    matplotlib.use(_BACKEND_INLINE, force=True)
    coque = InteractiveShell.instance()
    configure_inline_support(coque, _BACKEND_INLINE)


def formater_nombres_rapport(texte):
    def grouper(match):
        entier, decimales = match.groups()
        entier = entier.replace(",", "")
        resultat = f"{int(entier):,}".replace(",", " ")
        return resultat + ("," + decimales if decimales else "")

    texte = re.sub(r"(?<![\w./-])(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.(\d+))?(?![\w./-])", grouper, texte)
    return re.sub(r"(?<![\w./-])(-?\d+)\.(\d+)(?![\w./-])", r"\1,\2", texte)


def _resoudre_colonne(source, colonnes):
    """Retrouve la colonne de la base à partir du nom donné par l'utilisateur.

    Accepte le nom exact, le nom qualifié ``table__colonne`` ou, à défaut, le nom
    seul s'il est unique parmi les colonnes personnalisées de la base.
    """
    colonnes = list(colonnes)
    if source in colonnes:
        return source
    cible = str(source).strip().casefold()
    for test in (
        lambda c: c.casefold() == cible,
        lambda c: c.casefold().endswith("__" + cible),
    ):
        trouvees = [c for c in colonnes if test(c)]
        if len(trouvees) == 1:
            return trouvees[0]
        if len(trouvees) > 1:
            raise ValueError(
                f"La variable '{source}' existe dans plusieurs tables : {', '.join(trouvees)}. "
                "Indiquez le nom qualifié table__colonne."
            )
    raise ValueError(f"La variable '{source}' est introuvable dans la base (aucune colonne de ce nom).")


def _appliquer_contexte(df, contexte):
    """Associe statut, sexe et âge du répondant aux variables de la base si elles sont renommées."""
    df = df.copy()
    inconnues = set(contexte) - set(NOTIONS_CONTEXTE)
    if inconnues:
        raise ValueError(f"Notion de contexte inconnue : {sorted(inconnues)}. Attendu : {list(NOTIONS_CONTEXTE)}.")
    for notion, source in contexte.items():
        df[notion] = df[_resoudre_colonne(source, df.columns)]
    if df["status"].isna().all():
        raise ValueError(
            "Aucun statut de ménage n'est renseigné. Si la variable porte un autre nom, "
            "indiquez-la dans le profil (clé « contexte »)."
        )
    return df


def _resoudre_profil(profil, df):
    profil = copy.deepcopy(profil)
    for notion, details in profil["correspondances"].items():
        if details.get("validee") is True:
            try:
                details["source"] = _resoudre_colonne(details["source"], df.columns)
            except ValueError as erreur:
                raise ValueError(f"Profil, notion '{notion}' : {erreur}") from erreur
    return profil


def _trouver_xlsform():
    """XLSForm du questionnaire actif : data/ en priorité, sinon le questionnaire de démonstration."""
    for dossier in ("data", "data_test"):
        fichiers = sorted((RACINE_PROJET / dossier).glob("*.xlsx"))
        fichiers = [f for f in fichiers if not f.name.startswith("~$")]
        if len(fichiers) == 1 or (dossier == "data_test" and fichiers):
            return fichiers[0]
    raise FileNotFoundError("Aucun questionnaire XLSForm trouvé dans data/ ou data_test/.")


def analyser_univarie(db_path, chemin_xlsform):
    """Analyse univariée de la table principale et des tables secondaires ; retourne deux HTML."""
    racine_projet = RACINE_PROJET
    db_path = Path(db_path)

    conn = sqlite3.connect(db_path)
    df_data = pd.read_sql("SELECT * FROM META_ENQUETE", conn)
    conn.close()
    df_survey = pd.read_excel(chemin_xlsform, sheet_name="survey")
    print(f"✅ Données chargées : {len(df_data)} lignes et {len(df_data.columns)} colonnes.")

    # --- LISTES D'EXCLUSION ÉLARGIES ---
    COLONNES_EXCLUES_TECHNIQUES = ['id', 'uuid', 'index', 'jeton', 'token', 'key', '_id', '_uuid']
    MOTS_CLES_EXCLUS_TEMPORELS = ['start', 'end', 'today', 'deviceid', 'subscriberid', 'simserial', 'phonenumber', 'date', 'heure']


    # ==========================================
    # 2. PROPAGATION ROBUSTE DES GROUPES ET TRADUCTION
    # ==========================================
    def preparer_regles_survey(df_survey):
        lignes_traitees = []
        pile_groupes = []
    
        for _, row in df_survey.iterrows():
            col_type = str(row.get('type', ''))
            col_name = row.get('name')
            relevant_actuel = row.get('relevant')
        
            if col_type.startswith('begin_group') or col_type.startswith('begin group'):
                pile_groupes.append(relevant_actuel)
                continue
            elif col_type.startswith('end_group') or col_type.startswith('end group'):
                if pile_groupes:
                    pile_groupes.pop()
                continue
            
            if pd.notna(col_name):
                tous_les_relevant = []
                for g_rel in pile_groupes:
                    if pd.notna(g_rel) and str(g_rel).strip():
                        tous_les_relevant.append(str(g_rel).strip())
            
                if pd.notna(relevant_actuel) and str(relevant_actuel).strip():
                    tous_les_relevant.append(str(relevant_actuel).strip())
                
                combined_relevant = " & ".join([f"({r})" for r in tous_les_relevant]) if tous_les_relevant else None
            
                row_dict = row.to_dict()
                row_dict['relevant_combine'] = combined_relevant
                lignes_traitees.append(row_dict)
            
        return pd.DataFrame(lignes_traitees)


    def traduire_relevant_en_pandas(relevant_expr):
        if pd.isna(relevant_expr) or not str(relevant_expr).strip():
            return None
        
        expr_pandas = str(relevant_expr)
    
        if "selected(" in expr_pandas:
            match = re.search(r"selected\(\s*\${([^}]+)}\s*,\s*'([^']+)'\)", expr_pandas)
            if match:
                col, val = match.groups()
                expr_pandas = f"df_data['{col}'] == '{val}'"
    
        expr_pandas = re.sub(r'\$\{([^}]+)\}', r"df_data['\1']", expr_pandas)
        expr_pandas = expr_pandas.replace(' and ', ' & ').replace(' or ', ' | ')
    
        return expr_pandas


    def rendre_relevant_lisible(expr_brute):
        """Transforme une expression XLSForm brute en phrase claire et compréhensible."""
        if pd.isna(expr_brute) or not str(expr_brute).strip():
            return ""
    
        texte = str(expr_brute).strip()
    
        # Nettoyage récursif des parenthèses englobantes
        while texte.startswith('(') and texte.endswith(')'):
            texte = texte[1:-1].strip()
        
        texte = re.sub(r'\$\{([^}]+)\}', r'\1', texte)
        texte = texte.replace('selected(', '').replace(')', '')
    
        if ',' in texte:
            parts = [p.strip().replace("'", "").replace('"', '') for p in texte.split(',')]
            if len(parts) == 2:
                return f"La question s'applique si la variable '{parts[0]}' vaut '{parts[1]}'"
        elif '==' in texte:
            parts = [p.strip().replace("'", "").replace('"', '') for p in texte.split('==')]
            if len(parts) == 2:
                return f"La question s'applique si la variable '{parts[0]}' vaut '{parts[1]}'"
            
        return f"Condition : {texte}"


    # ==========================================
    # 3. MOTEUR D'ANALYSE UNIVARIÉE INTELLIGENT
    # ==========================================
    def executer_eda_univariee(df_data, df_survey_clean):
        total_global = len(df_data)
        colonnes_xlsform = set(df_survey_clean['name'].dropna().tolist())
        colonnes_orphelines = list(set(df_data.columns) - colonnes_xlsform)
    
        for _, row in df_survey_clean.iterrows():
            col_name = row.get('name')
            col_type = str(row.get('type'))
            relevant_rule = row.get('relevant_combine')
        
            if pd.isna(col_name) or col_name not in df_data.columns:
                continue
            
            if any(kw in col_name.lower() for kw in COLONNES_EXCLUES_TECHNIQUES + MOTS_CLES_EXCLUS_TEMPORELS):
                continue
            
            df_cible = df_data.copy()
            filtre_pandas = traduire_relevant_en_pandas(relevant_rule)
        
            total_eligible = total_global
            masque_valide = True
        
            if filtre_pandas:
                try:
                    mask = eval(filtre_pandas)
                    df_cible = df_data[mask]
                    total_eligible = len(df_cible)
                except Exception as e:
                    masque_valide = False
                    total_eligible = 0 

            print(f"\n==================================================")
            print(f"🔍 Analyse : {col_name} (Type XLSForm : {col_type})")
            print(f"--------------------------------------------------")
        
            if filtre_pandas and masque_valide:
                print(f"📌 Conditionnement : {rendre_relevant_lisible(relevant_rule)}")
                print(f"   - Éligibles : {total_eligible} / {total_global} lignes")
            elif filtre_pandas and not masque_valide:
                print(f"📌 Conditionnement : {relevant_rule}")
                print(f"   - ⚠️ Erreur d'évaluation du filtre - Vérifiez la syntaxe")
            
            if total_eligible == 0 and filtre_pandas:
                print("⚠️ Aucun enregistrement ou échec du filtre éligible.")
                continue
            
            # Les remarques et commentaires restent du texte même avec peu de valeurs distinctes.
            libelle_question = str(row.get('label', '')).casefold()
            texte_libre = any(mot in f'{col_name} {libelle_question}' for mot in ('comment', 'remarque', 'observation', 'note'))

            # --- INFÉRENCE INTELLIGENTE DES TYPES ---
            if col_type == 'text' and not texte_libre:
                series_val = df_cible[col_name].dropna()
                nb_uniques = series_val.nunique()
                if 0 < nb_uniques <= 6:
                    print(f"💡 [Inférence] Type 'text' converti en select_one (faible cardinalité : {nb_uniques} valeurs uniques).")
                    col_type = 'select_one_inferred'

            # --- 1. STATISTIQUES NUMÉRIQUES ---
            if col_type.startswith('integer') or col_type.startswith('decimal'):
                nb_nuls = df_cible[col_name].isnull().sum()
                print(f"📊 Statistiques Numériques (Valeurs manquantes : {nb_nuls}) :")
                stats = df_cible[col_name].describe()[['mean', 'std', 'min', '50%', 'max']]
                stats.index = ['Moyenne', 'Écart-type', 'Minimum', 'Médiane', 'Maximum']
                print(stats.round(2).to_string(float_format=lambda valeur: f'{valeur:,.2f}'.replace(',', ' ').replace('.', ',')))
            
            # --- 2. TABLEAUX DE FRÉQUENCES (CATÉGORIELS) ---
            elif col_type.startswith('select_one') or col_type.startswith('select_multiple') or col_type == 'select_one_inferred':
                freq = df_cible[col_name].value_counts(dropna=False)
                freq_pct = (freq / total_eligible) * 100
            
                resume = pd.DataFrame({
                    'Effectif': freq.map(lambda valeur: f'{int(valeur):,}'.replace(',', ' ')),
                    'Pourcentage (%)': freq_pct.map(lambda valeur: f'{valeur:.2f}'.replace('.', ',') + '%')
                })
            
                resume.index = ['NaN (non concernés)' if pd.isna(x) else str(x) for x in resume.index]
            
                total_effectif = int(freq.sum())
                total_pct = (total_effectif / total_eligible) * 100 if total_eligible > 0 else 0
                df_total = pd.DataFrame({
                    'Effectif': [f'{total_effectif:,}'.replace(',', ' ')],
                    'Pourcentage (%)': [f'{total_pct:.2f}'.replace('.', ',') + '%']
                }, index=['TOTAL'])
            
                print(f"📋 Tableau de fréquences (Total catégories : {len(freq)}) :")
                if len(freq) > 20:
                    print(pd.concat([resume.head(25), df_total]).to_string())
                else:
                    print(pd.concat([resume, df_total]).to_string())

            # --- 3. NLP POUR LES TEXTES LIBRES LONGS ---
            elif col_type == 'text':
                series_text = df_cible[col_name].dropna().astype(str)
                series_text = series_text[series_text.str.strip() != '']
                print(f"📝 Analyse NLP / Texte libre ({len(series_text)} réponses) :")
            
                if len(series_text) > 0:
                    longueurs_mots = series_text.apply(lambda x: len(x.split()))
                    longueurs_car = series_text.apply(len)
                    print(f"   - Longueur moyenne : {longueurs_mots.mean():.1f} mots ({longueurs_car.mean():.1f} caractères)")
                
                    stopwords_fr = {'le', 'la', 'les', 'un', 'une', 'des', 'et', 'en', 'à', 'de', 'du', 'au', 'aux', 'que', 'qui', 'dans', 'sur', 'par', 'pour', 'avec', 'pas', 'plus', 'sont', 'est', 'ont', 'nous', 'vous', 'ils', 'elles', 'leur', 'leurs', 'son', 'sa', 'ses', 'ce', 'cette', 'ces', 'mais', 'ou', 'donc', 'or', 'ni', 'car', 'etre', 'avoir', 'suis', 'es', 'sommes', 'etes', 'sont', 'ai', 'as', 'avons', 'avez', 'ont', 'tout', 'tous', 'toute', 'toutes', 'faire', 'fait'}
                
                    tous_les_mots = " ".join(series_text).lower()
                    mots_propres = re.findall(r'\b[a-zA-Zàâäéèêëïîôöùûüç]{4,}\b', tous_les_mots)
                    mots_filtres = [m for m in mots_propres if m not in stopwords_fr]
                
                    top_mots = pd.Series(mots_filtres).value_counts().head(5)
                    print(f"   - Top mots significatifs : {dict(top_mots)}")
                
                    print(f"   - Top 10 des verbatims / commentaires les plus fréquents (extraits) :")
                    top_commentaires = series_text.value_counts().head(10)
                    for comm, count in top_commentaires.items():
                        print(f"     * ({count}x) \"{comm}\'")
                else:
                    print("   - Aucune réponse textuelle enregistrée.")

        # --- 4. TRAITEMENT AUTOMATIQUE DES COLONNES DE NETTOYAGE (ex: duree_minutes) ---
        print(f"\n==================================================")
        print(f"🔍 ANALYSE DES COLONNES CALCULÉES / NETTOYAGE (HORS XLSFORM)")
        print(f"==================================================")
    
        for col_name in colonnes_orphelines:
            if any(kw in col_name.lower() for kw in COLONNES_EXCLUES_TECHNIQUES):
                continue
            
            if pd.api.types.is_numeric_dtype(df_data[col_name]):
                print(f"\n📊 Statistiques Numériques (Calculée) : {col_name}")
                nb_nuls = df_data[col_name].isnull().sum()
                print(f"   - Valeurs manquantes : {nb_nuls}")
                stats = df_data[col_name].describe()[['mean', 'std', 'min', '50%', 'max']]
                stats.index = ['Moyenne', 'Écart-type', 'Minimum', 'Médiane', 'Maximum']
                print(stats.round(2).to_string(float_format=lambda valeur: f'{valeur:,.2f}'.replace(',', ' ').replace('.', ',')))
            else:
                print(f"\n📋 Analyse Catégorielle (Calculée) : {col_name}")
                freq = df_data[col_name].value_counts(dropna=False)
                freq_pct = (freq / total_global) * 100
                resume = pd.DataFrame({
                    'Effectif': freq.map(lambda valeur: f'{int(valeur):,}'.replace(',', ' ')),
                    'Pourcentage (%)': freq_pct.map(lambda valeur: f'{valeur:.2f}'.replace('.', ',') + '%')
                })
                resume.index = ['NaN (non concernés)' if pd.isna(x) else str(x) for x in resume.index]
                print(resume.head(10).to_string())

    # ==========================================
    # 4. LANCEMENT DU MOTEUR
    # ==========================================
    df_survey_clean = preparer_regles_survey(df_survey)
    def formater_nombres_fr(texte):
        def grouper(match):
            entier, decimales = match.groups()
            entier = entier.replace(',', '')
            return f'{int(entier):,}'.replace(',', ' ') + (',' + decimales if decimales else '')

        texte = re.sub(r'(?<![\w./-])(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.(\d+))?(?![\w./-])', grouper, texte)
        return re.sub(r'(?<![\w./-])(-?\d+)\.(\d+)(?![\w./-])', r'\1,\2', texte)


    def construire_rapport_univ_principal_html(sortie_console):
        styles = (
            '<style>.eda-report{font-family:Arial,sans-serif;color:#243447;max-width:1100px}'
            '.eda-report h1{border-bottom:2px solid #4C78A8;padding-bottom:.4rem}'
            '.eda-report details{border:1px solid #d7e0e8;border-radius:8px;margin:.6rem 0;background:#fff}'
            '.eda-report summary{cursor:pointer;padding:.75rem 1rem;font-weight:700;background:#edf3f8}'
            '.eda-report pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:1rem;margin:0;font:.88rem/1.45 Consolas,monospace}'
            '.eda-risk{color:#b22222;background:#fff1f0;border-left:4px solid #b22222;padding:.7rem 1rem;font-weight:700}'
            '.eda-risk-inline{color:#b22222;font-weight:700}'
            '.eda-report details .eda-risk,.eda-report details .eda-note{margin:.6rem 1rem}'
            '</style>'
        )
        texte = formater_nombres_fr(sortie_console)
        alertes_par_variable = {}
        if 'code_initial_renseigne' in df_data.columns and 'code_jeton' in df_data.columns:
            historique = df_data['code_initial_renseigne'].astype('string').str.contains('code initial', case=False, na=False)
            jetons = df_data['code_jeton'].dropna().astype('string').str.strip()
            doublons_restants = int(jetons.duplicated(keep=False).sum())
            jetons_manquants = int(df_data['code_jeton'].isna().sum())
            modifies = int(historique.sum())
            if modifies or doublons_restants or jetons_manquants:
                alertes_par_variable.setdefault('code_initial_renseigne', []).append(
                    '<p class="eda-risk">⚠ Contrôle des jetons : '
                    f'{formater_nombres_fr(str(modifies))} régénérés après détection de doublons ; '
                    f'{formater_nombres_fr(str(doublons_restants))} doublon(s) résiduel(s) ; '
                    f'{formater_nombres_fr(str(jetons_manquants))} identifiant(s) manquant(s).</p>'
                )
        if 'duree_minutes' in df_data.columns:
            durees_manquantes = int(df_data['duree_minutes'].isna().sum())
            if durees_manquantes:
                fins_avant_debut = 0
                if {'heure_debut', 'heure_fin'}.issubset(df_data.columns):
                    debut = pd.to_datetime(df_data['heure_debut'], errors='coerce')
                    fin = pd.to_datetime(df_data['heure_fin'], errors='coerce')
                    fins_avant_debut = int((fin < debut).sum())
                cause = (
                    f'{formater_nombres_fr(str(fins_avant_debut))} fin(s) antérieure(s) au début'
                    if fins_avant_debut == durees_manquantes
                    else f'{formater_nombres_fr(str(fins_avant_debut))} fin(s) antérieure(s) au début sur '
                         f'{formater_nombres_fr(str(durees_manquantes))} durée(s) manquante(s)'
                )
                if fins_avant_debut == durees_manquantes:
                    libelle_duree = 'durée manquante' if durees_manquantes == 1 else 'durées manquantes'
                    verbe_duree = 'correspond' if durees_manquantes == 1 else 'correspondent'
                    alertes_par_variable.setdefault('duree_minutes', []).append(
                        f'<p class="eda-note"><em>{formater_nombres_fr(str(durees_manquantes))} {libelle_duree} {verbe_duree} à une heure de fin antérieure à l’heure de début ; les durées négatives ne sont pas retenues.</em></p>'
                    )
                else:
                    alertes_par_variable.setdefault('duree_minutes', []).append(
                        f'<p class="eda-risk">⚠ Durée non calculable : {cause}.</p>'
                    )
        if 'remarques_enquete' in df_data.columns:
            commentaires = df_data['remarques_enquete'].dropna()
            numeriques = pd.to_numeric(commentaires, errors='coerce')
            type_remarque = df_survey.loc[df_survey['name'].astype(str).eq('remarques_enquete'), 'type']
            if not commentaires.empty and not type_remarque.empty and str(type_remarque.iloc[0]).startswith('text') and numeriques.notna().all():
                alertes_par_variable.setdefault('remarques_enquete', []).append(
                    '<p class="eda-risk">⚠ Le champ de remarques est déclaré en texte dans le XLSForm, '
                    'mais toutes les valeurs conservées dans cette base sont numériques. '
                    'Vérifier le nettoyage et recharger les commentaires depuis le CSV brut.</p>'
                )
        motif_titres = re.compile(
            r'(?m)^(?:🔍 Analyse : (?P<question>.+)|(?:📊 Statistiques Numériques|📋 Analyse Catégorielle) \(Calculée\) : (?P<calculee>.+))$'
        )
        reperes = list(motif_titres.finditer(texte))
        sections = []
        alertes_placees = set()
        if reperes:
            if texte[:reperes[0].start()].strip():
                sections.append(f'<details><summary>Contexte de l’analyse</summary><pre>{html.escape(texte[:reperes[0].start()].strip())}</pre></details>')
            for index, repere in enumerate(reperes):
                fin = reperes[index + 1].start() if index + 1 < len(reperes) else len(texte)
                contenu = texte[repere.end():fin]
                contenu = re.split(r'\n=+\n🔍 ANALYSE DES COLONNES CALCULÉES', contenu)[0]
                contenu = re.sub(r'\s*=+\s*$', '', contenu).strip()
                calculee = repere.group('calculee')
                nom_variable = (calculee or repere.group('question')).split(' (Type XLSForm')[0].strip()
                titre = html.escape(f'{calculee} (colonne calculée)' if calculee else repere.group('question'))
                contenu_html = html.escape(contenu)
                contenu_html = contenu_html.replace('\x1b[91m', '<span class="eda-risk-inline">').replace('\x1b[0m', '</span>')
                alertes_variable = ''.join(alertes_par_variable.get(nom_variable, []))
                alertes_placees.add(nom_variable)
                sections.append(f'<details><summary>{titre}</summary><pre>{contenu_html}</pre>{alertes_variable}</details>')
        else:
            sections.append(f'<details open><summary>Rapport détaillé</summary><pre>{html.escape(texte)}</pre></details>')
        alertes_non_placees = ''.join(
            alerte for variable, alertes in alertes_par_variable.items()
            if variable not in alertes_placees for alerte in alertes
        )
        return f'{styles}<main class="eda-report"><h1>Analyse univariée de la table principale</h1>{alertes_non_placees}{"".join(sections)}</main>'


    sortie_principale = io.StringIO()
    with redirect_stdout(sortie_principale):
        executer_eda_univariee(df_data, df_survey_clean)
    html_principal = construire_rapport_univ_principal_html(sortie_principale.getvalue())
    tables_secondaires = [
        "STATUT_MENAGE",
        "COMPOSITION_MENAGE",
        "VULNERABILITE_SANTE",
        "ECONOMIE_REVENU",
        "SECURITE_ALIMENTAIRE",
        "BIENS_AME",
        "WASH_EAU",
        "AGRICULTURE",
        "PROTECTION"
    ]

    COLONNES_EXCLUES_TECHNIQUES = ['id', 'uuid', 'index', 'jeton', 'token', 'key', '_id', '_uuid', 'id_menage', 'parent_index', '_parent_index']
    MOTS_CLES_EXCLUS_TEMPORELS = ['start', 'end', 'today', 'deviceid', 'subscriberid', 'simserial', 'phonenumber', 'date', 'heure', 'timestamp']
    recommandations_conditions = None
    for base in [racine_projet, Path.cwd(), *Path.cwd().parents]:
        chemin_edna = base / 'outputs' / 'edna_mode_capit.json'
        if chemin_edna.is_file():
            with chemin_edna.open(encoding='utf-8') as fichier_edna:
                historique_edna = json.load(fichier_edna)
            rapports_edna = historique_edna if isinstance(historique_edna, list) else [historique_edna]
            for rapport in reversed(rapports_edna):
                recommandations = rapport.get('capitalisation_edna_mode', {}).get('recommandations_conditions_analyse') if isinstance(rapport, dict) else None
                if recommandations:
                    recommandations_conditions = recommandations
                    break
            if recommandations_conditions:
                break
    if recommandations_conditions is None:
        raise KeyError('Aucune recommandation d\u2019analyse n\u2019est enregistr\u00e9e dans outputs/edna_mode_capit.json.')


    def mettre_chiffre_rouge(valeur):
        return f'\033[91m{valeur}\033[0m'


    def afficher_alerte_coherence(message):
        print(f'\n\033[91m\U0001f6a8 Alerte de coh\u00e9rence : {message}\033[0m\n')


    def normaliser_reponse(valeur):
        texte = unicodedata.normalize('NFKD', str(valeur).replace(chr(8217), ' ').replace(chr(39), ' ')).encode('ascii', 'ignore').decode('ascii').lower()
        return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9_]+', ' ', texte)).strip()


    def preparer_choix(df_choices):
        choix_par_liste = {}
        for _, choix in df_choices.dropna(subset=['list_name', 'name']).iterrows():
            nom_liste = str(choix['list_name']).strip()
            nom = str(choix['name']).strip()
            label = str(choix.get('label', nom)).strip()
            if not nom_liste or not nom:
                continue
            aliases = {normaliser_reponse(nom), normaliser_reponse(label)}
            aliases.discard('')
            choix_par_liste.setdefault(nom_liste, []).append({
                'name': nom,
                'label': label if label and label.lower() != 'nan' else nom,
                'aliases': aliases
            })
        for choix_liste in choix_par_liste.values():
            choix_liste.sort(key=lambda choix: max(map(len, choix['aliases'])), reverse=True)
            motifs = [(re.compile(r'(?<!\w)' + re.escape(alias) + r'(?!\w)'), choix['name'])
                      for choix in choix_liste for alias in choix['aliases']]
            motifs.sort(key=lambda element: len(element[0].pattern), reverse=True)
            choix_liste.append({'_motifs': motifs})
        return choix_par_liste


    def extraire_choix_multiples(reponse, choix_liste):
        texte = normaliser_reponse(reponse)
        if not texte or texte == 'nan':
            return set()
        selectionnes = set()
        positions_occupees = []
        motifs = choix_liste[-1].get('_motifs', [])
        for motif, nom in motifs:
            for match in motif.finditer(texte):
                if any(match.start() < fin and match.end() > debut for debut, fin in positions_occupees):
                    continue
                selectionnes.add(nom)
                positions_occupees.append((match.start(), match.end()))
        return selectionnes


    def inferer_type_texte(series, choix_par_liste):
        reponses = series.dropna().astype(str).str.strip()
        reponses = reponses[reponses.ne('')].map(normaliser_reponse).value_counts()
        if reponses.empty:
            return None, None

        meilleurs = []
        for nom_liste, choix_liste in choix_par_liste.items():
            alias_vers_choix = {alias: choix['name'] for choix in choix_liste[:-1] for alias in choix['aliases']}
            couverture_simple = sum(n for reponse, n in reponses.items() if reponse in alias_vers_choix) / reponses.sum()
            if couverture_simple >= 0.8:
                meilleurs.append((couverture_simple, 'select_one_inferred', nom_liste))
                continue
            if len(reponses) > 500:
                continue
            parsees = [(reponse, n, extraire_choix_multiples(reponse, choix_liste)) for reponse, n in reponses.items()]
            couverture_multi = sum(n for _, n, selections in parsees if selections) / reponses.sum()
            part_multi = sum(n for _, n, selections in parsees if len(selections) >= 2) / reponses.sum()
            if couverture_multi >= 0.8 and part_multi >= 0.2:
                meilleurs.append((couverture_multi + part_multi, 'select_multiple_inferred', nom_liste))
        if not meilleurs:
            return None, None
        _, type_inferre, nom_liste = max(meilleurs)
        return type_inferre, nom_liste


    def evaluer_relevant(expression, dataframe, df_survey_clean, choix_par_liste):
        texte = str(expression)
        colonnes_survey = {
            str(row['name']): str(row.get('type', ''))
            for _, row in df_survey_clean.iterrows() if pd.notna(row.get('name'))
        }
        masques_locaux = {}

        def traduire_selected(match):
            colonne, _, valeur = match.groups()
            if colonne not in dataframe.columns:
                raise KeyError(f"La variable relevant '{colonne}' est absente des tables jointes.")
            type_question = colonnes_survey.get(colonne, '')
            nom_liste = type_question.split()[-1] if type_question.startswith('select_one ') else None
            choix = next(
                (item for item in choix_par_liste.get(nom_liste, [])[:-1] if item['name'] == valeur),
                None
            )
            valeurs_attendues = {normaliser_reponse(valeur)}
            if choix:
                valeurs_attendues.update(choix['aliases'])
            nom_masque = f'relevant_{len(masques_locaux)}'
            masques_locaux[nom_masque] = dataframe[colonne].map(normaliser_reponse).isin(valeurs_attendues)
            return '@' + nom_masque
        texte = re.sub(
            r"selected\(\s*\$\{([^}]+)\}\s*,\s*(['\"])(.*?)\2\s*\)",
            traduire_selected, texte
        )
        texte = re.sub(r'\$\{([^}]+)\}', lambda m: '`' + m.group(1) + '`', texte)
        texte = re.sub(r'\band\b', '&', texte)
        texte = re.sub(r'\bor\b', '|', texte)
        resultat = dataframe.eval(texte, engine='python', local_dict=masques_locaux)
        if not isinstance(resultat, pd.Series):
            return pd.Series(bool(resultat), index=dataframe.index)
        return resultat.reindex(dataframe.index).fillna(False).astype(bool)


    def enlever_condition_consentement(expression):
        if pd.isna(expression) or not str(expression).strip():
            return ''
        texte = re.sub(
            r"\(?\s*selected\(\s*\$\{volont\}\s*,\s*(['\"])oui\1\s*\)\s*\)?", '', str(expression), flags=re.IGNORECASE
        )
        texte = re.sub(r'^\s*&\s*|\s*&\s*$', '', texte)
        return re.sub(r'\(\s*\)', '', texte).strip()


    def decrire_condition(expression, df_survey_clean, choix_par_liste):
        libelles = {
            str(row['name']): str(row.get('label', row['name'])).replace('\n', ' ').strip()
            for _, row in df_survey_clean.iterrows() if pd.notna(row.get('name'))
        }
        types = {
            str(row['name']): str(row.get('type', ''))
            for _, row in df_survey_clean.iterrows() if pd.notna(row.get('name'))
        }

        def traduire_selected(match):
            nom, valeur = match.groups()
            type_question = types.get(nom, '')
            nom_liste = type_question.split()[-1] if type_question.startswith('select_one ') else None
            choix = next((c for c in choix_par_liste.get(nom_liste, [])[:-1] if c['name'] == valeur), None)
            return f"{libelles.get(nom, nom)} = {choix['label'] if choix else valeur}"

        texte = re.sub(
            r"selected\(\s*\$\{([^}]+)\}\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
            traduire_selected, expression
        )
        texte = re.sub(r'\$\{([^}]+)\}', lambda m: libelles.get(m.group(1), m.group(1)), texte)
        return texte.strip().strip('() ')


    def evaluer_condition_ajoutee(nom_variable, dataframe):
        regle = recommandations_conditions['conditions'].get(nom_variable)
        if not regle:
            return None, None
        type_regle = regle['type']
        if type_regle == 'reponse_egale':
            variable = regle['variable']
            if variable not in dataframe.columns:
                return None, None
            masque = dataframe[variable].map(normaliser_reponse).eq(normaliser_reponse(regle['valeur']))
            return masque, regle['condition']
        if type_regle == 'variable_superieure_a_zero':
            variable = regle['variable']
            if variable not in dataframe.columns:
                return None, None
            masque = pd.to_numeric(dataframe[variable], errors='coerce').gt(0)
            return masque, regle['condition']
        if type_regle == 'effectif_menage_minimum':
            if regle['groupe_age'] == 'femmes_15_49':
                colonnes = ['f_15_17', 'f_18_49']
            else:
                tranches = ['0_5', '6_24', '25_59', '5_14', '15_17'] if regle['groupe_age'] == 'enfants' else ['18_49', '50_59', 'plus60']
                colonnes = [f'{sexe}_{tranche}' for sexe in ['h', 'f'] for tranche in tranches]
            if not all(col in dataframe.columns for col in colonnes):
                return None, None
            effectif = dataframe[colonnes].apply(pd.to_numeric, errors='coerce').sum(axis=1, min_count=len(colonnes))
            return effectif.ge(regle['minimum']).fillna(False), regle['condition']
        if type_regle == 'validation_superieure':
            tranches = ['18_49', '50_59', 'plus60']
            colonnes = [f'{sexe}_{tranche}' for sexe in ['h', 'f'] for tranche in tranches]
            if nom_variable not in dataframe.columns or not all(col in dataframe.columns for col in colonnes):
                return None, None
            adultes = dataframe[colonnes].apply(pd.to_numeric, errors='coerce').sum(axis=1, min_count=len(colonnes))
            valeur = pd.to_numeric(dataframe[nom_variable], errors='coerce')
            valide = valeur.isna() | adultes.isna() | valeur.le(adultes)
            return valide, regle['condition']
        raise ValueError(f"Type de condition recommandée non pris en charge : {type_regle}")


    def figure_en_html(figure, texte_alternatif):
        tampon = io.BytesIO()
        figure.savefig(tampon, format='png', dpi=120, bbox_inches='tight')
        plt.close(figure)
        image = base64.b64encode(tampon.getvalue()).decode('ascii')
        texte_alternatif = html.escape(texte_alternatif, quote=True)
        return f'<img src="data:image/png;base64,{image}" alt="{texte_alternatif}" style="display:block;width:100%;height:auto">'


    def formater_entier_fr(valeur):
        return f'{int(valeur):,}'.replace(',', ' ')


    def formater_pourcentage_fr(valeur, decimales=2):
        return f'{float(valeur):.{decimales}f}'.replace('.', ',') + '%'


    def afficher_repartition_sociodemographique(df_contexte, df_meta, df_survey_clean, choix_par_liste):
        donnees = df_contexte.copy()
        if 'volont' in df_meta.columns and 'volont' not in donnees.columns:
            donnees = donnees.merge(df_meta[['id_menage', 'volont']], on='id_menage', how='left')
        if 'volont' in donnees.columns:
            consentement = donnees['volont'].astype(str).str.strip().str.casefold().isin(
                ['oui', 'yes', '1', 'true']
            )
            donnees = donnees.loc[consentement].copy()
        if donnees.empty:
            return '<p>Aucun ménage consentant à représenter dans les graphiques socio-démographiques.</p>'

        libelles_par_variable = {}

        def libeller(variable, valeur):
            if variable not in libelles_par_variable:
                question = df_survey_clean.loc[df_survey_clean['name'].astype(str).eq(variable)]
                correspondances = {}
                if not question.empty:
                    type_question = str(question.iloc[0].get('type', ''))
                    match = re.match(r'^select_one\s+(\S+)', type_question)
                    if match:
                        for choix in choix_par_liste.get(match.group(1), [])[:-1]:
                            for alias in choix['aliases']:
                                correspondances.setdefault(alias, choix['label'])
                libelles_par_variable[variable] = correspondances
            cle = normaliser_reponse(valeur)
            return libelles_par_variable[variable].get(cle, str(valeur))

        sections_rapport = []

        def dessiner_categories(variable, titre):
            if variable not in donnees:
                sections_rapport.append(f'<section><h3>{html.escape(titre)}</h3><p>Variable absente : {html.escape(variable)}</p></section>')
                return
            valeurs = donnees[variable].astype('string').str.strip().replace('', pd.NA).dropna()
            if valeurs.empty:
                sections_rapport.append(f'<section><h3>{html.escape(titre)}</h3><p>Aucune réponse renseignée.</p></section>')
                return
            libelles_uniques = {valeur: libeller(variable, valeur) for valeur in valeurs.unique()}
            valeurs = valeurs.map(libelles_uniques)
            frequences = valeurs.value_counts()
            parts = frequences / frequences.sum() * 100
            resume = pd.DataFrame({'Réponse': frequences.index,
                                   'Effectif': [formater_entier_fr(n) for n in frequences.values],
                                   'Part des réponses valides': [formater_pourcentage_fr(part, 1) for part in parts.values]})
            fig, axe = plt.subplots(figsize=(9, max(3, .45 * len(frequences))))
            positions = range(len(frequences))
            barres = axe.barh(list(positions), frequences.values, color='#4C78A8')
            axe.set_yticks(list(positions), labels=frequences.index)
            axe.invert_yaxis()
            axe.set_title(f'{titre} (N={formater_entier_fr(frequences.sum())} réponses valides)')
            axe.set_xlabel('Nombre de ménages')
            axe.set_ylabel('')
            axe.set_xlim(0, max(frequences.values) * 1.35)
            for barre, effectif, part in zip(barres, frequences.values, parts.values):
                axe.text(barre.get_width(), barre.get_y() + barre.get_height() / 2,
                         f' {formater_entier_fr(effectif)} ({formater_pourcentage_fr(part, 1)})', va='center', fontsize=9)
            fig.tight_layout()
            tableau_html = resume.to_html(index=False, border=0, classes='eda-table', escape=True)
            image_html = figure_en_html(fig, f'Répartition : {titre}')
            sections_rapport.append(
                f'<section class="eda-card"><h3>{html.escape(titre)}</h3>'
                f'<p class="eda-meta">{formater_entier_fr(frequences.sum())} réponses valides</p>'
                f'<div class="eda-grid"><div>{tableau_html}</div><div>{image_html}</div></div></section>'
            )

        dessiner_categories('status', 'Statut du ménage')
        sexe = next((nom for nom in ('sexe', 'sexe_repondant') if nom in donnees), 'sexe')
        dessiner_categories(sexe, 'Sexe du répondant')

        age = next((nom for nom in ('age', 'age_repondant') if nom in donnees), 'age')
        ages = pd.to_numeric(donnees[age], errors='coerce').dropna() if age in donnees else pd.Series(dtype=float)
        if ages.empty:
            sections_rapport.append('<section class="eda-card"><h3>Âge du répondant</h3><p>Aucune réponse numérique valide.</p></section>')
        else:
            debut = int(ages.min() // 5 * 5)
            fin = int(ages.max() // 5 * 5 + 5)
            fig, axe = plt.subplots(figsize=(9, 4))
            axe.hist(ages, bins=range(debut, fin + 5, 5), color='#72A0C1', edgecolor='white')
            axe.set_title(f'Âge du répondant (N={formater_entier_fr(len(ages))} réponses valides)')
            axe.set_xlabel('Âge (années, classes de 5 ans)')
            axe.set_ylabel('Nombre de répondants')
            fig.tight_layout()
            resume_age = pd.DataFrame([{
                'Réponses valides': formater_entier_fr(len(ages)),
                'Âge moyen': f'{ages.mean():.1f} ans',
                'Âge médian': f'{ages.median():.1f} ans',
                'Minimum': f'{ages.min():.0f} ans',
                'Maximum': f'{ages.max():.0f} ans',
            }]).to_html(index=False, border=0, classes='eda-table', escape=True)
            image_html = figure_en_html(fig, 'Répartition de l’âge des répondants')
            sections_rapport.append(
                '<section class="eda-card"><h3>Âge du répondant</h3>'
                f'{resume_age}<div class="eda-chart">{image_html}</div></section>'
            )

        style = (
            '<style>.eda-report{font-family:Arial,sans-serif;color:#243447;max-width:1200px}'
            '.eda-report h2{border-bottom:2px solid #4C78A8;padding-bottom:.4rem}'
            '.eda-card{border:1px solid #d7e0e8;border-radius:8px;padding:1rem;margin:1rem 0;background:#fff}'
            '.eda-grid{display:grid;grid-template-columns:minmax(260px, .8fr) minmax(360px, 1.2fr);gap:1rem;align-items:center}'
            '.eda-chart{max-width:900px;margin:auto}.eda-table{border-collapse:collapse;width:100%}'
            '.eda-table th,.eda-table td{padding:.45rem .6rem;border-bottom:1px solid #e5eaf0;text-align:left!important;vertical-align:middle}'
            '.eda-table th{background:#edf3f8}.eda-meta,.eda-note{color:#586878;font-size:.92em}'
            '@media(max-width:760px){.eda-grid{grid-template-columns:1fr}}</style>'
        )
        rapport_html = (
            f'{style}<div class="eda-report"><h2>Profil des ménages enquêtés</h2>'
            f'<p class="eda-note">Population consentante : {formater_entier_fr(len(donnees))} ménages. '
            'Les pourcentages sont calculés parmi les réponses valides de chaque question.</p>'
            f'{"".join(sections_rapport)}</div>'
        )
        return rapport_html

    def afficher_graphique_composition_sociodemographique(donnees):
        classes = [('0–5 mois', '0_5'), ('6–24 mois', '6_24'), ('25–59 mois', '25_59'),
                   ('5–14 ans', '5_14'), ('15–17 ans', '15_17'), ('18–49 ans', '18_49'),
                   ('50–59 ans', '50_59'), ('60 ans et plus', 'plus60')]
        sexes = {'Hommes': 'h', 'Femmes': 'f'}
        presentes = [groupe for _, groupe in classes if any(f'{prefixe}_{groupe}' in donnees for prefixe in sexes.values())]
        if not presentes:
            return '<p>Graphique de composition non produit : les colonnes d’âge h_/f_ sont absentes.</p>'
        fig, axe = plt.subplots(figsize=(13, 5))
        positions = np.arange(len(presentes))
        largeur = .38
        for decalage, (libelle, prefixe) in zip((-largeur / 2, largeur / 2), sexes.items()):
            valeurs = []
            for groupe in presentes:
                colonne = f'{prefixe}_{groupe}'
                if colonne not in donnees or not pd.to_numeric(donnees[colonne], errors='coerce').notna().any():
                    valeurs.append(np.nan)
                else:
                    valeurs.append(pd.to_numeric(donnees[colonne], errors='coerce').sum())
            axe.bar(positions + decalage, valeurs, largeur, label=libelle,
                    color='#4C78A8' if libelle == 'Hommes' else '#E28EAA')
        noms_classes = {groupe: libelle for libelle, groupe in classes}
        axe.set_xticks(positions, labels=[noms_classes[groupe] for groupe in presentes], rotation=25, ha='right')
        axe.set_ylabel('Personnes recensées')
        axe.set_xlabel('Classe d’âge')
        axe.set_title('Composition des ménages par âge et sexe')
        axe.legend(title='')
        fig.text(.5, -.02, 'Effectifs agrégés; les classes entièrement manquantes ne sont pas tracées.', ha='center', fontsize=9)
        fig.tight_layout()
        style = (
            '<style>.eda-report{font-family:Arial,sans-serif;color:#243447;max-width:1200px}'
            '.eda-card{border:1px solid #d7e0e8;border-radius:8px;padding:1rem;margin:1rem 0;background:#fff}'
            '.eda-note{color:#586878;font-size:.92em}.eda-chart{max-width:900px;margin:auto}</style>'
        )
        note = '<p class="eda-note">Une tranche sans barre correspond à un effectif nul dans les données chargées.</p>'
        return (
            f'{style}<div class="eda-report"><section class="eda-card"><h3>Composition des ménages par âge et sexe</h3>'
            f'<div class="eda-chart">{figure_en_html(fig, "Composition des ménages par âge et sexe")}</div>{note}</section></div>'
        )


    def afficher_composition_menage(df_cible, df_survey_clean):
        groupes = {
            'Hommes': [f'h_{tranche}' for tranche in ['0_5', '6_24', '25_59', '5_14', '15_17', '18_49', '50_59', 'plus60']],
            'Femmes': [f'f_{tranche}' for tranche in ['0_5', '6_24', '25_59', '5_14', '15_17', '18_49', '50_59', 'plus60']]
        }
        groupes = {sexe: [col for col in colonnes if col in df_cible.columns] for sexe, colonnes in groupes.items()}
        groupes = {sexe: colonnes for sexe, colonnes in groupes.items() if colonnes}
        colonnes_age = [col for colonnes in groupes.values() for col in colonnes]
        colonnes_total = [col for col in ['nb_personnes', 'nb_personne', 'nombre_personnes', 'nombre_personne', 'total_personnes', 'nb_personnes_total', 'nombre_personnes_total', 'taille_menage', 'personne'] if col in df_cible.columns]
        if not colonnes_total:
            for variantes in [['h', 'f'], ['hommes', 'femmes']]:
                if all(col in df_cible.columns for col in variantes):
                    colonnes_total = variantes
                    break

        print(f"\U0001f4ca Composition moyenne ({len(df_cible)} m\u00e9nages consentants) :")
        if colonnes_total:
            effectif_total = df_cible[colonnes_total].apply(pd.to_numeric, errors='coerce').sum(axis=1, min_count=len(colonnes_total))
            moyenne_total = effectif_total.mean()
            moyenne_affichee = f'{moyenne_total:.0f}'
            if pd.notna(moyenne_total) and moyenne_total > 20:
                moyenne_affichee = mettre_chiffre_rouge(moyenne_affichee)
            print(f'Nombre moyen total de personnes : {moyenne_affichee} (n={effectif_total.notna().sum()})')
            if moyenne_total > 20:
                afficher_alerte_coherence('La moyenne d\u00e9passe 20 personnes par m\u00e9nage. Le jeu de donn\u00e9es ne semble pas r\u00e9aliste ; les donn\u00e9es devront \u00eatre revues avec les agents MEAL afin de diagnostiquer une erreur technique, un manque de formation des agents et/ou un manque de compr\u00e9hension des enqu\u00eat\u00e9s.')
            return

        if not colonnes_age:
            return

        effectifs = df_cible[colonnes_age].apply(pd.to_numeric, errors='coerce')
        moyennes = effectifs.mean()
        moyennes_par_sexe = {sexe: moyennes[colonnes].sum() for sexe, colonnes in groupes.items()}
        enfants = [col for col in colonnes_age if re.fullmatch(r'[hf]_(0_5|6_24|25_59|5_14|15_17)', col)]
        personnes_agees = [col for col in colonnes_age if re.fullmatch(r'[hf]_plus60', col)]
        total_par_menage = effectifs.sum(axis=1, min_count=len(colonnes_age))
        moyenne_total = total_par_menage.mean()
        resume_composition = {'Nombre moyen total de personnes': moyenne_total}
        noms_moyenne_sexe = {'Femmes': 'de femmes', 'Hommes': 'd\u2019hommes'}
        for sexe in ['Femmes', 'Hommes']:
            if sexe in moyennes_par_sexe:
                resume_composition[f'Nombre moyen {noms_moyenne_sexe[sexe]}'] = moyennes_par_sexe[sexe]
        if enfants:
            resume_composition['Nombre moyen d\u2019enfants (moins de 18 ans)'] = moyennes[enfants].sum()
        if personnes_agees:
            resume_composition['Nombre moyen de personnes \u00e2g\u00e9es (60 ans et plus)'] = moyennes[personnes_agees].sum()
        resume_affiche = pd.Series(resume_composition).round(0).astype('Int64').astype('string')
        if pd.notna(moyenne_total) and moyenne_total > 20:
            resume_affiche.loc['Nombre moyen total de personnes'] = mettre_chiffre_rouge(resume_affiche.loc['Nombre moyen total de personnes'])
        print(resume_affiche.to_string())
        print(f'   - M\u00e9nages complets pour le total : {total_par_menage.notna().sum()} / {len(df_cible)}')

        if pd.notna(moyenne_total) and moyenne_total > 20:
                afficher_alerte_coherence('La moyenne d\u00e9passe 20 personnes par m\u00e9nage. Le jeu de donn\u00e9es ne semble pas r\u00e9aliste ; les donn\u00e9es devront \u00eatre revues avec les agents MEAL afin de diagnostiquer une erreur technique, un manque de formation des agents et/ou un manque de compr\u00e9hension des enqu\u00eat\u00e9s.')

        libelles = {
            str(row['name']): re.sub(r'\s+', ' ', str(row.get('label', row['name'])).replace('\n', ' ')).strip()
            for _, row in df_survey_clean.iterrows() if pd.notna(row.get('name'))
        }
        print('\U0001f4cb R\u00e9partition des tranches d\u2019\u00e2ge au sein de chaque sexe :')
        for sexe, colonnes in groupes.items():
            total_sexe = moyennes_par_sexe[sexe]
            lignes = [{
                'Tranche d\u2019\u00e2ge': libelles.get(col, col),
                'Personnes moyennes par m\u00e9nage': round(moyennes[col]),
                'Part du sexe': formater_pourcentage_fr(moyennes[col] / total_sexe * 100 if total_sexe else 0)
            } for col in colonnes]
            print(f'\n{sexe}')
            print(pd.DataFrame(lignes).to_string(index=False))


    def afficher_biens_ame(df_base, df_sec, df_survey_clean, choix_par_liste):
        lignes = []
        nombres_concernes = set()
        for _, row in df_survey_clean.iterrows():
            nom = row.get('name')
            if pd.isna(nom) or nom not in df_sec.columns:
                continue
            relevant = enlever_condition_consentement(row.get('relevant_combine'))
            eligibles = df_base
            if relevant:
                masque = evaluer_relevant(relevant, df_base, df_survey_clean, choix_par_liste)
                eligibles = df_base.loc[masque]
            nombres_concernes.add(len(eligibles))
            valeurs = pd.to_numeric(eligibles[nom], errors='coerce').dropna()
            label = re.sub(r'\s+', ' ', str(row.get('label', nom))).strip()
            if not label or label.lower() == 'nan':
                label = str(nom)
            statistiques_ame = recommandations_conditions.get('synthese_biens_ame', {}).get('statistiques', ['M\u00e9diane', 'Moyenne'])
            ligne = {'Bien': label}
            for statistique in statistiques_ame:
                valeur = valeurs.median() if normaliser_reponse(statistique) == 'mediane' else valeurs.mean()
                ligne[statistique] = '' if pd.isna(valeur) else f'{valeur:.0f}' if float(valeur).is_integer() else f'{valeur:.2f}'
            lignes.append(ligne)
        print('\n\U0001f4e6 Synth\u00e8se des biens AME : m\u00e9diane et moyenne par bien.')
        if len(nombres_concernes) == 1:
            print(f'Enqu\u00eat\u00e9s concern\u00e9s pour chaque bien : {next(iter(nombres_concernes))} / {len(df_base)}')
        else:
            print('Enqu\u00eat\u00e9s concern\u00e9s indiqu\u00e9s pour chaque bien, selon les conditions du XLSForm.')
        print(pd.DataFrame(lignes).to_string(index=False) if lignes else 'Aucun bien num\u00e9rique \u00e0 analyser.')


    def executer_eda_toutes_tables_secondaires(db_path, tables_sec_liste, df_survey_clean, df_choices):
        choix_par_liste = preparer_choix(df_choices)
        conn = sqlite3.connect(db_path)
        df_meta = pd.read_sql('SELECT * FROM META_ENQUETE', conn)
        tables_disponibles = set(pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)['name'])
        df_contexte = pd.DataFrame({'id_menage': df_meta['id_menage']})
        for table_contexte in ['MENAGE', 'COMPOSITION_MENAGE']:
            if table_contexte in tables_disponibles:
                df_table_contexte = pd.read_sql(f'SELECT * FROM {table_contexte}', conn)
                df_contexte = df_contexte.merge(df_table_contexte, on='id_menage', how='left', suffixes=('', '_contexte'))

        rapport_profil = afficher_repartition_sociodemographique(df_contexte, df_meta, df_survey_clean, choix_par_liste)
        graphiques_par_table = {}
        alertes_par_table = {}

        for nom_table in tables_sec_liste:
            print(f"\n{'=' * 60}")
            print(f"\U0001f517 ANALYSE DE LA TABLE SECONDAIRE : {nom_table}")
            print('=' * 60)
            try:
                df_sec = pd.read_sql(f'SELECT * FROM {nom_table}', conn)
            except Exception as erreur:
                print(f'\u26a0 Impossible de charger la table {nom_table} : {erreur}')
                continue

            df_joint = pd.merge(df_sec, df_meta, on='id_menage', suffixes=('', '_meta'))
            colonnes_contexte = ['id_menage'] + [col for col in df_contexte.columns if col != 'id_menage' and col not in df_joint.columns]
            df_joint = df_joint.merge(df_contexte[colonnes_contexte], on='id_menage', how='left')
            if 'volont' in df_joint.columns:
                consentement = df_joint['volont'].astype(str).str.strip().str.lower().isin(['oui', 'yes', '1', 'true'])
                df_base = df_joint.loc[consentement].copy()
                print(f"\U0001f4cc Population de base (volont = oui) : {len(df_base)} / {len(df_joint)} enqu\u00eat\u00e9s")
            else:
                df_base = df_joint.copy()
                print(f'\U0001f4cc Total des enregistrements li\u00e9s : {len(df_base)}')
            if df_base.empty:
                print('\u26a0 Aucun enregistrement dans la population analys\u00e9e.')
                continue

            alertes = []
            if nom_table == 'STATUT_MENAGE' and 'environ' in df_base:
                environ = df_base['environ'].dropna().map(normaliser_reponse)
                denominateur = len(environ)
                for libelle, masque in (
                    ('Environnement dangereux', environ.eq('environnement dangereux')),
                    ('Environnement dangereux avec promiscuité', environ.str.contains('dangereux', na=False) & environ.str.contains('promiscuite', na=False)),
                ):
                    effectif = int(masque.sum())
                    if effectif and denominateur:
                        part = effectif / denominateur * 100
                        alertes.append((
                            'environ',
                            f'<p class="eda-risk">⚠ {html.escape(libelle)} : '
                            f'{formater_entier_fr(effectif)} / {formater_entier_fr(denominateur)} '
                            f'({formater_pourcentage_fr(part)})</p>'
                        ))
            if nom_table == 'VULNERABILITE_SANTE' and {'malnut', 'malnut_charge'}.issubset(df_base.columns):
                malnutrition = df_base['malnut'].map(normaliser_reponse).eq('oui')
                non_pris_en_charge = malnutrition & df_base['malnut_charge'].map(normaliser_reponse).eq('non')
                denominateur = int(malnutrition.sum())
                effectif = int(non_pris_en_charge.sum())
                if denominateur and effectif:
                    alertes.append((
                        'malnut_charge',
                        f'<p class="eda-risk">⚠ Enfants malnutris non pris en charge : '
                        f'{formater_entier_fr(effectif)} / {formater_entier_fr(denominateur)} '
                        f'({formater_pourcentage_fr(effectif / denominateur * 100)} des enfants malnutris concernés)</p>'
                    ))
            if nom_table == 'WASH_EAU' and {'separer', 'raison'}.issubset(df_base.columns):
                separations = df_base['separer'].map(normaliser_reponse).eq('oui')
                raisons_renseignees = int(df_base['raison'].notna().sum())
                if separations.any() and raisons_renseignees == 0:
                    alertes.append((
                        'raison',
                        f'<p class="eda-risk">⚠ Aucune raison enregistrée malgré '
                        f'{formater_entier_fr(int(separations.sum()))} réponses « oui » à la séparation des sources. '
                        'Vérifier le filtre relevant du questionnaire et relancer nettoyage puis ingestion.</p>'
                    ))
            if nom_table == 'AGRICULTURE' and {'agro', 'personne'}.issubset(df_base.columns):
                personnes_agro = pd.to_numeric(df_base.loc[df_base['agro'].map(normaliser_reponse).eq('oui'), 'personne'], errors='coerce').dropna()
                if len(personnes_agro):
                    sans_personne = int(personnes_agro.eq(0).sum())
                    if sans_personne:
                        alertes.append((
                            'personne',
                            f'<p class="eda-note"><em>{formater_pourcentage_fr(sans_personne / len(personnes_agro) * 100)} des ménages '
                            f'({formater_entier_fr(sans_personne)} / {formater_entier_fr(len(personnes_agro))}) déclarent 0 personne apte aux activités agricoles '
                            'alors qu’ils pratiquent l’agriculture. À vérifier côté terrain (compréhension de la question, saisie).</em></p>'
                        ))
            if alertes:
                alertes_par_table[nom_table] = alertes

            if nom_table == 'COMPOSITION_MENAGE':
                afficher_composition_menage(df_base, df_survey_clean)
                graphiques_par_table[nom_table] = afficher_graphique_composition_sociodemographique(df_base)

            if nom_table == recommandations_conditions.get('synthese_biens_ame', {}).get('table'):
                afficher_biens_ame(df_base, df_sec, df_survey_clean, choix_par_liste)
                continue
            for _, row in df_survey_clean.iterrows():
                col_name = row.get('name')
                if pd.isna(col_name) or col_name not in df_sec.columns:
                    continue
                col_name = str(col_name)
                if any(kw in col_name.lower() for kw in COLONNES_EXCLUES_TECHNIQUES + MOTS_CLES_EXCLUS_TEMPORELS):
                    continue
                col_type = str(row.get('type', '')).lower()
                if 'date' in col_type or 'time' in col_type:
                    continue
                if nom_table == 'COMPOSITION_MENAGE' and re.fullmatch(r'[hf]_(0_5|6_24|25_59|5_14|15_17|18_49|50_59|plus60)', col_name):
                    continue

                label = row.get('label')
                label = re.sub(r'\s+', ' ', str(label)).strip() if pd.notna(label) else col_name
                if not label or label.lower() == 'nan':
                    label = col_name
                if col_name in {'loyer_depl_montant', 'loyer_auto_montant'}:
                    label = f'{label} — montant en francs congolais (CDF)'
                print(f'@@VARIABLE:{col_name}@@')
                print(f"\n{'-' * 50}")
                print(f"\U0001f50d Analyse : {label} (Type XLSForm : {col_type})")
                print('-' * 50)

                df_cible = df_base
                relevant_rule = enlever_condition_consentement(row.get('relevant_combine'))
                conditions = []
                descriptions_conditions = []
                conditions_ajoutees = []
                if relevant_rule:
                    try:
                        masque = evaluer_relevant(relevant_rule, df_cible, df_survey_clean, choix_par_liste)
                        if masque is not None:
                            conditions.append(masque)
                            descriptions_conditions.append(decrire_condition(relevant_rule, df_survey_clean, choix_par_liste))
                    except Exception as erreur:
                        print(f"\u26a0 Relevant non \u00e9valu\u00e9 ({relevant_rule}) : {erreur}. Analyse ignor\u00e9e.")
                        continue

                masque_technique, description_technique = evaluer_condition_ajoutee(col_name, df_cible)
                regle_technique = recommandations_conditions['conditions'].get(col_name)
                validation_incoherente = None
                if masque_technique is not None and regle_technique['type'] == 'validation_superieure':
                    validation_incoherente = ~masque_technique
                elif masque_technique is not None:
                    conditions.append(masque_technique)
                if description_technique:
                    descriptions_conditions.append(description_technique)
                    if masque_technique is not None and regle_technique['type'] != 'validation_superieure':
                        conditions_ajoutees.append(description_technique)

                regle_conditionnement = recommandations_conditions.get('alertes_conditionnement', {}).get(col_name)
                if regle_conditionnement:
                    variable_parent = regle_conditionnement['variable_condition']
                    lignes_parent = df_survey_clean.loc[
                        df_survey_clean['name'].astype(str).eq(variable_parent)
                    ]
                    if not lignes_parent.empty:
                        ligne_parent = lignes_parent.iloc[0]
                        relevant_parent = enlever_condition_consentement(
                            ligne_parent.get('relevant_combine')
                        )
                        if relevant_parent:
                            masque_parent = evaluer_relevant(
                                relevant_parent, df_base, df_survey_clean, choix_par_liste
                            )
                            conditions.append(masque_parent)
                            descriptions_conditions.append(
                                decrire_condition(relevant_parent, df_survey_clean, choix_par_liste)
                            )
                        regle_parent = recommandations_conditions['conditions'].get(variable_parent)
                        if regle_parent and regle_parent['type'] != 'validation_superieure':
                            masque_parent, description_parent = evaluer_condition_ajoutee(
                                variable_parent, df_base
                            )
                            if masque_parent is not None:
                                conditions.append(masque_parent)
                                descriptions_conditions.append(description_parent)
                                conditions_ajoutees.append(description_parent)

                for masque in conditions:
                    df_cible = df_cible.loc[masque]
                total_eligible = len(df_cible)
                if regle_conditionnement:
                    reponses_presentes_base = (
                        df_base[col_name].notna()
                        & df_base[col_name].astype(str).str.strip().ne('')
                    )
                    indices_eligibles = df_base.index.isin(df_cible.index)
                    reponses_dans_condition = int(
                        (reponses_presentes_base & indices_eligibles).sum()
                    )
                    reponses_hors_condition = int(
                        (reponses_presentes_base & ~indices_eligibles).sum()
                    )
                    reponses_manquantes_condition = total_eligible - reponses_dans_condition
                    if reponses_hors_condition or reponses_manquantes_condition:
                        afficher_alerte_coherence(
                            f'{col_name} : {total_eligible} enqu\u00eat\u00e9s sont concern\u00e9s apr\u00e8s application des conditions de la question parente et de la r\u00e9ponse \u00ab {regle_conditionnement["valeur_attendue"]} \u00bb \u00e0 {regle_conditionnement["variable_condition"]}; {reponses_dans_condition} r\u00e9ponses sont renseign\u00e9es parmi eux, {reponses_hors_condition} hors condition et {reponses_manquantes_condition} non renseign\u00e9es parmi les concern\u00e9s. V\u00e9rifier le relevant dans le formulaire.'
                        )
                non_concernes = len(df_base) - total_eligible
                condition_lisible = ' ; '.join(dict.fromkeys(filter(None, descriptions_conditions))) or 'Aucune condition suppl\u00e9mentaire'
                pct = total_eligible / len(df_base) * 100 if len(df_base) else 0
                print(f'Conditions attendues : {condition_lisible}')
                pct_affiche = f'{pct:.0f}%' if pct == 100 else f'{pct:.2f}%'
                print(f'   - Enqu\u00eat\u00e9s concern\u00e9s : {total_eligible} / {len(df_base)} ({pct_affiche})')
                print(f'   - Non concern\u00e9s (hors condition) : {non_concernes}')
                for condition_ajoutee in conditions_ajoutees:
                    print(f"{recommandations_conditions['label_condition_ajoutee']} : {condition_ajoutee}")
                if validation_incoherente is not None:
                    nombre_incoherents = int(validation_incoherente.loc[df_base.index].fillna(False).sum())
                    print(f"{recommandations_conditions['label_condition_ajoutee']} : {description_technique}")
                    print(f'   - Valeurs incoh\u00e9rentes (adultes en incapacit\u00e9 > adultes du m\u00e9nage) : {nombre_incoherents}')
                if total_eligible == 0:
                    print('\u26a0 Aucun enqu\u00eat\u00e9 concern\u00e9 par cette condition.')
                    continue

                serie = df_cible[col_name]
                masque_reponses_renseignees = serie.notna() & serie.astype(str).str.strip().ne('')
                non_renseignees = int(total_eligible - masque_reponses_renseignees.sum())
                print(f'R\u00e9ponses renseign\u00e9es : {int(masque_reponses_renseignees.sum())} ; non renseign\u00e9es : {non_renseignees}.')
                type_analyse = col_type
                nom_liste = None
                match_liste = re.match(r'^select_(?:one|multiple)\s+(\S+)', col_type)
                if match_liste:
                    nom_liste = match_liste.group(1)
                elif col_type == 'text':
                    type_inferre, nom_liste = inferer_type_texte(serie, choix_par_liste)
                    if type_inferre:
                        type_analyse = type_inferre
                        print(f"\U0001f4a1 Inf\u00e9rence par l\u2019onglet choices : type {type_analyse}, name {nom_liste}.")

                est_choix_multiple = type_analyse.startswith('select_multiple')
                est_choix_unique = type_analyse.startswith('select_one')
                valeur_numerique = pd.to_numeric(serie, errors='coerce')
                valeurs_renseignees = masque_reponses_renseignees
                frequences_numeriques = col_name in recommandations_conditions['repartition_frequences']
                est_numerique = (
                    'integer' in col_type or 'decimal' in col_type or
                    (not est_choix_unique and not est_choix_multiple and valeurs_renseignees.any()
                     and valeur_numerique[valeurs_renseignees].notna().all())
                )

                if est_numerique and frequences_numeriques:
                    reponses_valides = valeur_numerique[valeur_numerique.notna()]
                    if col_name in recommandations_conditions.get('alertes_oui_zero', {}):
                        nombre_zero = int(reponses_valides.eq(0).sum())
                        if nombre_zero:
                            parent = recommandations_conditions['alertes_oui_zero'][col_name]
                            afficher_alerte_coherence(
                                f'{nombre_zero} r\u00e9ponse(s) indiquent 0 fois alors que \u00ab {parent} \u00bb est oui. V\u00e9rifier une erreur technique, la coh\u00e9rence de la saisie par l\u2019enqu\u00eateur ou la compr\u00e9hension de la question par l\u2019enqu\u00eat\u00e9.'
                            )
                    print('\U0001f4ca R\u00e9partition des r\u00e9ponses : les proportions sont calcul\u00e9es parmi les r\u00e9ponses renseign\u00e9es.')
                    if not reponses_valides.empty:
                        frequences = reponses_valides.value_counts().sort_index()
                        frequences.index = [int(valeur) if float(valeur).is_integer() else valeur for valeur in frequences.index]
                        proportions = frequences / len(reponses_valides) * 100
                        resume = pd.DataFrame({
                            'Enqu\u00eat\u00e9s': [formater_entier_fr(n) for n in frequences.values],
                            'Proportion des r\u00e9ponses': [formater_pourcentage_fr(p) for p in proportions.values]
                        }, index=frequences.index)
                        print(resume.to_string())
                    continue

                if est_numerique:
                    valides = valeur_numerique.dropna()
                    unite_monetaire = ' en francs congolais (FC)' if col_name in ('revenu', 'montant_dette') else ''
                    print(f'\U0001f4ca Statistiques num\u00e9riques{unite_monetaire} (r\u00e9ponses valides : {len(valides)}, non renseign\u00e9es : {total_eligible - len(valides)}) :')
                    if not valides.empty:
                        seuil = recommandations_conditions.get('alertes_moyenne', {}).get(col_name)
                        if seuil and valides.mean() > seuil['seuil_maximum']:
                            afficher_alerte_coherence(f"Moyenne observ\u00e9e : {valides.mean():.2f}. {seuil['message']}")
                        if col_name in recommandations_conditions.get('statistiques_moyenne_seule', []):
                            moyenne = valides.mean()
                            if col_name in recommandations_conditions.get('moyennes_entieres', []):
                                print(f'Moyenne : {int(round(moyenne))}')
                            else:
                                print(f'Moyenne : {moyenne:.2f}'.replace('.', ','))
                            continue
                        stats = valides.describe()[['mean', 'std', 'min', '50%', 'max']]
                        stats.index = ['Moyenne', '\u00c9cart-type', 'Minimum', 'M\u00e9diane', 'Maximum']
                        print(stats.round(2).to_string())
                    else:
                        print('\u26a0 Aucune r\u00e9ponse num\u00e9rique valide.')
                    continue

                choix_liste = choix_par_liste.get(nom_liste, []) if nom_liste else []
                if est_choix_multiple and choix_liste:
                    selections = serie.apply(lambda valeur: extraire_choix_multiples(valeur, choix_liste) if pd.notna(valeur) else set())
                    lignes = []
                    for choix in choix_liste[:-1]:
                        effectif = sum(choix['name'] in selection for selection in selections)
                        lignes.append({'R\u00e9ponse': choix['label'], 'Enqu\u00eat\u00e9s': effectif, 'Pourcentage des concern\u00e9s': formater_pourcentage_fr(effectif / total_eligible * 100)})
                    lignes.sort(key=lambda ligne: ligne['Enqu\u00eat\u00e9s'], reverse=True)
                    tableau_choix = pd.DataFrame(lignes)
                    tableau_choix['Enqu\u00eat\u00e9s'] = tableau_choix['Enqu\u00eat\u00e9s'].map(formater_entier_fr)
                    repondants = int(selections.map(bool).sum())
                    print(f'\U0001f4cb Choix multiples : enqu\u00eat\u00e9s ayant s\u00e9lectionn\u00e9 au moins une r\u00e9ponse : {formater_entier_fr(repondants)} / {formater_entier_fr(total_eligible)}')
                    print(tableau_choix.to_string(index=False))
                    continue
                if est_choix_multiple and not choix_liste:
                    print(f"\u26a0 Liste de choix '{nom_liste}' introuvable ; les r\u00e9ponses ne peuvent pas \u00eatre d\u00e9sagr\u00e9g\u00e9es.")

                if est_choix_unique:
                    correspondance = {alias: choix['label'] for choix in choix_liste[:-1] for alias in choix['aliases']}
                    serie_affichee = serie.map(lambda valeur: None if pd.isna(valeur) or not str(valeur).strip() else correspondance.get(normaliser_reponse(valeur), str(valeur)))
                    reponses_renseignees = serie_affichee.dropna()
                    frequences = reponses_renseignees.value_counts()
                    proportions = frequences / len(reponses_renseignees) * 100 if len(reponses_renseignees) else pd.Series(0, index=frequences.index)
                    resume = pd.DataFrame({
                        'Effectif': [formater_entier_fr(n) for n in frequences.values],
                        'Pourcentage': [formater_pourcentage_fr(p) for p in proportions.values]
                    }, index=frequences.index)
                    print('\U0001f4cb Tableau de fr\u00e9quences :')
                    print(resume.to_string())
                    continue

                if col_type == 'text':
                    series_text = serie.dropna().astype(str)
                    series_text = series_text[series_text.str.strip() != '']
                    print(f'\U0001f4dd Analyse texte libre ({len(series_text)} r\u00e9ponses) :')
                    if not series_text.empty:
                        print(f"   - Longueur moyenne : {series_text.apply(lambda x: len(x.split())).mean():.1f} mots")
                        for commentaire, effectif in series_text.value_counts().head(5).items():
                            print(f'     * ({effectif}x) "{commentaire}"')
                    else:
                        print('   - Aucune r\u00e9ponse textuelle enregistr\u00e9e.')

        conn.close()
        return rapport_profil, graphiques_par_table, alertes_par_table


    # ==========================================
    # 3. LANCEMENT GLOBAL
    # ==========================================
    def formater_nombres_rapport(texte):
        def grouper(match):
            entier, decimales = match.groups()
            entier = entier.replace(',', '')
            resultat = f'{int(entier):,}'.replace(',', ' ')
            return resultat + (',' + decimales if decimales else '')

        texte = re.sub(r'(?<![\w./-])(\d{1,3}(?:,\d{3})+|\d{4,})(?:\.(\d+))?(?![\w./-])', grouper, texte)
        return re.sub(r'(?<![\w./-])(-?\d+)\.(\d+)(?![\w./-])', r'\1,\2', texte)


    def construire_rapport_univ_html(sortie_console, rapport_profil, graphiques_par_table, alertes_par_table):
        style = (
            '<style>.eda-report{font-family:Arial,sans-serif;color:#243447;max-width:1200px}'
            '.eda-report h1,.eda-report h2{border-bottom:2px solid #4C78A8;padding-bottom:.4rem}'
            '.eda-report details{border:1px solid #d7e0e8;border-radius:8px;margin:.7rem 0;background:#fff}'
            '.eda-report summary{cursor:pointer;padding:.8rem 1rem;font-weight:700;background:#edf3f8}'
            '.eda-report pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:1rem;margin:0;font: .88rem/1.45 Consolas,monospace}'
            '.eda-report .eda-detail-graph{padding:0 1rem 1rem}.eda-report .alerte,.eda-report .eda-risk{color:#b22222;font-weight:700}'
            '.eda-report .eda-risk{background:#fff1f0;border-left:4px solid #b22222;padding:.7rem 1rem;margin:.5rem 1rem}'
            '</style>'
        )
        texte = formater_nombres_rapport(sortie_console)
        bornes = list(re.finditer(r'ANALYSE DE LA TABLE SECONDAIRE\s*:\s*([^\r\n]+)', texte))
        sections = []
        if not bornes:
            sections.append(f'<details><summary>Rapport détaillé</summary><pre>{html.escape(texte)}</pre></details>')
        else:
            for index, match in enumerate(bornes):
                fin = bornes[index + 1].start() if index + 1 < len(bornes) else len(texte)
                nom_table = match.group(1).strip()
                bloc = texte[match.start():fin].strip()
                alertes_variables = {}
                for variable, alerte in alertes_par_table.get(nom_table, []):
                    alertes_variables.setdefault(variable, []).append(alerte)

                def bloc_en_html(contenu):
                    contenu_html = html.escape(contenu.strip())
                    for code, classe in (('\x1b[91m', 'alerte'), ('\x1b[93m', 'alerte'), ('\x1b[0m', '/span')):
                        balise = '</span>' if classe == '/span' else f'<span class="{classe}">'
                        contenu_html = contenu_html.replace(code, balise)
                    return f'<pre>{contenu_html}</pre>'

                morceaux = re.split(r'@@VARIABLE:([^@\r\n]+)@@', bloc)
                contenu_table = bloc_en_html(morceaux[0])
                variables_placees = set()
                for variable, contenu in zip(morceaux[1::2], morceaux[2::2]):
                    contenu_table += bloc_en_html(contenu)
                    if variable in alertes_variables:
                        contenu_table += ''.join(alertes_variables[variable])
                        variables_placees.add(variable)
                contenu_table += ''.join(
                    alerte for variable, alertes in alertes_variables.items()
                    if variable not in variables_placees for alerte in alertes
                )
                graphique = graphiques_par_table.get(nom_table, '')
                graphique_html = f'<div class="eda-detail-graph">{graphique}</div>' if graphique else ''
                sections.append(
                    f'<details><summary>{html.escape(nom_table)} — rapport détaillé</summary>'
                    f'{contenu_table}{graphique_html}</details>'
                )
        return (
            f'{style}<main class="eda-report"><h1>Analyse univariée des tables secondaires</h1>'
            f'{rapport_profil}<h2>Résultats détaillés par table</h2>{"".join(sections)}</main>'
        )


    df_choices = pd.read_excel(chemin_xlsform, sheet_name='choices')
    sortie_console = io.StringIO()
    with redirect_stdout(sortie_console):
        rapport_profil, graphiques_par_table, alertes_par_table = executer_eda_toutes_tables_secondaires(
            db_path, tables_secondaires, df_survey_clean, df_choices
        )
    html_secondaires = construire_rapport_univ_html(
        sortie_console.getvalue(), rapport_profil, graphiques_par_table, alertes_par_table
    )

    return html_principal, html_secondaires


def analyser_bivarie(db_path, identifiant_profil=None, chemin_xlsform_profil=None, correspondances_contexte=None):
    """Analyse bivariée et multivariée ; retourne le rapport HTML."""
    blocs_rapport_3 = []
    bloc_actif = {}


    def fermer_bloc():
        if bloc_actif:
            bloc_actif["capture"].__exit__(None, None, None)
            blocs_rapport_3.append((bloc_actif["titre"], bloc_actif["ouvert"], bloc_actif["sortie"]))
            bloc_actif.clear()


    def ouvrir_bloc(titre, ouvert=True):
        # Chaque bloc capture ses propres sorties pour conserver l'ordre du rapport.
        fermer_bloc()
        capture = capture_output()
        bloc_actif.update(titre=titre, ouvert=ouvert, capture=capture, sortie=capture.__enter__())


    def texte_en_html(texte):
        paragraphes = []
        for ligne in texte.splitlines():
            if not ligne.strip():
                continue
            classe = 'eda-texte'
            if ligne.startswith('\x1b[91m'):
                classe = 'eda-risk'
            elif ligne.startswith('\x1b[93m'):
                classe = 'eda-warning'
            elif ligne.startswith('- '):
                classe = 'eda-ok'
            for code in ('\x1b[91m', '\x1b[93m', '\x1b[0m'):
                ligne = ligne.replace(code, '')
            paragraphes.append(f'<p class="{classe}">{escape(formater_nombres_rapport(ligne))}</p>')
        return ''.join(paragraphes)


    def note(texte):
        # Affichée comme une sortie pour rester placée après le graphique commenté.
        paragraphes = ''.join(
            f'<p class="eda-note">{escape(formater_nombres_rapport(ligne))}</p>'
            for ligne in texte.split('\n') if ligne.strip()
        )
        display(HTML(paragraphes))


    def sortie_en_html(sortie, titre, index):
        donnees = sortie.data
        if 'text/html' in donnees:
            contenu = donnees['text/html']
            if isinstance(contenu, list):
                contenu = ''.join(contenu)
            return f'<div class="eda-table-wrap">{contenu}</div>'
        for type_image in ('image/svg+xml', 'image/png'):
            if type_image in donnees:
                contenu = donnees[type_image]
                if isinstance(contenu, str) and type_image == 'image/svg+xml':
                    contenu = contenu.encode('utf-8')
                if isinstance(contenu, bytes):
                    contenu = b64encode(contenu).decode('ascii')
                return f'<img alt="{escape(titre)} — graphique {index}" src="data:{type_image};base64,{contenu}">'
        if 'text/plain' in donnees:
            contenu = donnees['text/plain']
            if isinstance(contenu, list):
                contenu = ''.join(contenu)
            return f'<pre>{escape(str(contenu))}</pre>'
        types_disponibles = escape(', '.join(donnees))
        raise ValueError(f'Impossible d’intégrer la sortie {index} au rapport HTML : {types_disponibles}.')


    def corps_bloc(titre, capture):
        parties = []
        if capture.stdout.strip():
            parties.append(texte_en_html(capture.stdout))
        for index, sortie in enumerate(capture.outputs, start=1):
            parties.append(f'<div class="eda-output">{sortie_en_html(sortie, titre, index)}</div>')
        return ''.join(parties)


    def construire_rapport_html_bloc_3(capture_principale, blocs):
        styles = (
            '<style>.eda-report{font-family:Arial,sans-serif;color:#243447;max-width:1200px;margin:auto}'
            '.eda-report h1{border-bottom:2px solid #4C78A8;padding-bottom:.4rem}'
            '.eda-report details{border:1px solid #d7e0e8;border-radius:8px;margin:.7rem 0;background:#fff}'
            '.eda-report summary{cursor:pointer;padding:.8rem 1rem;font-weight:700;background:#edf3f8}'
            '.eda-report .eda-body{padding:.5rem 1rem 1rem}'
            '.eda-report p{margin:.4rem 0;line-height:1.5}'
            '.eda-report .eda-ok{color:#4a5a6a}'
            '.eda-report .eda-risk{color:#b22222;background:#fff1f0;border-left:4px solid #b22222;padding:.5rem .8rem;font-weight:700}'
            '.eda-report .eda-warning{color:#8a5a00;background:#fff8e5;border-left:4px solid #d9a21b;padding:.5rem .8rem;font-weight:700}'
            '.eda-report .eda-note{background:#eef5fb;border-left:4px solid #4C78A8;padding:.6rem .9rem;margin:.5rem 0}'
            '.eda-report pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:.88rem/1.45 Consolas,monospace}'
            '.eda-report .eda-output{margin:.8rem 0}'
            '.eda-report .eda-table-wrap{overflow-x:auto}'
            '.eda-report table{border-collapse:collapse}'
            '.eda-report th,.eda-report td{padding:.45rem .6rem;border-bottom:1px solid #e5eaf0;text-align:left!important;vertical-align:middle}'
            '.eda-report img{display:block;max-width:100%;height:auto;margin:.5rem auto}'
            '</style>'
        )
        sections = []
        synthese = corps_bloc('Synthèse', capture_principale)
        if synthese:
            sections.append(f'<details open><summary>Synthèse</summary><div class="eda-body">{synthese}</div></details>')
        for titre, ouvert, capture in blocs:
            contenu = corps_bloc(titre, capture)
            if contenu:
                attribut = ' open' if ouvert else ''
                sections.append(
                    f'<details{attribut}><summary>{escape(titre)}</summary><div class="eda-body">{contenu}</div></details>'
                )
        avertissements = capture_principale.stderr + ''.join(capture.stderr for _, _, capture in blocs)
        if avertissements.strip():
            sections.append(
                '<details><summary>Avertissements techniques</summary>'
                f'<div class="eda-body"><pre>{escape(avertissements)}</pre></div></details>'
            )
        return f'{styles}<main class="eda-report"><h1>Analyse bivariée et multivariée</h1>{"".join(sections)}</main>'



    with capture_output() as sortie_bivariee, ExitStack() as pile:
        pile.callback(fermer_bloc)

        sns.set_theme(style="whitegrid", context="notebook")
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial"]

        profil_actif = None
        if chemin_xlsform_profil:
            chemin_xlsform_profil = Path(chemin_xlsform_profil)
            if not chemin_xlsform_profil.is_file():
                raise FileNotFoundError(f"XLSForm introuvable : {chemin_xlsform_profil}")
            with pd.ExcelFile(chemin_xlsform_profil) as classeur_xlsform:
                questions_profil = classeur_xlsform.parse("survey")
                choix_profil = classeur_xlsform.parse("choices") if "choices" in classeur_xlsform.sheet_names else None
            suggestions = proposer_correspondances(questions_profil)
            print("Suggestions depuis les profils validés (à vérifier avant utilisation) :")
            display(pd.DataFrame(suggestions))
            if identifiant_profil:
                profil_actif = charger_profil_questionnaire(identifiant_profil)
                verifier_profil_questionnaire(profil_actif, questions_profil, choix_profil)
        elif identifiant_profil:
            raise ValueError("Choisissez aussi le XLSForm correspondant (chemin_xlsform_profil) pour vérifier le profil.")
        contexte = dict((profil_actif or {}).get("contexte", {}))
        contexte.update(correspondances_contexte or {})

        chemin_base = Path(db_path)
        tables_a_verifier = (
            "MENAGE", "META_ENQUETE", "STATUT_MENAGE", "COMPOSITION_MENAGE",
            "VULNERABILITE_SANTE", "ECONOMIE_REVENU", "SECURITE_ALIMENTAIRE",
            "BIENS_AME", "WASH_EAU", "AGRICULTURE",
        )

        requete_menages = textwrap.dedent("""
        SELECT m.id_menage,
               me.date_enquete,
               m.age AS age_repondant,
               m.sexe AS sexe_repondant,
               m.statmtr, m.decision, m.status,
               sm.herber AS lieu_hab, sm.environ,
               sm.loyer_depl_montant, sm.loyer_auto_montant,
               cm.h_0_5, cm.h_6_24, cm.h_25_59, cm.h_5_14,
               cm.h_15_17, cm.h_18_49, cm.h_50_59, cm.h_plus60,
               cm.f_0_5, cm.f_6_24, cm.f_25_59, cm.f_5_14,
               cm.f_15_17, cm.f_18_49, cm.f_50_59, cm.f_plus60,
               cm.fem_enc, cm.fem_all,
               vs.vis_ss, vs.hear_ss, vs.mob_ss, vs.cog_ss, vs.sc_ss, vs.com_ss,
               vs.observation_0, vs.adultincap, vs.hand, vs.malnut,
               er.revenu, er.montant_dette,
               sa.ressources, sa.repas_r, sa.suffisant, sa.repas_f, sa.manque, sa.repas_m,
               ba.nb_bidon, ba.nb_cass, ba.nb_bas, ba.nb_outil,
               ba.nb_couch, ba.nb_couv, ba.nb_habit_femme, ba.nb_habit_e,
               we.capacite, we.capacites, we.eau, we.separer,
               ag.agro, ag.terre, ag.outims, ag.personne, ag.eau_point, ag.asso, ag.date_agro
        FROM MENAGE m
        INNER JOIN META_ENQUETE me ON me.id_menage = m.id_menage
        LEFT JOIN STATUT_MENAGE sm ON sm.id_menage = m.id_menage
        LEFT JOIN COMPOSITION_MENAGE cm ON cm.id_menage = m.id_menage
        LEFT JOIN VULNERABILITE_SANTE vs ON vs.id_menage = m.id_menage
        LEFT JOIN ECONOMIE_REVENU er ON er.id_menage = m.id_menage
        LEFT JOIN SECURITE_ALIMENTAIRE sa ON sa.id_menage = m.id_menage
        LEFT JOIN BIENS_AME ba ON ba.id_menage = m.id_menage
        LEFT JOIN WASH_EAU we ON we.id_menage = m.id_menage
        LEFT JOIN AGRICULTURE ag ON ag.id_menage = m.id_menage
        """)

        with closing(sqlite3.connect(chemin_base.resolve().as_uri() + "?mode=ro", uri=True)) as connexion:
            connexion.execute("PRAGMA query_only = ON")
            tables_presentes = {
                ligne[0] for ligne in connexion.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            tables_absentes = sorted(set(tables_a_verifier) - tables_presentes)
            if tables_absentes:
                raise ValueError(f"Tables SQL absentes : {tables_absentes}")
            for table in tables_a_verifier:
                total, distincts = connexion.execute(
                    f'SELECT COUNT(*), COUNT(DISTINCT id_menage) FROM "{table}"'
                ).fetchone()
                if total != distincts:
                    raise ValueError(f"La clé id_menage n'est pas unique dans {table}.")
            alias_tables = {
                "META_ENQUETE": "me", "MENAGE": "m", "STATUT_MENAGE": "sm",
                "COMPOSITION_MENAGE": "cm", "VULNERABILITE_SANTE": "vs",
                "ECONOMIE_REVENU": "er", "SECURITE_ALIMENTAIRE": "sa",
                "BIENS_AME": "ba", "WASH_EAU": "we", "AGRICULTURE": "ag",
            }
            colonnes_personnalisees = []
            for table, alias in alias_tables.items():
                for info_colonne in connexion.execute(f'PRAGMA table_info("{table}")'):
                    colonne = info_colonne[1]
                    if colonne != "id_menage":
                        nom_qualifie = f"{table.lower()}__{colonne}"
                        colonne_sql = '"' + colonne.replace('"', '""') + '"'
                        alias_sql = '"' + nom_qualifie.replace('"', '""') + '"'
                        colonnes_personnalisees.append(f"{alias}.{colonne_sql} AS {alias_sql}")
            if colonnes_personnalisees:
                requete_menages = requete_menages.replace(
                    "\nFROM MENAGE m",
                    ",\n       " + ",\n       ".join(colonnes_personnalisees) + "\nFROM MENAGE m",
                    1,
                )
            df_menages_joint = pd.read_sql_query(requete_menages, connexion)

        if df_menages_joint["id_menage"].duplicated().any():
            raise ValueError("Les jointures ont créé plusieurs lignes pour un même ménage.")
        df_menages_joint = _appliquer_contexte(df_menages_joint, contexte)
        if profil_actif is not None:
            df_scores_analyse = calculer_scores(
                df_menages_joint,
                profil=_resoudre_profil(profil_actif, df_menages_joint),
            )
        elif chemin_xlsform_profil:
            df_scores_analyse = calculer_scores(df_menages_joint, verifier_colonnes=False)
        else:
            df_scores_analyse = calculer_scores(df_menages_joint)
        diagnostic_indicateurs = pd.DataFrame.from_dict(
            df_scores_analyse.attrs["diagnostic_indicateurs"], orient="index"
        )
        print(f"Base lue en lecture seule : {len(df_scores_analyse):,} ménages ; une ligne par ménage.")
        print("Scores calculés par secteur ; aucun score global intersectoriel n'est créé.")
        modalites_non_reconnues = df_scores_analyse.attrs.get("modalites_non_reconnues", {})
        if modalites_non_reconnues:
            print("Codes de réponse non traduits par le profil; vérifier les modalités :")
            display(pd.Series(modalites_non_reconnues, name="codes non traduits"))

        scores_sectoriels = {
            "Abri (score inversé pour lecture vulnérabilité)": "vulnerabilite_abri_orientee",
            "SECAL / HHS": "score_hhs_total",
            "AME/NFI": "score_ame_global",
            "WASH": "score_global_wash",
            "AGRO": "score_global_agro",
        }
        df_scores_analyse["vulnerabilite_abri_orientee"] = 11 - pd.to_numeric(
            df_scores_analyse["score_card_abri_reduit"], errors="coerce"
        )
        colonnes_scores = list(scores_sectoriels.values())
        for colonne in colonnes_scores:
            df_scores_analyse[colonne] = pd.to_numeric(df_scores_analyse[colonne], errors="coerce")

        # Les indicateurs non composites sont également croisés ; ils ne sont pas
        # fusionnés avec les scores sectoriels.
        indicateurs_a_croiser = {
            **scores_sectoriels,
            "Ratio de dépendance": "ratio_dependance",
            "Handicap WG-SS sévère": "score_handicap_wg",
            "Genre — proxy critique": "score_genre_vulnerabilite_critique",
            "Loyer payé / revenu": "ratio_loyer_revenu",
            "Revenu locatif / revenu": "ratio_revenu_locatif",
            "Dette / revenu": "ratio_dette_revenu",
        }
        COULEURS_VULNERABILITE = {
            "faible": "#2E8B57",
            "moderee": "#F2C94C",
            "critique": "#D64545",
            "neutre": "#8A96A3",
        }

        def couleur_niveau(niveau):
            texte = str(niveau).casefold()
            if any(mot in texte for mot in ("faible", "non atteint", "non dépassé", "non active", "non activé", "ratio nul", "pas de difficulté", "aucune difficulté", "sans vulnérabilité")):
                return COULEURS_VULNERABILITE["faible"]
            if any(mot in texte for mot in ("modér", "tension", "urgence")):
                return COULEURS_VULNERABILITE["moderee"]
            if any(mot in texte for mot in ("critique", "sévère", "severe", "crise")):
                return COULEURS_VULNERABILITE["critique"]
            return COULEURS_VULNERABILITE["neutre"]

        def couleur_indicateur(colonne, valeur):
            if pd.isna(valeur) or colonne == "ratio_revenu_locatif":
                return COULEURS_VULNERABILITE["neutre"]
            valeur = float(valeur)
            if colonne == "vulnerabilite_abri_orientee":
                # Dégradé continu sur l'échelle inversée (1 = moins vulnérable, 10 = plus vulnérable).
                return plt.get_cmap("RdYlGn_r")(np.clip((valeur - 1) / 9, 0, 1))
            if colonne == "score_hhs_total":
                niveau = "faible" if valeur <= 1 else "moderee" if valeur <= 3 else "critique"
            elif colonne == "score_ame_global":
                niveau = "faible" if valeur < 3 else "moderee" if valeur < 4 else "critique"
            elif colonne == "score_global_wash":
                niveau = "faible" if valeur <= 1 else "moderee" if valeur == 2 else "critique"
            elif colonne == "score_global_agro":
                niveau = "faible" if valeur < 2 else "critique"
            elif colonne == "ratio_dependance":
                niveau = "faible" if valeur <= 2 else "critique"
            elif colonne == "ratio_loyer_revenu":
                niveau = "faible" if valeur <= 0.4 else "critique"
            elif colonne == "ratio_dette_revenu":
                niveau = "faible" if valeur <= 3 else "critique"
            elif colonne in ("score_handicap_wg", "score_genre_vulnerabilite_critique"):
                niveau = "faible" if valeur < 0.5 else "critique"
            else:
                return COULEURS_VULNERABILITE["neutre"]
            return COULEURS_VULNERABILITE[niveau]

        ouvrir_bloc("Alertes métier")
        # Les seuils ci-dessous sont ceux déjà définis par les méthodes du projet.
        regles_vigilance = [
            ("SECAL / HHS sévère", "score_hhs_total", lambda valeurs: valeurs.ge(4)),
            ("AME/NFI en crise", "score_ame_global", lambda valeurs: valeurs.ge(4)),
            ("Alerte WASH maximale", "score_global_wash", lambda valeurs: valeurs.ge(3)),
            ("Vulnérabilité agricole sévère", "score_global_agro", lambda valeurs: valeurs.ge(2)),
            ("Ratio de dépendance critique", "ratio_dependance", lambda valeurs: valeurs.gt(2)),
            ("WG-SS sévère", "score_handicap_wg", lambda valeurs: valeurs.ge(1)),
            ("Proxy genre critique", "score_genre_vulnerabilite_critique", lambda valeurs: valeurs.ge(1)),
            ("Surcharge de loyer", "ratio_loyer_revenu", lambda valeurs: valeurs.gt(.4)),
            ("Endettement critique", "ratio_dette_revenu", lambda valeurs: valeurs.gt(3)),
        ]
        print("Alertes calculées avec les seuils métier existants :")
        for libelle, colonne, est_critique in regles_vigilance:
            valeurs = pd.to_numeric(df_scores_analyse[colonne], errors="coerce").dropna()
            if valeurs.empty:
                print(f"- {libelle} : non calculable")
                continue
            nombre = int(est_critique(valeurs).sum())
            part = nombre / len(valeurs) * 100
            resultat = f"{libelle} : {nombre:,} / {len(valeurs):,} ménages ({part:.1f} %)"
            if nombre:
                print(f"\033[91m⚠ {resultat}\033[0m")
            else:
                print(f"- {resultat}")

        ouvrir_bloc("Composition des ménages par statut")

        def libelle_statut(valeur):
            if pd.isna(valeur):
                return "Statut non renseigné"
            texte = str(valeur).casefold()
            if "fugi" in texte:
                return "Réfugié"
            if "non famille" in texte:
                return "Autochtone, hors famille d’accueil"
            if "famille" in texte:
                return "Autochtone, famille d’accueil"
            return str(valeur)

        def intensite(valeur):
            valeur = abs(valeur)
            return "négligeable" if valeur < .1 else "faible" if valeur < .3 else "modérée" if valeur < .5 else "forte"

        df_scores_analyse["statut_court"] = df_scores_analyse["status"].map(libelle_statut)
        taille = pd.to_numeric(df_scores_analyse["taille_menage"], errors="coerce")
        groupes_taille = taille.groupby(df_scores_analyse["statut_court"])
        tableau_statut = pd.DataFrame({
            "Ménages (N)": groupes_taille.size(),
            "Part (%)": groupes_taille.size() / len(df_scores_analyse) * 100,
            "Taille moyenne": groupes_taille.mean(),
            "Médiane": groupes_taille.median(),
            "Q1": groupes_taille.quantile(.25),
            "Q3": groupes_taille.quantile(.75),
            "Maximum": groupes_taille.max(),
        }).sort_values("Ménages (N)", ascending=False)
        tableau_statut.index.name = None
        display(tableau_statut.style.format({
            "Ménages (N)": "{:.0f}", "Part (%)": "{:.1f} %", "Taille moyenne": "{:.1f}",
            "Médiane": "{:.1f}", "Q1": "{:.1f}", "Q3": "{:.1f}", "Maximum": "{:.0f}",
        }))
        ordre_statuts = list(tableau_statut.index)
        fig, axe = plt.subplots(figsize=(9, 1.4 + 0.9 * len(ordre_statuts)))
        sns.boxplot(
            data=pd.DataFrame({"statut": df_scores_analyse["statut_court"], "taille": taille}).dropna(),
            x="taille", y="statut", order=ordre_statuts, showfliers=False, color="#9DB9D6", ax=axe,
            showmeans=True, meanprops={"marker": "D", "markerfacecolor": "white", "markeredgecolor": "#243447"},
        )
        axe.set_xlabel("Personnes par ménage (valeurs extrêmes non tracées)")
        axe.set_ylabel("")
        axe.set_title("Taille des ménages selon leur statut")
        fig.tight_layout()
        plt.show()
        plt.close(fig)
        plus_grand, plus_petit = tableau_statut["Taille moyenne"].idxmax(), tableau_statut["Taille moyenne"].idxmin()
        petits = tableau_statut.index[tableau_statut["Ménages (N)"] < 0.1 * len(df_scores_analyse)]
        texte_composition = (
            f"Lecture : le groupe « {tableau_statut['Ménages (N)'].idxmax()} » représente {tableau_statut['Part (%)'].max():.1f} % de l’échantillon. "
            f"La taille moyenne est la plus élevée pour « {plus_grand} » ({tableau_statut.loc[plus_grand, 'Taille moyenne']:.1f} personnes, médiane {tableau_statut.loc[plus_grand, 'Médiane']:.1f}) "
            f"et la plus faible pour « {plus_petit} » ({tableau_statut.loc[plus_petit, 'Taille moyenne']:.1f}, médiane {tableau_statut.loc[plus_petit, 'Médiane']:.1f}). "
            "Dans le graphique, la boîte couvre la moitié centrale des ménages et le losange blanc indique la moyenne."
        )
        if len(petits):
            texte_composition += " Les groupes « " + " », « ".join(petits) + " » sont plus petits (moins de 10 % de l’échantillon) : leurs résultats sont moins stables."
        taille_nulle = int(taille.eq(0).sum())
        if taille_nulle:
            texte_composition += f" ⚠ {taille_nulle:,} ménage(s) ont une taille égale à 0 : à vérifier dans la base."
        note(texte_composition)

        ouvrir_bloc("Répartition des scores")
        # A. Répartition des scores : les histogrammes conservent toute l’échelle théorique.
        domaines_scores = {
            "Abri (risque orienté)": ("vulnerabilite_abri_orientee", 1, 10, False),
            "SECAL / HHS": ("score_hhs_total", 0, 6, True),
            "AME/NFI": ("score_ame_global", 0, 5, False),
            "WASH": ("score_global_wash", 0, 3, True),
            "AGRO": ("score_global_agro", 0, 5, True),
        }


        def tracer_distributions_scores():
            fig, axes = plt.subplots(2, 3, figsize=(17, 10))
            for axe, (libelle, (colonne, borne_min, borne_max, discret)) in zip(axes.flat, domaines_scores.items()):
                valeurs = pd.to_numeric(df_scores_analyse[colonne], errors="coerce").dropna()
                hors_echelle = valeurs[(valeurs < borne_min) | (valeurs > borne_max)]
                if valeurs.empty:
                    axe.text(.5, .5, "Aucun score calculable", ha="center", va="center", transform=axe.transAxes)
                    axe.set_xlim(borne_min, borne_max)
                else:
                    minimum = min(borne_min, int(np.floor(valeurs.min())))
                    maximum = max(borne_max, int(np.ceil(valeurs.max())))
                    if discret:
                        axe.hist(valeurs, bins=np.arange(minimum - .5, maximum + 1.5, 1),
                                 color=COULEURS_VULNERABILITE["neutre"], edgecolor="white")
                        axe.set_xticks(np.arange(minimum, maximum + 1, 1))
                    else:
                        axe.hist(valeurs, bins=np.linspace(minimum, maximum, 21),
                                 color=COULEURS_VULNERABILITE["neutre"], edgecolor="white")
                        axe.set_xticks(np.arange(borne_min, borne_max + 1, 1))
                    for barre in axe.patches:
                        centre = barre.get_x() + barre.get_width() / 2
                        barre.set_facecolor(couleur_indicateur(colonne, centre))
                    axe.set_xlim(minimum - .5 if discret else minimum, maximum + .5 if discret else maximum)
                    if not hors_echelle.empty:
                        axe.text(.98, .96, f"⚠ {len(hors_echelle)} hors échelle", color="#B22222",
                                 ha="right", va="top", transform=axe.transAxes, fontsize=9)
                        print(f"\033[91m⚠ {libelle} : {len(hors_echelle)} valeur(s) hors de l’échelle [{borne_min}, {borne_max}].\033[0m")
                n_valide = int(valeurs.size)
                n_manquant = int(len(df_scores_analyse) - n_valide)
                axe.set_title(f"{libelle}\nN={n_valide:,} scores valides ; {n_manquant:,} manquants")
                axe.set_xlabel(f"Score (échelle complète : {borne_min} à {borne_max})")
                axe.set_ylabel("Nombre de ménages")
            axes.flat[-1].axis("off")
            fig.suptitle("Répartition des scores sectoriels parmi les ménages", y=.99)
            fig.tight_layout(rect=(0, 0, 1, .96))
            plt.show()
            plt.close(fig)


        tracer_distributions_scores()

        lignes_manquants = []
        for libelle, (colonne, _, _, _) in domaines_scores.items():
            manquant = df_scores_analyse[colonne].isna()
            vide = pd.Series(False, index=df_scores_analyse.index)
            non_concerne = vide
            non_classe = vide
            if colonne == "score_global_agro":
                non_concerne = manquant & df_scores_analyse["cible_pratique_agro"].eq(0).fillna(False).astype(bool)
            if colonne == "score_global_wash":
                non_classe = manquant & df_scores_analyse["categorie_source_eau"].str.startswith("Puits traditionnel", na=False)
            lignes_manquants.append({
                "Score": libelle,
                "Calculé (N)": int((~manquant).sum()),
                "Non concernés": int(non_concerne.sum()),
                "Non classés par la méthode": int(non_classe.sum()),
                "Données manquantes": int((manquant & ~non_concerne & ~non_classe).sum()),
            })
        display(pd.DataFrame(lignes_manquants).set_index("Score"))
        manquant_wash = df_scores_analyse["score_global_wash"].isna() & ~df_scores_analyse["categorie_source_eau"].str.startswith("Puits traditionnel", na=False)
        detail_wash = ", ".join(
            f"{nom} : {int((manquant_wash & df_scores_analyse[col].isna()).sum()):,}"
            for nom, col in (("source d’eau", "cible_wash_eau_critique"), ("stockage par habitant", "cible_wash_stockage_insuffisant"), ("séparation de l’eau", "cible_wash_absence_separation"))
        )
        note(
            "Les scores absents ne sont pas tous des valeurs manquantes. "
            "AGRO : seuls les ménages qui déclarent pratiquer l’agriculture sont concernés ; les autres sont « non concernés ». "
            "WASH : les puits traditionnels sont volontairement non classés (classification séparée) ; le reste est une donnée manquante parmi les trois composantes "
            f"({detail_wash}). "
            "SECAL / HHS : le score n’est calculé que si les trois questions de fréquence sont exploitables.\n"
            "Seuls les cinq scores sectoriels sont tracés ici. Le ratio de dépendance, le handicap WG-SS, le proxy genre, le loyer et la dette sont des ratios ou des indicateurs 0/1 sans échelle de score ; ils sont suivis dans les alertes et les associations."
        )

        marquees = []
        ouvrir_bloc("Corrélations entre scores et variables socio-démographiques")
        # B. Matrice de Spearman des scores et de quelques mesures démographiques.
        variables_matrice = {
            "Risque abri": "vulnerabilite_abri_orientee",
            "SECAL / HHS": "score_hhs_total",
            "AME/NFI": "score_ame_global",
            "WASH": "score_global_wash",
            "AGRO": "score_global_agro",
            "Âge du répondant": "age_repondant",
            "Taille du ménage": "taille_menage",
            "Ratio de dépendance": "ratio_dependance",
        }
        variables_utilisables = {}
        for libelle, colonne in variables_matrice.items():
            if colonne in df_scores_analyse.columns:
                valeurs = pd.to_numeric(df_scores_analyse[colonne], errors="coerce")
                if valeurs.nunique(dropna=True) > 1:
                    variables_utilisables[libelle] = valeurs

        liens_mecaniques = {
            frozenset(("taille_menage", "score_ame_global")): "La taille du ménage sert à normaliser certains articles AME.",
            frozenset(("taille_menage", "score_global_wash")): "Le score WASH tient compte de la quantité d'eau par personne.",
            frozenset(("taille_menage", "ratio_dependance")): "Les deux mesures sont calculées à partir des mêmes groupes d'âge.",
            frozenset(("ratio_dependance", "score_ame_global")): "Les deux indicateurs dépendent en partie de la composition et de la taille du ménage.",
            frozenset(("ratio_dependance", "score_global_wash")): "Le ratio dépend de la composition; le score WASH utilise la quantité par personne.",
        }
        if len(variables_utilisables) >= 2:
            libelles_variables = list(variables_utilisables)
            donnees_matrice = pd.DataFrame(variables_utilisables)
            masque_validite = donnees_matrice.notna().astype("int64")
            matrice_n = masque_validite.T.dot(masque_validite)
            matrice_rho = donnees_matrice.corr(method="spearman", min_periods=3)
            for libelle in libelles_variables:
                matrice_rho.loc[libelle, libelle] = 1.0
            annotations = matrice_rho.copy().astype(object)
            for libelle_x in libelles_variables:
                for libelle_y in libelles_variables:
                    rho = matrice_rho.loc[libelle_x, libelle_y]
                    if pd.notna(rho):
                        cx, cy = variables_matrice[libelle_x], variables_matrice[libelle_y]
                        avertissement = " ⚠" if frozenset((cx, cy)) in liens_mecaniques else ""
                        annotations.loc[libelle_x, libelle_y] = f"{rho:.2f}{avertissement}"
            print("\nMatrice des corrélations de rang de Spearman (ρ) :")
            fig, axe = plt.subplots(figsize=(11, 8))
            sns.heatmap(matrice_rho, annot=annotations, fmt="", center=0, cmap="vlag", vmin=-1, vmax=1,
                        mask=matrice_rho.isna(), ax=axe)
            axe.set_title("Associations entre scores sectoriels et variables socio-démographiques")
            fig.tight_layout()
            plt.show()
            plt.close(fig)
            paires_mecaniques = [
                (libelle_x, libelle_y, liens_mecaniques[frozenset((variables_matrice[libelle_x], variables_matrice[libelle_y]))])
                for i, libelle_x in enumerate(libelles_variables)
                for libelle_y in libelles_variables[i + 1:]
                if frozenset((variables_matrice[libelle_x], variables_matrice[libelle_y])) in liens_mecaniques
            ]
            if paires_mecaniques:
                print("\033[93m⚠ Certaines corrélations sont potentiellement mécaniques : des calculs partagent des variables.\033[0m")
                for a, b, raison in paires_mecaniques:
                    print(f"- {a} — {b} : {raison}")
            paires = [
                (a, b, matrice_rho.loc[a, b], int(matrice_n.loc[a, b]))
                for i, a in enumerate(libelles_variables)
                for b in libelles_variables[i + 1:]
                if pd.notna(matrice_rho.loc[a, b])
            ]
            est_mecanique = lambda paire: frozenset((variables_matrice[paire[0]], variables_matrice[paire[1]])) in liens_mecaniques
            marquees = sorted((p for p in paires if not est_mecanique(p) and abs(p[2]) >= .1), key=lambda p: abs(p[2]), reverse=True)
            lecture = [
                "Comment lire la matrice : ρ va de −1 à +1 ; près de 0, il n’y a pas de lien de rang net ; |ρ| < 0.1 négligeable, 0.1–0.3 faible, 0.3–0.5 modéré, ≥ 0.5 fort. "
                f"Chaque paire utilise les ménages renseignés pour les deux variables (de {min(p[3] for p in paires):,} à {max(p[3] for p in paires):,} ménages)."
            ]
            if marquees:
                lecture.append("Liens les plus nets hors liens mécaniques : " + " ; ".join(
                    f"{a} — {b} (ρ = {rho:.2f}, {intensite(rho)}, N = {n:,})" for a, b, rho, n in marquees[:4]
                ) + ".")
            else:
                lecture.append("Aucun lien hors liens mécaniques n’atteint |ρ| ≥ 0.1 : les scores sectoriels évoluent de façon largement indépendante.")
            forts_mecaniques = [p for p in paires if est_mecanique(p) and abs(p[2]) >= .3]
            if forts_mecaniques:
                lecture.append("Les liens les plus forts (" + " ; ".join(f"{a} — {b} : ρ = {rho:.2f}" for a, b, rho, _ in forts_mecaniques)
                               + ") viennent surtout de la construction des variables (⚠) ; il ne faut pas les lire comme un effet réel.")
            note("\n".join(lecture))
        else:
            matrice_rho = pd.DataFrame()
            matrice_n = pd.DataFrame()
            print("Matrice non produite : moins de deux variables numériques avec une variation suffisante.")

        ouvrir_bloc("Corrélations de Spearman selon le statut du ménage")
        if len(variables_utilisables) >= 2:
            donnees_complet = pd.DataFrame(variables_utilisables)
            matrices_statut = {}
            for statut, effectif_statut in df_scores_analyse["statut_court"].value_counts().items():
                if effectif_statut < 100:
                    continue
                matrices_statut[statut] = (donnees_complet.loc[df_scores_analyse["statut_court"].eq(statut)].corr(method="spearman", min_periods=30), int(effectif_statut))
            for statut, (matrice_s, effectif_statut) in matrices_statut.items():
                annotations_s = matrice_s.copy().astype(object)
                for libelle_x in matrice_s.index:
                    for libelle_y in matrice_s.columns:
                        rho = matrice_s.loc[libelle_x, libelle_y]
                        if pd.notna(rho):
                            marque = " ⚠" if frozenset((variables_matrice[libelle_x], variables_matrice[libelle_y])) in liens_mecaniques else ""
                            annotations_s.loc[libelle_x, libelle_y] = f"{rho:.2f}{marque}"
                fig, axe = plt.subplots(figsize=(10, 7))
                sns.heatmap(matrice_s, annot=annotations_s, fmt="", center=0, cmap="vlag", vmin=-1, vmax=1, mask=matrice_s.isna(), ax=axe)
                axe.set_title(f"{statut} (N={effectif_statut:,})")
                fig.tight_layout()
                plt.show()
                plt.close(fig)
            ecarts = []
            for i, a in enumerate(donnees_complet.columns):
                for b in donnees_complet.columns[i + 1:]:
                    if frozenset((variables_matrice[a], variables_matrice[b])) in liens_mecaniques:
                        continue
                    valeurs = {statut: m.loc[a, b] for statut, (m, _) in matrices_statut.items() if pd.notna(m.loc[a, b])}
                    if len(valeurs) >= 2 and max(valeurs.values()) - min(valeurs.values()) >= .1:
                        ecarts.append((max(valeurs.values()) - min(valeurs.values()), a, b, valeurs))
            ecarts.sort(key=lambda ligne: ligne[0], reverse=True)
            lecture = ["Lecture : mêmes variables et même échelle que la matrice globale, calculées séparément dans chaque statut (groupes d’au moins 100 ménages)."]
            if ecarts:
                lecture.append("Écarts de ρ les plus nets entre statuts (hors liens mécaniques) :")
                for _, a, b, valeurs in ecarts[:4]:
                    lecture.append(f"{a} — {b} : " + " ; ".join(f"{statut} ρ = {rho:.2f} (N = {int(donnees_complet.loc[df_scores_analyse['statut_court'].eq(statut), [a, b]].dropna().shape[0]):,})" for statut, rho in valeurs.items()))
            else:
                lecture.append("Les corrélations hors liens mécaniques sont proches d’un statut à l’autre (écart de ρ < 0.1) : le statut ne modifie pas la structure des liens entre scores.")
            lecture.append("Un écart de ρ est d’autant plus fragile que N est faible ; des signes opposés entre statuts signalent des structures différentes, à confirmer avant toute généralisation.")
            note("\n".join(lecture))
            if {"SECAL / HHS", "AGRO"} <= set(donnees_complet.columns):
                paire = donnees_complet[["SECAL / HHS", "AGRO"]].assign(statut=df_scores_analyse["statut_court"]).dropna()
                statuts_paire = [statut for statut in matrices_statut if (paire["statut"] == statut).sum() >= 30]
                if len(statuts_paire) >= 2:
                    generateur = np.random.default_rng(0)
                    fig, axes = plt.subplots(1, len(statuts_paire), figsize=(5 * len(statuts_paire), 4.6), sharex=True, sharey=True)
                    for axe, statut in zip(np.atleast_1d(axes), statuts_paire):
                        sous = paire[paire["statut"] == statut]
                        rho_paire = sous["SECAL / HHS"].corr(sous["AGRO"], method="spearman")
                        axe.scatter(sous["SECAL / HHS"] + generateur.uniform(-.15, .15, len(sous)), sous["AGRO"] + generateur.uniform(-.15, .15, len(sous)), s=8, alpha=.25, color="#4C78A8")
                        axe.set_title(f"{statut}\nρ = {rho_paire:.2f} (N={len(sous):,})", fontsize=10)
                        axe.set_xlabel("SECAL / HHS")
                    axes_liste = np.atleast_1d(axes)
                    axes_liste[0].set_ylabel("AGRO")
                    fig.suptitle("SECAL / HHS et AGRO selon le statut (points légèrement décalés pour limiter le chevauchement)")
                    fig.tight_layout(rect=(0, 0, 1, .93))
                    plt.show()
                    plt.close(fig)
                    if "Autochtone, famille d’accueil" in statuts_paire:
                        note("Lecture : l’hypothèse d’une pression d’accueil est plausible (les familles d’accueil partagent leurs ressources, y compris agricoles, avec des ménages réfugiés), mais elle n’est pas démontrée : la base ne mesure ni le nombre de personnes hébergées ni la dépendance aux terres partagées. Avec des données fictives, un artefact de génération reste possible ; à confirmer avec une variable d’hébergement ou sur données réelles.")
        else:
            print("Matrices par statut non produites : moins de deux variables numériques avec une variation suffisante.")

        ouvrir_bloc("Cercle des corrélations (ACP descriptive)")
        rangs_acp = pd.DataFrame(variables_utilisables).dropna().rank() if len(variables_utilisables) >= 3 else pd.DataFrame()
        if len(rangs_acp) >= 100:
            # ACP sur les rangs (cohérente avec Spearman) : décomposition de la matrice de corrélation, sans apprentissage.
            z_acp = (rangs_acp - rangs_acp.mean()) / rangs_acp.std(ddof=0)
            valeurs_propres, vecteurs = np.linalg.eigh(np.corrcoef(z_acp.to_numpy(), rowvar=False))
            ordre_acp = np.argsort(valeurs_propres)[::-1]
            valeurs_propres, vecteurs = valeurs_propres[ordre_acp], vecteurs[:, ordre_acp]
            part_variance = valeurs_propres / valeurs_propres.sum() * 100
            charges = vecteurs * np.sqrt(valeurs_propres)
            for axe_acp in range(2):
                if charges[:, axe_acp].sum() < 0:
                    charges[:, axe_acp] *= -1
            fig, axe = plt.subplots(figsize=(7.5, 7.5))
            axe.add_patch(plt.Circle((0, 0), 1, fill=False, color="#8A96A3"))
            for indice, libelle in enumerate(z_acp.columns):
                x, y = charges[indice, 0], charges[indice, 1]
                axe.annotate("", xy=(x, y), xytext=(0, 0), arrowprops={"arrowstyle": "->", "color": "#4C78A8", "lw": 1.6})
                axe.text(x * 1.1, y * 1.1, libelle, ha="center", va="center", fontsize=9)
            axe.axhline(0, color="#c9d2db", lw=.8)
            axe.axvline(0, color="#c9d2db", lw=.8)
            axe.set_xlim(-1.25, 1.25)
            axe.set_ylim(-1.25, 1.25)
            axe.set_aspect("equal")
            axe.set_xlabel(f"Axe 1 ({part_variance[0]:.1f} % de la variance)")
            axe.set_ylabel(f"Axe 2 ({part_variance[1]:.1f} % de la variance)")
            axe.set_title(f"Cercle des corrélations (N={len(rangs_acp):,} ménages complets)")
            fig.tight_layout()
            plt.show()
            plt.close(fig)
            part_uniforme = 100 / len(z_acp.columns)
            axes_kaiser = int((valeurs_propres > 1).sum())
            qualite = pd.Series((charges[:, :2] ** 2).sum(axis=1), index=z_acp.columns)
            axe_1 = [libelle for libelle, charge in zip(z_acp.columns, charges[:, 0]) if abs(charge) >= .5]
            axe_2 = [libelle for libelle, charge in zip(z_acp.columns, charges[:, 1]) if abs(charge) >= .5]
            mal_representees = list(qualite.index[qualite < .3])
            lecture = [
                "Comment lire : chaque flèche est une variable ; plus elle est longue (proche du cercle), mieux elle est représentée dans ce plan. Deux flèches proches vont dans le même sens, deux flèches opposées vont en sens inverse, deux flèches à angle droit sont indépendantes. "
                "Méthode descriptive (analyse en composantes principales sur les rangs), sans modèle prédictif.",
                f"Les deux premiers axes résument {part_variance[:2].sum():.1f} % de la variance. Si les {len(z_acp.columns)} variables étaient totalement indépendantes, chaque axe en expliquerait environ {part_uniforme:.1f} % ; {axes_kaiser} axe(s) dépasse(nt) la valeur propre 1.",
                "Axe 1 : " + (", ".join(axe_1) if axe_1 else "aucune variable avec une corrélation ≥ 0,5") + ". Axe 2 : " + (", ".join(axe_2) if axe_2 else "aucune variable avec une corrélation ≥ 0,5") + ".",
            ]
            if mal_representees:
                lecture.append("Mal représentées dans ce plan (flèche courte) : " + ", ".join(mal_representees) + " ; leur information se trouve sur d’autres axes ou n’est pas partagée avec les autres variables.")
            lecture.append("Limite : seuls les ménages disposant de toutes les variables sont retenus ; les ménages non agricoles et les puits traditionnels (WASH non classé) sont donc exclus de cette figure. La taille du ménage et le ratio de dépendance, liés mécaniquement, pèsent ensemble sur un même axe.")
            note("\n".join(lecture))
        else:
            print("Cercle non produit : trop peu de ménages complets ou de variables.")

        ouvrir_bloc("Relations numériques notables")
        # C. Illustrer quelques relations lisibles qui ressortent de la matrice.
        scores_cibles = {"vulnerabilite_abri_orientee", "score_hhs_total", "score_ame_global", "score_global_wash", "score_global_agro"}
        relations = []
        for i, libelle_a in enumerate(variables_utilisables):
            for libelle_b in list(variables_utilisables)[i + 1:]:
                colonne_a, colonne_b = variables_matrice[libelle_a], variables_matrice[libelle_b]
                if colonne_a not in scores_cibles and colonne_b not in scores_cibles:
                    continue
                if frozenset((colonne_a, colonne_b)) in liens_mecaniques or matrice_rho.empty:
                    continue
                rho = matrice_rho.loc[libelle_a, libelle_b]
                n = int(matrice_n.loc[libelle_a, libelle_b])
                if pd.notna(rho) and n >= 3 and abs(rho) >= .15:
                    relations.append({"Variable A": libelle_a, "Variable B": libelle_b, "ρ de Spearman": rho,
                                      "N": n, "colonnes": (colonne_a, colonne_b)})
        relations = sorted(relations, key=lambda ligne: abs(ligne["ρ de Spearman"]), reverse=True)[:3]
        if relations:
            print("\nJusqu’à trois relations hors corrélations mécaniques (|ρ| ≥ 0,15; intensité à interpréter avec prudence) :")
            display(pd.DataFrame([{k: v for k, v in relation.items() if k != "colonnes"} for relation in relations]).round(3))
            fig, axes = plt.subplots(1, len(relations), figsize=(6 * len(relations), 5), squeeze=False)
            for axe, relation in zip(axes.flat, relations):
                colonne_x, colonne_y = relation["colonnes"]
                donnees = df_scores_analyse[[colonne_x, colonne_y]].apply(pd.to_numeric, errors="coerce").dropna()
                if donnees[colonne_x].nunique() <= 12 and donnees[colonne_y].nunique() <= 12:
                    sns.histplot(data=donnees, x=colonne_x, y=colonne_y, discrete=True,
                                 cbar=True, ax=axe, cmap="Blues")
                    axe.collections[-1].colorbar.set_label("Nombre de ménages")
                else:
                    image = axe.hexbin(donnees[colonne_x], donnees[colonne_y], gridsize=25, mincnt=1, cmap="Blues")
                    fig.colorbar(image, ax=axe, label="Nombre de ménages")
                axe.set_xlabel(relation["Variable A"])
                axe.set_ylabel(relation["Variable B"])
                axe.set_title(f"ρ={relation['ρ de Spearman']:.2f} ; N={relation['N']:,}")
            fig.suptitle("Relations sélectionnées dans la matrice", y=.99)
            fig.tight_layout(rect=(0, 0, 1, .93))
            plt.show()
            plt.close(fig)
            phrases = []
            for relation in relations:
                rho = relation["ρ de Spearman"]
                phrases.append(
                    f"{relation['Variable A']} et {relation['Variable B']} : association {intensite(rho)} {'positive' if rho > 0 else 'négative'} "
                    f"(ρ = {rho:.2f}, N = {relation['N']:,}) ; les ménages dont « {relation['Variable A']} » est plus élevé tendent à avoir un « {relation['Variable B']} » "
                    f"{'plus élevé' if rho > 0 else 'plus faible'}."
                )
            if all(abs(relation["ρ de Spearman"]) < .3 for relation in relations):
                phrases.append("Ces liens restent modestes (|ρ| < 0.3) : la majeure partie de la variation d’un indicateur n’est pas expliquée par l’autre. Ils décrivent l’échantillon sans établir de causalité.")
            else:
                phrases.append("Ces liens décrivent l’échantillon sans établir de causalité.")
            note("\n".join(phrases))
        else:
            print("Aucune relation non mécanique d’intensité |ρ| ≥ 0,15 à illustrer.")

        # D. Comparer les profils de niveaux existants par statut et sexe, sans refaire tous les graphiques.
        niveaux_existants = {
            "Ratio de dépendance": "niveau_ratio_dependance",
            "Handicap WG-SS": "categorie_handicap_wg",
            "Genre — proxy critique": "niveau_genre_analyse",
            "Loyer payé / revenu": "niveau_loyer_analyse",
            "Dette / revenu": "niveau_dette_analyse",
            "SECAL / HHS": "categorie_hhs",
            "AME/NFI": "categorie_ame_phase",
            "WASH": "niveau_wash",
        }
        df_scores_analyse["niveau_agro_analyse"] = pd.Series(pd.NA, index=df_scores_analyse.index, dtype="string")
        df_scores_analyse.loc[df_scores_analyse["score_global_agro"].notna() & df_scores_analyse["score_global_agro"].lt(2), "niveau_agro_analyse"] = "0–1 : seuil sévère non atteint"
        df_scores_analyse.loc[df_scores_analyse["score_global_agro"].ge(2), "niveau_agro_analyse"] = "≥2 : vulnérabilité sévère"
        niveaux_existants["AGRO"] = "niveau_agro_analyse"
        for source, resultat, seuil, libelle_bas, libelle_haut, binaire in [
            ("score_genre_vulnerabilite_critique", "niveau_genre_analyse", 1, "0 : proxy non activé", "1 : proxy critique activé", True),
            ("ratio_loyer_revenu", "niveau_loyer_analyse", .4, "≤ 0,40 : seuil non dépassé", "> 0,40 : surcharge critique", False),
            ("ratio_dette_revenu", "niveau_dette_analyse", 3, "≤ 3 : seuil non dépassé", "> 3 : endettement critique", False),
        ]:
            valeurs = pd.to_numeric(df_scores_analyse[source], errors="coerce")
            niveau = pd.Series(pd.NA, index=df_scores_analyse.index, dtype="string")
            if binaire:
                niveau.loc[valeurs.eq(0)] = libelle_bas
                niveau.loc[valeurs.eq(1)] = libelle_haut
            else:
                niveau.loc[valeurs.le(seuil)] = libelle_bas
                niveau.loc[valeurs.gt(seuil)] = libelle_haut
            df_scores_analyse[resultat] = niveau


        def calculer_v_cramer(contingence):
            n = int(contingence.to_numpy().sum())
            lignes, colonnes = contingence.shape
            if n <= 1 or min(lignes, colonnes) < 2:
                return np.nan
            chi2 = chi2_contingency(contingence, correction=False)[0]
            phi2 = chi2 / n
            phi2_corr = max(0.0, phi2 - ((colonnes - 1) * (lignes - 1)) / (n - 1))
            lignes_corr = lignes - (lignes - 1) ** 2 / (n - 1)
            colonnes_corr = colonnes - (colonnes - 1) ** 2 / (n - 1)
            denominateur = min(colonnes_corr - 1, lignes_corr - 1)
            return float(np.sqrt(phi2_corr / denominateur)) if denominateur > 0 else np.nan


        associations_categories = []
        for groupe, libelle_groupe in (("status", "Statut du ménage"), ("sexe_repondant", "Sexe du répondant")):
            if groupe not in df_scores_analyse.columns:
                continue
            for libelle, colonne_niveau in niveaux_existants.items():
                if colonne_niveau not in df_scores_analyse.columns:
                    continue
                donnees = df_scores_analyse[[groupe, colonne_niveau]].dropna()
                if donnees.empty:
                    continue
                contingence = pd.crosstab(donnees[groupe], donnees[colonne_niveau])
                v_cramer = calculer_v_cramer(contingence)
                if pd.notna(v_cramer):
                    associations_categories.append({"Caractéristique": libelle_groupe, "Indicateur": libelle,
                        "V de Cramér": v_cramer, "N": int(contingence.to_numpy().sum()),
                        "groupe": groupe, "niveau": colonne_niveau})

        ouvrir_bloc("Associations catégorielles")
        if associations_categories:
            associations_triees = sorted(associations_categories, key=lambda ligne: ligne["V de Cramér"], reverse=True)
            print("\nAssociations catégorielles les plus marquées (V de Cramér : intensité, pas causalité) :")
            tableau_v = pd.DataFrame([{cle: ligne[cle] for cle in ("Caractéristique", "Indicateur", "V de Cramér", "N")}
                                      for ligne in associations_triees[:8]]).round(3)
            tableau_v["Intensité"] = tableau_v["V de Cramér"].map(intensite)
            display(tableau_v)
            meilleure = associations_triees[0]
            lecture_v = (
                "Comment lire le V de Cramér : de 0 (aucun lien) à 1 (lien parfait) ; < 0.1 négligeable, 0.1–0.3 faible, 0.3–0.5 modéré, ≥ 0.5 fort. "
                "Il mesure l’intensité du lien entre un groupe et les niveaux d’un indicateur, pas son sens ni sa cause.\n"
                f"Le lien le plus net concerne « {meilleure['Indicateur']} » selon « {meilleure['Caractéristique']} » (V = {meilleure['V de Cramér']:.2f}, {intensite(meilleure['V de Cramér'])})."
            )
            if meilleure["V de Cramér"] < .3:
                lecture_v += " Toutes les associations restent faibles ou négligeables : le statut et le sexe du répondant distinguent peu les niveaux de vulnérabilité."
            note(lecture_v)
            selections = []
            for groupe in ("status", "sexe_repondant"):
                candidat = next((ligne for ligne in associations_triees if ligne["groupe"] == groupe), None)
                if candidat is not None and candidat["V de Cramér"] >= .1:
                    selections.append(candidat)
            if not selections:
                note("Aucune association n’atteint V ≥ 0.1 : aucun graphique détaillé n’est présenté.")
            else:
                note("Un exemple détaillé n’est montré que pour l’association la plus forte de chaque caractéristique, et seulement si V ≥ 0.1 (en dessous, l’écart entre groupes est trop faible pour être commenté).")
            for relation in selections:
                groupe, colonne_niveau = relation["groupe"], relation["niveau"]
                donnees = df_scores_analyse[[groupe, colonne_niveau]].dropna()
                effectifs = donnees[groupe].value_counts()
                proportions = pd.crosstab(donnees[groupe], donnees[colonne_niveau], normalize="index").mul(100).reindex(effectifs.index)
                tableau = proportions.copy()
                tableau.insert(0, "Ménages (N)", effectifs)
                precision = "; le sexe du répondant ne désigne pas nécessairement le chef de ménage" if groupe == "sexe_repondant" else ""
                ouvrir_bloc(f"Exemple : {relation['Indicateur']} selon {relation['Caractéristique']}")
                print(f"V de Cramér = {relation['V de Cramér']:.2f}{precision}")
                display(tableau.style.format({colonne: "{:.1f} %" for colonne in proportions.columns}))
                axe = proportions.plot(kind="bar", stacked=True, figsize=(9, 4),
                                       color=[couleur_niveau(niveau) for niveau in proportions.columns])
                axe.set_ylabel("Ménages du groupe (%)")
                axe.set_xlabel(relation["Caractéristique"])
                axe.set_title(f"{relation['Indicateur']} selon {relation['Caractéristique']}")
                axe.legend(title="Niveau", bbox_to_anchor=(1.02, 1), loc="upper left")
                for conteneur in axe.containers:
                    labels = [f"{barre.get_height():.0f} %" if barre.get_height() >= 8 else "" for barre in conteneur]
                    axe.bar_label(conteneur, labels=labels, label_type="center", fontsize=8)
                plt.xticks(rotation=25, ha="right")
                plt.tight_layout()
                plt.show()
                plt.close(axe.figure)
                colonnes_critiques = [niveau for niveau in proportions.columns if couleur_niveau(niveau) == COULEURS_VULNERABILITE["critique"]]
                if colonnes_critiques:
                    part_critique = proportions[colonnes_critiques].sum(axis=1)
                    part_critique = part_critique[effectifs.reindex(part_critique.index) >= 30]
                    if len(part_critique) >= 2:
                        haut, bas = part_critique.idxmax(), part_critique.idxmin()
                        note(
                            f"Lecture : la part de ménages au niveau critique ({', '.join(map(str, colonnes_critiques))}) est la plus élevée pour « {haut} » "
                            f"({part_critique[haut]:.1f} %, N = {int(effectifs[haut]):,}) et la plus faible pour « {bas} » ({part_critique[bas]:.1f} %, N = {int(effectifs[bas]):,}), "
                            f"soit {part_critique[haut] - part_critique[bas]:.1f} points d’écart. Association {intensite(relation['V de Cramér'])} (V = {relation['V de Cramér']:.2f})."
                        )
        else:
            print("Aucune association catégorielle calculable avec les groupes et niveaux disponibles.")

        ouvrir_bloc("Interprétation")
        conclusion = ["Ces analyses décrivent des associations dans l’échantillon, pas des causes ; les scores manquants ne sont pas assimilés à zéro."]
        if marquees:
            a, b, rho, n = marquees[0]
            conclusion.append(f"Hors liens mécaniques, la corrélation la plus nette est {a} — {b} (ρ = {rho:.2f}, {intensite(rho)}). Les scores sectoriels sont globalement peu corrélés entre eux : ils mesurent des dimensions différentes, ce qui justifie de ne pas les additionner en un score global.")
        conclusion.append("Pour la suite : peu de redondance entre variables (peu de risque de colinéarité), mais aucun prédicteur ne ressort fortement en analyse bivariée ; l’intérêt d’un modèle devra être jugé sur sa performance, pas sur ces associations seules.")
        note("\n".join(conclusion))
    fermer_bloc()
    html_bivariee = construire_rapport_html_bloc_3(sortie_bivariee, blocs_rapport_3)


    return html_bivariee


def lancer_eda(
    db_path=None,
    chemin_xlsform=None,
    identifiant_profil=None,
    chemin_xlsform_profil=None,
    correspondances_contexte=None,
    dossier_sortie=None,
    rappel_progression=None,
):
    """Exécute les trois analyses et écrit un rapport HTML unique ; retourne son chemin."""
    db_path = Path(db_path) if db_path else DB_PAR_DEFAUT
    if not db_path.is_file():
        raise FileNotFoundError(f"Base SQLite introuvable : {db_path}")
    dossier_sortie = Path(dossier_sortie) if dossier_sortie else DOSSIER_SORTIE
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemin_xlsform = Path(chemin_xlsform) if chemin_xlsform else _trouver_xlsform()
    _preparer_environnement_graphique()

    def signaler(message):
        print(message, flush=True)
        if rappel_progression:
            rappel_progression(message)

    signaler("⏳ Analyse en cours : cela peut prendre plusieurs minutes, merci de ne pas fermer cette fenêtre.")
    signaler("Étape 1/3 : analyse de la table principale et des tables secondaires…")
    html_principal, html_secondaires = analyser_univarie(db_path, chemin_xlsform)
    signaler("Étape 2/3 : analyse des liens entre scores et caractéristiques des ménages (étape la plus longue)…")
    html_bivariee = analyser_bivarie(db_path, identifiant_profil, chemin_xlsform_profil, correspondances_contexte)
    signaler("Étape 3/3 : assemblage du rapport…")

    chemin = dossier_sortie / "eda_rapport.html"
    chemin.write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Rapport d\'analyse exploratoire</title></head>'
        "<body>" + "<hr>".join((html_principal, html_secondaires, html_bivariee)) + "</body></html>",
        encoding="utf-8",
    )
    signaler(f"✅ Analyse terminée ({datetime.now():%d/%m/%Y %H:%M}). Rapport : {chemin}")
    return {"rapport": chemin}


def main(argv=None):
    parseur = argparse.ArgumentParser(description="Analyse exploratoire des enquêtes (partie 3).")
    parseur.add_argument("--db", default=None, help="Base SQLite (défaut : outputs/enquete_ms.db)")
    parseur.add_argument("--xlsform", default=None, help="XLSForm du questionnaire (défaut : data/)")
    parseur.add_argument("--profil", default=None, help="Identifiant d'un profil de questionnaire")
    parseur.add_argument("--xlsform-profil", default=None, help="XLSForm vérifié par le profil")
    parseur.add_argument("--sortie", default=None, help="Dossier de sortie (défaut : outputs/analyse)")
    arguments = parseur.parse_args(argv)
    chemins = lancer_eda(
        arguments.db, arguments.xlsform, arguments.profil, arguments.xlsform_profil, dossier_sortie=arguments.sortie
    )



if __name__ == "__main__":
    main()



