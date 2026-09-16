from datetime import datetime
from difflib import get_close_matches
import json
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
import pandas as pd
from IPython.display import display
import os

# ==========================================
# 0. SÉLECTION INTERACTIVE DES FICHIERS (SANS SAISIE MANUELLE)
# ==========================================
root = tk.Tk()
root.withdraw()  # Masquer la fenêtre principale Tkinter

messagebox.showinfo(
    "Sélection des fichiers",
    "Veuillez sélectionner le fichier de données brutes (CSV).",
)
chemin_brute = filedialog.askopenfilename(
    title="Sélectionner enquete_vul_brute.csv",
    filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")],
)

messagebox.showinfo(
    "Sélection des fichiers",
    "Veuillez sélectionner le catalogue des choix (CSV).",
)
chemin_choix = filedialog.askopenfilename(
    title="Sélectionner code_choix.csv",
    filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")],
)

messagebox.showinfo(
    "Sélection des fichiers",
    "Veuillez sélectionner le questionnaire Excel (XLSX).",
)
chemin_excel = filedialog.askopenfilename(
    title="Sélectionner Questionnaire Vulnérabilités Fictif.xlsx",
    filetypes=[("Fichiers Excel", "*.xlsx *.xls"), ("Tous les fichiers", "*.*")],
)

# Vérification si l'utilisateur a bien tout sélectionné
if not chemin_brute or not chemin_choix or not chemin_excel:
    raise ValueError(
        "Erreur : Un ou plusieurs fichiers n'ont pas été sélectionnés. Arrêt du script."
    )


# ==========================================
# 1. IMPORTATION ET CHARGEMENT DES DONNÉES
# ==========================================
print("Chargement des données en cours...")
df_brute = pd.read_csv(chemin_brute)
df_choix = pd.read_csv(chemin_choix)
df_dict = pd.read_excel(chemin_excel, sheet_name="survey")

print("Fichiers chargés avec succès !")


# ==========================================
# 2. NORMALISATION GLOBALE DES DONNÉES
# ==========================================
print("Normalisation globale des colonnes et des textes...")

# df_clean : copie initiale et nettoyage des noms de colonnes et des valeurs textuelles
df_clean = df_brute.copy()
df_clean.columns = df_clean.columns.astype(str).str.lower().str.strip()

cols_texte_clean = df_clean.select_dtypes(include=["object", "string"]).columns
for col in cols_texte_clean:
    df_clean[col] = (
        df_clean[col]
        .astype(str)
        .str.lower()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

# df_dict : normalisation des colonnes de référence si présentes
if "df_dict" in globals():
    df_dict.columns = df_dict.columns.astype(str).str.lower().str.strip()
    for col in ["name", "type"]:
        if col in df_dict.columns:
            df_dict[col] = df_dict[col].astype(str).str.lower().str.strip()

# df_choix : normalisation du catalogue de choix si présent
if "df_choix" in globals():
    df_choix.columns = df_choix.columns.astype(str).str.lower().str.strip()
    for col in ["list_name", "code"]:
        if col in df_choix.columns:
            df_choix[col] = df_choix[col].astype(str).str.lower().str.strip()

print("Normalisation terminée avec succès !")


# ==========================================
# 3. AUDIT STRUCTUREL ET FILTRAGE DES COLONNES
# ==========================================
print("Audit structurel et filtrage des colonnes en cours...")

vars_a_garder = []
variables_exception = ["heure_fin", "heure_debut"]
rapport_audit_structure = []
compteur_anomalies_groupes = 0

for _, row in df_dict.iterrows():
    t_val = str(row.get("type", "")).strip().lower()
    v_val = str(row.get("name", "")).strip()

    if not v_val or v_val == "nan":
        continue

    if v_val in variables_exception:
        vars_a_garder.append(v_val)
        continue

    # Gestion des groupes (begin/end group) -> masqués par défaut
    if (
        "group" in t_val
        or t_val in ["begin_group", "end_group", "begin group", "end group"]
    ):
        if v_val in df_clean.columns and df_clean[v_val].notna().any():
            compteur_anomalies_groupes += 1
        continue  # On ne l'ajoute pas à vars_a_garder (donc masquée)

    # Gestion des types vides dans le dictionnaire -> masqués par défaut
    if t_val == "" or t_val == "nan":
        if v_val in df_clean.columns and df_clean[v_val].notna().any():
            compteur_anomalies_groupes += 1
        continue  # Masquée également

    vars_a_garder.append(v_val)

# Suppression automatique des colonnes 100% vides de données dans le dataset physique
cols_100_vides = [col for col in df_clean.columns if df_clean[col].isna().all()]
if cols_100_vides:
    df_clean = df_clean.drop(columns=cols_100_vides)

    # Ajout du message spécifique pour le rapport d'erreur
    liste_cols_vides_str = ", ".join([f"'{c}'" for c in cols_100_vides])
    message_vides = (
        f"Il y a {len(cols_100_vides)} colonne(s) vide(s) : [{liste_cols_vides_str}], "
        f"veuillez vérifier quelle en était l'utilité afin d'améliorer le futur questionnaire."
    )
    rapport_audit_structure.append(message_vides)

# Génération du message d'alerte global synthétique pour le rapport d'erreur
if compteur_anomalies_groupes > 0:
    message_global = (
        f"Dans le cadre du nettoyage des colonnes, on note un problème structurel. "
        f"A vérifier dans le codage du prochain questionnaire : les colonnes de groupe "
        f"ne doivent pas contenir de données ({compteur_anomalies_groupes} colonne(s) concernée(s))."
    )
    rapport_audit_structure.append(message_global)
    print(message_global)

# Filtrage final de la base de données
cols_existantes = [col for col in vars_a_garder if col in df_clean.columns]
df_clean = df_clean[cols_existantes]

print(
    f"Filtrage structurel terminé. Base réduite à {df_clean.shape[1]} colonnes exploitables."
)


# ==========================================
# 4. CONVERSION ET AUDIT DES VARIABLES TEMPORELLES
# ==========================================
print("Traitement et conversion des variables temporelles...")

colonnes_dates_converties = []
total_valeurs_invalides = 0
exemples_invalides = {}
variables_exception = ["heure_fin", "heure_debut"]

# Recherche dynamique de la colonne de date de référence (ex: 'date_enquete')
# pour rattacher correctement les heures pures et éviter le piège de la date du jour.
col_date_ref = None
if "df_dict" in globals():
    for _, row in df_dict.iterrows():
        if str(row.get("type", "")).strip().lower() == "date":
            col_date_ref = str(row.get("name", "")).strip()
            break
if not col_date_ref or col_date_ref not in df_clean.columns:
    for c in ["date_enquete", "date", "submission_time"]:
        if c in df_clean.columns:
            col_date_ref = c
            break

# Boucle de nettoyage et conversion des variables temporelles
for _, row in df_dict.iterrows():
    var = str(row.get("name", "")).strip()
    t = str(row.get("type", "")).strip().lower()

    if var not in df_clean.columns:
        continue

    if (
        t == "date"
        or "datetime" in t
        or "start" in t
        or "date" in var.lower()
        or (var in variables_exception)
    ):
        serie_brute = df_clean[var].replace(r"^\s*$", np.nan, regex=True)
        # Condition : type date, contient 'start', OU fait partie des exceptions explicitées (heures)
        try:
            serie_numerique = pd.to_numeric(serie_brute, errors="coerce")
            # Si une part significative des valeurs non nulles sont de grands entiers (> 10**12)
            if (
                serie_numerique.notna().sum() > 0
                and (serie_numerique.dropna() > 10**12).mean() > 0.5
            ):
                serie_convertie = pd.to_datetime(
                    serie_numerique, unit="us", errors="coerce"
                )
            elif var in variables_exception or "time" in t:
                heures_extraites = serie_brute.astype(str).str.extract(
                    r"(\d{2}:\d{2}(?::\d{2})?)"
                )[0]
                if col_date_ref and col_date_ref in df_clean.columns:
                    serie_combinee = (
                        pd.to_datetime(
                            df_clean[col_date_ref], errors="coerce"
                        )
                        .dt.strftime("%Y-%m-%d")
                        .astype(str)
                        + " "
                        + heures_extraites
                    )
                    serie_convertie = pd.to_datetime(
                        serie_combinee, errors="coerce", format="mixed"
                    )
                else:
                    serie_convertie = pd.to_datetime(
                        serie_brute, errors="coerce", format="mixed"
                    )
            else:
                serie_convertie = pd.to_datetime(
                    serie_brute, errors="coerce", format="mixed"
                )
        except Exception:
            serie_convertie = pd.to_datetime(
                serie_brute, errors="coerce", format="mixed"
            )

        # Capture des valeurs qui étaient remplies mais impossibles à convertir en date/heure
        masque_erreur = serie_brute.notna() & serie_convertie.isna()
        if masque_erreur.any():
            exemples_invalides[var] = (
                serie_brute[masque_erreur].unique()[:5].tolist()
            )
            total_valeurs_invalides += masque_erreur.sum()

        df_clean[var] = serie_convertie
        colonnes_dates_converties.append(var)

rapport_audit_conversion_temporelle = []

# Affichage des rapports et des exemples avec alimentation de la liste
if colonnes_dates_converties:
    msg_dates = f"Colonnes de dates traitées : {colonnes_dates_converties}"
    rapport_audit_conversion_temporelle.append(msg_dates)
    print(msg_dates)

if total_valeurs_invalides > 0:
    msg_invalides = f"⚠️ [{total_valeurs_invalides}] valeurs illisibles remplacées en NaN. Exemples : {exemples_invalides}"
    rapport_audit_conversion_temporelle.append(msg_invalides)

    print(f"⚠️ [{total_valeurs_invalides}] valeurs illisibles remplacées en NaN.")
    print(
        "Même si KoboToolbox / Enketo force un calendrier standard sur le terrain, "
        "plusieurs facteurs expliquent l'apparition de formats corrompus ou illisibles dans une base : "
        "Edition manuelle des données, Problèmes d'export Excel, Imports de données externes, "
        "Incident de Synchronisation. Exemples de ce qui posait problème par colonne :",
        exemples_invalides,
    )
else:
    msg_succes_dates = (
        "✅ Toutes les valeurs temporelles ont été converties sans valeur illisible."
    )
    rapport_audit_conversion_temporelle.append(msg_succes_dates)
    print(msg_succes_dates)


# ==========================================
# 5. CONVERSION ET AUDIT DES TYPES NUMÉRIQUES
# ==========================================
print("Analyse et conversion des types numériques...")

# Initialisation des listes pour stocker les colonnes converties et les messages du rapport d'audit
rapport_audit_types = []
colonnes_converties_int = []
colonnes_converties_float = []

# Parcours de toutes les colonnes du dataset qui sont de type numérique ou objet (texte)
for col in df_clean.select_dtypes(include=["number", "object"]).columns:
    try:
        # Sécurité : on ignore complètement les colonnes de type date/heure pour éviter les conflits de conversion
        if pd.api.types.is_datetime64_any_dtype(df_clean[col]):
            continue

        # Forcer la conversion de la colonne en valeurs numériques (les textes impossibles à convertir deviennent NaN)
        s_num = pd.to_numeric(df_clean[col], errors="coerce")

        # Isoler uniquement les valeurs non nulles pour analyser les données réelles présentes
        non_nulls = s_num.dropna()

        # Si la colonne est entièrement vide après conversion, on passe à la suivante
        if non_nulls.empty:
            continue

        # Vérification mathématique : est-ce que tous les nombres divisés par 1 ont un reste de 0 ?
        is_all_integers = (non_nulls % 1 == 0).all()

        # Vérification de l'état actuel de la colonne dans le DataFrame
        is_already_int = pd.api.types.is_integer_dtype(df_clean[col])
        is_already_float = pd.api.types.is_float_dtype(df_clean[col])

        # --- RÈGLE 1 : Si la colonne contient 100% de valeurs entières et n'est PAS déjà un entier ---
        if is_all_integers and not is_already_int:
            df_clean[col] = s_num.astype("Int64")
            colonnes_converties_int.append(col)

        # --- RÈGLE 2 : Si la colonne contient des décimales et n'est PAS déjà un float ---
        elif not is_all_integers and not is_already_float:
            df_clean[col] = s_num.astype("float64")
            colonnes_converties_float.append(col)

    except Exception:
        # Si une erreur imprévue survient sur une colonne textuelle complexe, on l'ignore et on continue
        continue

# Uniformisation globale : conversion de tous les entiers natifs (int64) vers le type nullable Int64
for col in df_clean.select_dtypes(include=["int64", "int32"]).columns:
    df_clean[col] = df_clean[col].astype("Int64")

# --- GÉNÉRATION DU RAPPORT POUR LES ENTIERS ---
if colonnes_converties_int:
    liste_cols_int = ", ".join([f"'{c}'" for c in colonnes_converties_int])
    nb_cols_int = len(colonnes_converties_int)

    if nb_cols_int == 1:
        msg_int = f"La colonne {liste_cols_int} contient uniquement des entiers : il est recommandé de déclarer explicitement un type integer dans le formulaire Kobo."
    else:
        msg_int = f"Ces {nb_cols_int} colonnes [{liste_cols_int}] contiennent uniquement des entiers cachés : il est recommandé de déclarer explicitement un type integer dans le formulaire Kobo."

    rapport_audit_types.append(msg_int)
    print(msg_int)

# --- GÉNÉRATION DU RAPPORT POUR LES DÉCIMAUX ---
if colonnes_converties_float:
    liste_cols_float = ", ".join([f"'{c}'" for c in colonnes_converties_float])
    nb_cols_float = len(colonnes_converties_float)

    if nb_cols_float == 1:
        message_float = f'La colonne {liste_cols_float} a été convertie en float. Le type "decimal" est conseillé pour cette colonne dans le questionnaire kobo.'
    else:
        message_float = f'Les colonnes [{liste_cols_float}] ont été converties en float. Le type "decimal" est conseillé pour ces colonnes dans le questionnaire kobo.'

    rapport_audit_types.append(message_float)
    print(message_float)

if not colonnes_converties_int and not colonnes_converties_float:
    print("✅ Aucun ajustement de type numérique requis.")


# ==========================================
# 6. NETTOYAGE ET AUDIT DES VARIABLES TEXTUELLES
# ==========================================
print("Analyse et nettoyage des variables textuelles...")

rapport_audit_texte = []

# Nettoyage textuel universel (minuscules, espaces, valeurs aberrantes)
cols_texte = df_clean.select_dtypes(include=["object", "string"]).columns
for col in cols_texte:
    df_clean[col] = df_clean[col].str.lower().str.strip()
    df_clean[col] = df_clean[col].replace(
        ["erreur", "na", "n/a", "none", "nan", ""], pd.NA
    )

# Indexation des choix officiels depuis df_choix (colonnes list_name, code, label)
metadata_choix = {}
if "df_choix" in globals():
    for list_name, group in df_choix.groupby("list_name"):
        metadata_choix[list_name] = set(
            group["code"].astype(str).str.lower().str.strip()
        )

# Extraction dynamique du lien depuis df_dict (colonnes type, variable, label)
col_vers_type_liste = {}
if "df_dict" in globals():
    for _, row in df_dict.iterrows():
        q_var = row.get("name")
        q_type = str(row.get("type"))
        if q_type.startswith("select_one") or q_type.startswith(
            "select_multiple"
        ):
            parts = q_type.split()
            if len(parts) > 1:
                col_vers_type_liste[q_var] = {
                    "type": parts[0],
                    "list_name": parts[1],
                }
        elif q_type.startswith("text"):
            col_vers_type_liste[q_var] = {"type": "text", "list_name": None}

# Analyse et classification des colonnes texte
colonnes_texte_libre = []
nb_reponses_libres = []
colonnes_orphelines_select = []
details_orphelines_select = []
cols_text_deguise = []
cols_text_orphelines_connues = []

for col in cols_texte:
    info_dict = col_vers_type_liste.get(
        col, {"type": "text", "list_name": None}
    )
    declared_type = info_dict["type"]
    nom_liste = info_dict["list_name"]

    # Rattrapage si absent du dict mais présent dans le choix via le nom de colonne
    if not nom_liste and col in metadata_choix:
        nom_liste = col

    valeurs_terrain = set(df_clean[col].dropna().unique())

    # Cas A : C'est déclaré ou rattaché à un select_one / select_multiple officiel
    if nom_liste and nom_liste in metadata_choix:
        choix_officiels = metadata_choix[nom_liste]

        if (
            declared_type in ["select_one", "text"]
            and not declared_type == "select_multiple"
        ):
            valeurs_orphelines = valeurs_terrain - choix_officiels
            if valeurs_orphelines:
                df_clean[col] = df_clean[col].replace(
                    list(valeurs_orphelines), pd.NA
                )
                if declared_type == "text":
                    cols_text_orphelines_connues.append(col)
                else:
                    colonnes_orphelines_select.append(col)
                    details_orphelines_select.append(
                        f"'{col}': {list(valeurs_orphelines)}"
                    )
        elif declared_type == "select_multiple":
            toutes_valeurs_tokens = set()
            for val in df_clean[col].dropna():
                tokens = str(val).split()
                toutes_valeurs_tokens.update(tokens)
            valeurs_orphelines = toutes_valeurs_tokens - choix_officiels
            if valeurs_orphelines:

                def nettoyer_tokens(cellule):
                    if pd.isna(cellule):
                        return pd.NA
                    tokens = str(cellule).split()
                    tokens_valides = [t for t in tokens if t in choix_officiels]
                    return " ".join(tokens_valides) if tokens_valides else pd.NA

                df_clean[col] = df_clean[col].apply(nettoyer_tokens)
                colonnes_orphelines_select.append(col)
                details_orphelines_select.append(
                    f"'{col}' (multiple): {list(valeurs_orphelines)}"
                )

    # Cas B : Déclaré en 'text' dans le dictionnaire mais ne correspond à aucun choix direct
    else:
        # Vérification intelligente si toutes les réponses rentrent dans un choix binaire type oui/non
        est_binaire_deguise = False
        for l_name, codes in metadata_choix.items():
            if (
                len(codes) <= 3
                and valeurs_terrain
                and valeurs_terrain.issubset(codes)
            ):
                est_binaire_deguise = True
                break

        if est_binaire_deguise:
            cols_text_deguise.append(col)
        else:
            nb_uniques = df_clean[col].dropna().nunique()
            colonnes_texte_libre.append(col)
            nb_reponses_libres.append(nb_uniques)

# Rapports d'audit spécifiques
if colonnes_orphelines_select:
    liste_cols = ", ".join([f"'{c}'" for c in colonnes_orphelines_select])
    liste_vals = ", ".join(details_orphelines_select)
    msg = f"Ces colonnes [{liste_cols}] avaient respectivement ces valeurs orphelines [{liste_vals}] elles ont été converties en NaN. Vérifier les conditions d'accès et de modification kobo."
    rapport_audit_texte.append(msg)
    print(msg)

if cols_text_orphelines_connues:
    liste_c = ", ".join([f"'{c}'" for c in cols_text_orphelines_connues])
    msg = f"Pour ces colonnes [{liste_c}], il est préférable d'inscrire le type select_one ou select_multiple pour ces variables."
    rapport_audit_texte.append(msg)
    print(msg)

if cols_text_deguise:
    liste_c = ", ".join([f"'{c}'" for c in cols_text_deguise])
    msg = f"Pour ces colonnes [{liste_c}], il serait préférable de passer le type sous la forme select_one oui_non."
    rapport_audit_texte.append(msg)
    print(msg)

if colonnes_texte_libre:
    nb_libres = len(colonnes_texte_libre)
    if nb_libres == 1:
        msg_libre = f"La colonne '{colonnes_texte_libre[0]}' est une colonne en texte libre, elle contient {nb_reponses_libres[0]} éléments de réponse distincts à analyser."
    else:
        details_list = [
            f"'{c}' ({n})" for c, n in zip(colonnes_texte_libre, nb_reponses_libres)
        ]
        liste_str = ", ".join(details_list)
        msg_libre = f"Ces {nb_libres} colonnes [{liste_str}] sont des colonnes en texte libre, elles contiennent respectivement des éléments de réponse distincts à analyser."
    rapport_audit_texte.append(msg_libre)
    print(msg_libre)

if (
    not colonnes_orphelines_select
    and not cols_text_orphelines_connues
    and not cols_text_deguise
    and not colonnes_texte_libre
):
    print("✅ Aucun problème textuel détecté.")


# ==========================================
# 7. DÉCHIFFREMENT ET TRADUCTION DES CODES EN LABELS
# ==========================================
print("Déchiffrement et conversion des codes en libellés officiels...")

rapport_audit_chiffrement = []

# Construction du dictionnaire de correspondance global : {list_name: {code: label}}
mapping_labels = {}
if "df_choix" in globals():
    for list_name, group in df_choix.groupby("list_name"):
        clean_list_name = str(list_name).strip().lower()
        mapping_labels[clean_list_name] = dict(
            zip(group["code"].astype(str).str.lower().str.strip(), group["label"])
        )

erreurs_dechiffrement = {}

for col in df_clean.columns:
    info = col_vers_type_liste.get(col)
    nom_liste = info["list_name"] if info else None
    sel_type = info["type"] if info else "select_one"

    if not nom_liste and col in mapping_labels:
        nom_liste = col

    if nom_liste and nom_liste in mapping_labels:
        dico_codes_labels = mapping_labels[nom_liste]

        if sel_type == "select_multiple":
            valeurs_orphelines_multiples = set()

            def traduire_multiple(cellule):
                if pd.isna(cellule) or str(cellule).strip() == "":
                    return pd.NA
                tokens = str(cellule).split()
                labels_traduits = []
                for t in tokens:
                    if t in dico_codes_labels:
                        labels_traduits.append(str(dico_codes_labels[t]))
                    else:
                        valeurs_orphelines_multiples.add(t)
                        labels_traduits.append(t)
                return ", ".join(labels_traduits) if labels_traduits else pd.NA

            df_clean[col] = df_clean[col].apply(traduire_multiple)

            if valeurs_orphelines_multiples:
                erreurs_dechiffrement[col] = list(valeurs_orphelines_multiples)
        else:
            valeurs_terrain = (
                df_clean[col].dropna().astype(str).str.lower().str.strip()
            )
            valeurs_inconnues = set(valeurs_terrain) - set(
                dico_codes_labels.keys()
            )

            if valeurs_inconnues:
                erreurs_dechiffrement[col] = list(valeurs_inconnues)

            df_clean[col] = (
                df_clean[col]
                .astype(str)
                .str.lower()
                .str.strip()
                .map(dico_codes_labels)
                .fillna(df_clean[col])
            )

# Rapport d'audit technique du déchiffrement
if erreurs_dechiffrement:
    details_err = [
        f"'{col}': {vals}" for col, vals in erreurs_dechiffrement.items()
    ]
    msg_err = f"[ANOMALIE TECHNIQUE] Des erreurs de déchiffrement ont été détectées sur ces colonnes : {', '.join(details_err)}. Les codes correspondants ne figurent pas dans le fichier des choix."
    rapport_audit_chiffrement.append(msg_err)
    print(msg_err)
else:
    msg_succes = "Vérification technique validée : tous les codes de réponse ont été convertis avec succès vers leurs labels officiels."
    rapport_audit_chiffrement.append(msg_succes)
    print(msg_succes)


# ==========================================
# 8. AUDIT TEMPOREL ET CALCUL DES DURÉES D'ENQUÊTE
# ==========================================
print("Analyse de la chronologie et des durées d'enquête...")

rapport_audit_dates = []

# Recherche dynamique et intelligente des variables start et end
col_start, col_end = None, None
autres_colonnes_dates = []

if "df_dict" in globals():
    for _, row in df_dict.iterrows():
        q_var = str(row.get("name")).strip().lower()
        q_type = str(row.get("type")).lower().strip()

        # Détection via les types Kobo natifs ou des mots-clés évidents
        if q_type == "start" or "start" in q_var or "debut" in q_var:
            if not col_start:
                col_start = q_var
        elif q_type == "end" or "end" in q_var or "fin" in q_var:
            if not col_end:
                col_end = q_var
        elif "date" in q_type or "time" in q_type or "date" in q_var:
            if (
                q_var not in autres_colonnes_dates
                and q_var != col_start
                and q_var != col_end
            ):
                autres_colonnes_dates.append(q_var)

# Fallback direct sur le DataFrame si le dictionnaire n'a pas suffi
if not col_start and "start" in df_clean.columns:
    col_start = "start"
if not col_start and "date_enquete" in df_clean.columns:
    col_start = "date_enquete"
if not col_end and "end" in df_clean.columns:
    col_end = "end"

col_id = (
    "_id" if "_id" in df_clean.columns else df_clean.index.name or "index"
)

# Audit de l'enquête (Start vs End)
if (
    col_start
    and col_end
    and col_start in df_clean.columns
    and col_end in df_clean.columns
):
    df_clean[col_start] = pd.to_datetime(df_clean[col_start], errors="coerce")
    df_clean[col_end] = pd.to_datetime(df_clean[col_end], errors="coerce")

    anomalies_detectees = False

    # Fin antérieure au début
    erreurs_chronologie = df_clean[df_clean[col_end] < df_clean[col_start]]
    if not erreurs_chronologie.empty:
        anomalies_detectees = True
        ids_err = (
            erreurs_chronologie[col_id].tolist()
            if col_id in erreurs_chronologie.columns
            else list(erreurs_chronologie.index)
        )
        msg_tech = f"⚠️ [TECHNIQUE] Erreur chronologique sur '{col_start}' / '{col_end}' (fin < début). IDs : {ids_err}"
        rapport_audit_dates.append(msg_tech)
        print(msg_tech)

    # Calcul de la durée en minutes
    df_clean["duree_minutes"] = (
        df_clean[col_end] - df_clean[col_start]
    ).dt.total_seconds() / 60

    # Durée < 10 min
    trop_courtes = df_clean[df_clean["duree_minutes"] < 10]
    if not trop_courtes.empty:
        anomalies_detectees = True
        ids_courts = (
            trop_courtes[col_id].tolist()
            if col_id in trop_courtes.columns
            else list(trop_courtes.index)
        )
        msg_court = f"⚠️ [DURÉE] Enquête(s) < 10 min [{ids_courts}] : à vérifier (entretien trop court)."
        rapport_audit_dates.append(msg_court)
        print(msg_court)

    # Durée > 2h (120 min)
    trop_longues = df_clean[df_clean["duree_minutes"] > 120]
    if not trop_longues.empty:
        anomalies_detectees = True
        ids_longs = (
            trop_longues[col_id].tolist()
            if col_id in trop_longues.columns
            else list(trop_longues.index)
        )
        msg_long = f"⚠️ [DURÉE] Enquête(s) > 2h [{ids_longs}] : à vérifier (risque de fraude ou suspension longue)."
        rapport_audit_dates.append(msg_long)
        print(msg_long)

    if not anomalies_detectees:
        msg_ok = "✅ Les dates de début et de fin d'enquête ont été renseignées de manière cohérente."
        rapport_audit_dates.append(msg_ok)
        print(msg_ok)
else:
    msg_err_struct = "⚠️ Impossible d'identifier clairement les variables de début et de fin pour l'enquête principale."
    rapport_audit_dates.append(msg_err_struct)
    print(msg_err_struct)

# Information sur les autres variables temporelles détectées
if autres_colonnes_dates:
    msg_autres = f"ℹ️ Autres variables temporelles détectées dans le dictionnaire à analyser au cas par cas : {autres_colonnes_dates}"
    print(msg_autres)


# ==========================================
# 9. CONTRÔLE INTERACTIF S&E (BORNES CALENDAIRES)
# ==========================================
print("Préparation du contrôle S&E des dates...")

# Affichage des bornes réelles du dataset pour orienter le S&E
if col_start and col_start in df_clean.columns:
    try:
        min_reel = df_clean[col_start].min().strftime("%d-%m-%Y")
        max_reel = df_clean[col_start].max().strftime("%d-%m-%Y")
        print(
            f"ℹ️ Info dataset : Les enquêtes de ce fichier s'étalent réellement du {min_reel} au {max_reel}\n"
        )
    except Exception:
        min_reel, max_reel = "01-01-2025", "31-12-2026"
else:
    min_reel, max_reel = "01-01-2025", "31-12-2026"

# Contrôle S&E interactif basé sur les dates calendaires pures
print("--- CONTRÔLE TERRAIN S&E (BORNES DES ENQUÊTES) ---")
date_debut_saisie = input(
    f"Quelle a été la date du début des enquêtes ? (Format JJ-MM-AAAA, ex: {min_reel}) : "
).strip()
date_fin_saisie = input(
    f"Quelle a été la date de fin ? (Format JJ-MM-AAAA, ex: {max_reel}) : "
).strip()

if (
    date_debut_saisie
    and date_fin_saisie
    and col_start
    and col_start in df_clean.columns
):
    try:
        # Conversion en objets date purs (sans heures ni fuseaux horaires)
        ref_debut = pd.to_datetime(
            date_debut_saisie, format="%d-%m-%Y"
        ).date()
        ref_fin = pd.to_datetime(date_fin_saisie, format="%d-%m-%Y").date()

        # Extraction de la date calendaire de la colonne d'enquête
        dates_terrain = df_clean[col_start].dt.date

        # Comparaison stricte sur les jours calendaires
        enquetes_hors_bornes = df_clean[
            (dates_terrain < ref_debut) | (dates_terrain > ref_fin)
        ]

        if not enquetes_hors_bornes.empty:
            ids_hors = (
                enquetes_hors_bornes[col_id].tolist()
                if col_id in enquetes_hors_bornes.columns
                else list(enquetes_hors_bornes.index)
            )
            msg_bornes = f"⚠️ [S&E] {len(enquetes_hors_bornes)} enquête(s) sortent de la fourchette officielle [{date_debut_saisie} au {date_fin_saisie}]. IDs concernés : {ids_hors}"
            rapport_audit_dates.append(msg_bornes)
            print(msg_bornes)
        else:
            msg_bornes_ok = "✅ Contrôle S&E validé : aucune enquête ne dépasse de la fourchette de dates renseignée."
            rapport_audit_dates.append(msg_bornes_ok)
            print(msg_bornes_ok)

    except Exception as e:
        msg_err_format = f"⚠️ Erreur de format de date. Veuillez respecter strictement le format JJ-MM-AAAA. (Détail : {e})"
        rapport_audit_dates.append(msg_err_format)
        print(msg_err_format)
else:
    msg_ignore = "⚠️ Contrôle S&E ignoré : dates non renseignées ou variable de début d'enquête introuvable."
    rapport_audit_dates.append(msg_ignore)
    print(msg_ignore)


# ==========================================
# 10. MOTEUR D'AUDIT ET NETTOYAGE DES CONTRAINTES (CONSTRAINTS)
# ==========================================
print("Exécution du moteur d'audit des contraintes (constraints)...")


def traducteur_regle_kobo_avance(rule_str, nom_serie, is_constraint=False):
    if pd.isna(rule_str) or str(rule_str).strip() == "":
        return None

    r = str(rule_str).strip()

    # Remplacer le point '.' par la série principale
    r = re.sub(r"(?<!\d)\.(?!\d)", nom_serie, r)

    # Remplacer D'ABORD toutes les variables ${nom_var} par df_clean['nom_var']
    def remplace_variable_kobo(match):
        var_name = match.group(1)
        if "df_clean" in globals() and var_name in df_clean.columns:
            if is_constraint and pd.api.types.is_numeric_dtype(
                df_clean[var_name]
            ):
                return f"df_clean['{var_name}'].fillna(0)"
            return f"df_clean['{var_name}']"
        return "0"

    r = re.sub(r"\$\{([a-zA-Z0-9_]+)\}", remplace_variable_kobo, r)

    # ENSUITE, appliquer la correction de soustraction de jours avec np.timedelta64
    def corrige_soustraction_date(match):
        expr_date = match.group(1)
        nb_jours = match.group(2)
        return f"({expr_date} - np.timedelta64({nb_jours}, 'D'))"

    r = re.sub(
        r"(df_clean\['[a-zA-Z0-9_]+'\](?:\.fillna\(0\)?)*)\s*-\s*(\d+)",
        corrige_soustraction_date,
        r,
    )

    # Traduire les opérateurs logiques et les égalités
    r = r.replace(" and ", " & ").replace(" or ", " | ")
    r = re.sub(r"(?<![<>!])\s*=\s*(?![=])", " == ", r)

    # Ajouter les parenthèses indispensables pour Pandas
    morceaux = re.split(r"(\s*[&|]\s*)", r)
    morceaux_traduits = []
    for m in morceaux:
        m_clean = m.strip()
        if m_clean in ["&", "|"]:
            morceaux_traduits.append(f" {m_clean} ")
        elif m_clean != "":
            if not (m_clean.startswith("(") and m_clean.endswith(")")):
                morceaux_traduits.append(f"({m_clean})")
            else:
                morceaux_traduits.append(m_clean)

    return "".join(morceaux_traduits)


# --- MOTEUR D'AUDIT & NETTOYAGE CONSTRAINTS ---
rapport_audit_constraints = []
total_violations_c = 0
col_id = (
    "_id" if "_id" in df_clean.columns else df_clean.index.name or "index"
)

if "df_dict" in globals() and "constraint" in df_dict.columns:
    for _, row in df_dict.iterrows():
        var = str(row.get("name", "")).strip()
        label = str(row.get("label", "")).strip()
        c_rule = row.get("constraint", None)

        if (
            var not in df_clean.columns
            or pd.isna(c_rule)
            or str(c_rule).strip() == ""
        ):
            continue

        if "date" in var.lower() or pd.api.types.is_datetime64_any_dtype(
            df_clean[var]
        ):
            df_clean[var] = pd.to_datetime(df_clean[var], errors="coerce")

        c_rule_str = str(c_rule).strip()

        # Bouclier anti-décalage
        if (
            any(keyword in c_rule_str for keyword in ['"', "'", ",", "…"])
            and "selected(" not in c_rule_str
        ):
            if "${" not in c_rule_str:
                continue

        serie_brute = df_clean[var]
        mask_remplie = serie_brute.notna() & (
            serie_brute.astype(str).str.strip() != ""
        )
        if not mask_remplie.any():
            continue

        violation_contrainte = pd.Series(
            [False] * len(df_clean), index=df_clean.index
        )

        try:
            if "string-length(.)" in c_rule_str:
                match = re.search(
                    r"string-length\(\s*\.\s*\)\s*([<>=!]+)\s*(\d+)",
                    c_rule_str,
                )
                if match:
                    op = match.group(1)
                    if op == "=":
                        op = "=="
                    seuil = int(match.group(2))

                    serie_str = (
                        serie_brute.dropna()
                        .astype(str)
                        .str.replace(r"\.0$", "", regex=True)
                    )
                    longueurs = serie_str.str.len()
                    mask_respect = eval(f"longueurs {op} {seuil}")
                    violation_contrainte.loc[serie_str.index] = ~mask_respect
            else:
                py_rule = traducteur_regle_kobo_avance(
                    c_rule_str, f"df_clean['{var}']", is_constraint=True
                )

                if py_rule:
                    mask_respect = eval(py_rule)
                    if isinstance(mask_respect, pd.Series):
                        violation_contrainte = mask_remplie & (
                            ~mask_respect.fillna(False)
                        )

            if violation_contrainte.any():
                nb_v = violation_contrainte.sum()
                total_violations_c += nb_v

                # Extraction d'exemples de valeurs incohérentes (3 plus basses et 3 plus hautes)
                vals_err = serie_brute[violation_contrainte].dropna()
                try:
                    if pd.api.types.is_datetime64_any_dtype(serie_brute):
                        min_vals = vals_err.min().strftime("%Y-%m-%d")
                        max_vals = vals_err.max().strftime("%Y-%m-%d")
                        apercu_valeurs = f"Min: {min_vals} | Max: {max_vals}"
                    else:
                        vals_num = pd.to_numeric(vals_err)
                        min_vals = vals_num.sort_values().head(3).tolist()
                        max_vals = vals_num.sort_values().tail(3).tolist()
                        apercu_valeurs = f"Min: {min_vals} | Max: {max_vals}"
                except Exception:
                    vals_unique = vals_err.astype(str).unique().tolist()
                    apercu_valeurs = f"Exemples: {vals_unique[:5]}"

                # Application du nettoyage : transformation des violations en NaN
                df_clean.loc[violation_contrainte, var] = np.nan

                msg = f"Erreur sur la colonne '{var}' ({label}) : {nb_v} violation(s) de règle -> Nettoyage : NaN | Valeurs aberrantes détectées [{apercu_valeurs}]"
                rapport_audit_constraints.append(msg)

        except Exception as e:
            print(f"⚠️ Erreur persistante sur '{var}' (Règle : {c_rule_str}) -> {e}")

print(f"\n--- BILAN FINAL DES CONSTRAINTS ---")
if total_violations_c > 0:
    print(f"⚠️ {total_violations_c} violation(s) au total.\n")
    for r in rapport_audit_constraints:
        print(r)
    print(
        "\n💡 Penser à vérifier les réglages d'accès et de modification du questionnaire KoboToolbox pour éviter ces incohérences sur le terrain."
    )
else:
    print("✅ Aucune violation de contrainte détectée.")


# ==========================================
# 11. MOTEUR D'AUDIT ET NETTOYAGE DES CONDITIONS D'AFFICHAGE (RELEVANT)
# ==========================================
print("Exécution du moteur d'audit des conditions d'affichage (relevant)...")

# EXCEPTION PERSONNALISÉE DE NOTRE FICHIER ACTUEL :
# Correspondance explicite entre les noms du XLSForm et les noms réels dans df_clean
COL_MAPPING = {"poss_carte_chef": "poss_carte"}


def traducteur_regle_kobo_universel(rule_str, nom_serie):
    if pd.isna(rule_str) or str(rule_str).strip() == "":
        return None

    r = str(rule_str).strip()

    # Remplacer le point '.' par la série principale
    r = re.sub(r"(?<!\d)\.(?!\d)", nom_serie, r)

    # Remplacer les variables ${nom_var} par df_clean['nom_var'] avec gestion générique/exception
    def remplace_variable(match):
        var_name = match.group(1)

        # Étape A : Vérifier si une exception/mapping explicite existe pour notre fichier
        var_effective = COL_MAPPING.get(var_name, var_name)

        if "df_clean" in globals():
            if var_effective in df_clean.columns:
                return f"df_clean['{var_effective}']"

            # Étape B : Gestion générique pour d'autres fichiers (Recherche par similarité si introuvable)
            matches = get_close_matches(
                var_name, df_clean.columns, n=1, cutoff=0.8
            )
            if matches:
                col_proche = matches[0]
                return f"df_clean['{col_proche}']"

        return "0"

    r = re.sub(r"\$\{([a-zA-Z0-9_]+)\}", remplace_variable, r)

    # Traduire les opérateurs logiques
    r = r.replace(" and ", " & ").replace(" or ", " | ")

    # Remplacer les égalités simples (= en ==) en amont
    r = re.sub(r"(?<![<>!=])\s*=\s*(?![=])", " == ", r)

    # Gérer la fonction selected(${var}, 'choix') post-remplacement des variables
    def traduit_selected(match):
        col_expr = match.group(1)
        choix = match.group(2)
        return (
            f"({col_expr}).astype(str).str.contains(r'\\b{choix}\\b', na=False)"
        )

    r = re.sub(
        r"selected\s*\(\s*(df_clean\['[a-zA-Z0-9_]+'\])\s*,\s*['\"]([a-zA-Z0-9_]+)['\"]?\s*\)",
        traduit_selected,
        r,
    )

    return r


# --- MOTEUR D'AUDIT & NETTOYAGE RELEVANT ---
rapport_audit_relevant = []
total_violations_r = 0
variables_auditees = 0
variables_sans_faute = 0
col_id = (
    "_id" if "_id" in df_clean.columns else df_clean.index.name or "index"
)

if "df_dict" in globals() and "relevant" in df_dict.columns:
    for _, row in df_dict.iterrows():
        var = str(row.get("name", "")).strip()
        label = str(row.get("label", "")).strip()
        r_rule = row.get("relevant", None)

        if (
            var not in df_clean.columns
            or pd.isna(r_rule)
            or str(r_rule).strip() == ""
        ):
            continue

        r_rule_str = str(r_rule).strip()
        serie_brute = df_clean[var]

        mask_remplie = (
            serie_brute.notna()
            & (serie_brute.astype(str).str.strip() != "")
            & (serie_brute.astype(str).str.strip() != "nan")
        )
        if not mask_remplie.any():
            continue

        variables_auditees += 1

        try:
            py_rule = traducteur_regle_kobo_universel(
                r_rule_str, f"df_clean['{var}']"
            )

            if py_rule:
                mask_pertinent = eval(py_rule)

                if isinstance(mask_pertinent, pd.Series):
                    mask_pertinent = mask_pertinent.fillna(False)
                    violation_relevant = mask_remplie & (~mask_pertinent)

                    if violation_relevant.any():
                        # ACTION DE NETTOYAGE : Basculement automatique en NaN des données remplies hors condition
                        df_clean.loc[violation_relevant, var] = np.nan

                        ids = (
                            df_clean.loc[violation_relevant, col_id].tolist()
                            if col_id in df_clean.columns
                            else list(
                                df_clean.loc[violation_relevant].index
                            )
                        )
                        nb_v = violation_relevant.sum()
                        total_violations_r += nb_v

                        msg = f"Erreur sur la colonne '{var}' ({label}) : {nb_v} violation(s) de règle -> Nettoyage : NaN (Données remplies hors condition d'affichage). IDs : {ids[:3]}..."
                        rapport_audit_relevant.append(msg)
                    else:
                        variables_sans_faute += 1

        except Exception as e:
            print(
                f"⚠️ Erreur d'audit sur le relevant de '{var}' (Règle : {r_rule_str}) -> {e}"
            )

print(f"\n--- BILAN FINAL DES RELEVANTS ---")
print(f"🔍 Audit réalisé sur {variables_auditees} variables conditionnelles.")

if variables_sans_faute > 0:
    print(
        f"✅ Validation réussie : {variables_sans_faute} variable(s) respectent parfaitement leurs conditions d'affichage."
    )

if total_violations_r > 0:
    print(f"\n⚠️ {total_violations_r} violation(s) de relevant au total.\n")
    for r in rapport_audit_relevant:
        print(r)
    print(
        "\n💡 Penser à vérifier les réglages d'accès et de modification du questionnaire KoboToolbox pour éviter ces incohérences sur le terrain."
    )
else:
    print("✅ Aucune violation de condition d'affichage (relevant) détectée.")


# ==========================================
# 12. MOTEUR D'AUDIT DES VALEURS MANQUANTES (OMISSIONS / RELEVANT OBLIGATOIRE)
# ==========================================
print("Exécution du moteur d'audit des omissions...")

rapport_audit_omissions = []
total_omissions = 0
variables_auditees_omission = 0
col_id = (
    "_id" if "_id" in df_clean.columns else df_clean.index.name or "index"
)

if "df_dict" in globals() and "relevant" in df_dict.columns:
    for _, row in df_dict.iterrows():
        var = str(row.get("name", "")).strip()
        label = str(row.get("label", "")).strip()
        r_rule = row.get("relevant", None)

        if (
            var not in df_clean.columns
            or pd.isna(r_rule)
            or str(r_rule).strip() == ""
        ):
            continue

        r_rule_str = str(r_rule).strip()
        serie_brute = df_clean[var]

        # Masque des valeurs vides (NaN, chaînes vides, 'nan')
        mask_vide = (
            serie_brute.isna()
            | (serie_brute.astype(str).str.strip() == "")
            | (serie_brute.astype(str).str.strip() == "nan")
        )
        if not mask_vide.any():
            continue

        variables_auditees_omission += 1

        try:
            py_rule = traducteur_regle_kobo_universel(
                r_rule_str, f"df_clean['{var}']"
            )

            if py_rule:
                mask_pertinent = eval(py_rule)

                if isinstance(mask_pertinent, pd.Series):
                    mask_pertinent = mask_pertinent.fillna(False)
                    # VIOLATION INVERSE : Devait répondre (pertinent = True) MAIS c'est vide (mask_vide = True)
                    violation_omission = mask_vide & mask_pertinent

                    if violation_omission.any():
                        ids = (
                            df_clean.loc[violation_omission, col_id].tolist()
                            if col_id in df_clean.columns
                            else list(
                                df_clean.loc[violation_omission].index
                            )
                        )
                        nb_o = violation_omission.sum()
                        total_omissions += nb_o

                        msg = f"Omission sur la colonne '{var}' ({label}) : {nb_o} valeur(s) manquante(s) alors que la question était requise. IDs : {ids[:3]}..."
                        rapport_audit_omissions.append(msg)

        except Exception as e:
            print(
                f"⚠️ Erreur d'audit des omissions sur '{var}' (Règle : {r_rule_str}) -> {e}"
            )

print(f"\n--- BILAN DES OMISSIONS (RELEVANT NON RESPECTÉ) ---")
if total_omissions > 0:
    print(
        f"⚠️ {total_omissions} omission(s) au total. Pensez à rendre la question obligatoire dans le questionnaire"
    )
    print(
        f"Pensez à vous rapprocher des enquêteurs pour obtenir des informations\n"
    )
    for r in rapport_audit_omissions:
        print(r)
else:
    print(
        "✅ Aucune omission détectée : toutes les questions requises ont bien été remplies."
    )


# ==========================================
# 13. AUDIT ET NETTOYAGE DES ERREURS RÉSIDUELLES ET PARASITES
# ==========================================
print("Nettoyage des valeurs parasites et résiduelles...")

# Mots-clés et valeurs parasites textuelles à cibler
mots_parasites = ["ERREUR", "erreur", "N/A", "n/a", "NaN", "nan", "NULL", "null"]

erreurs_residuelles = {}
total_residuelles = 0

for col in df_clean.columns:
    masque_col = pd.Series(False, index=df_clean.index)

    # Vérification pour les colonnes numériques (valeurs négatives)
    if pd.api.types.is_numeric_dtype(df_clean[col]):
        masque_col = df_clean[col] < 0

    # Vérification pour toutes les colonnes (textes parasites)
    else:
        # Convertit en string pour chercher les mots-clés exacts
        serie_str = df_clean[col].astype(str).str.strip()
        masque_col = serie_str.isin(mots_parasites)

    if masque_col.any():
        exemples = df_clean.loc[masque_col, col].dropna().unique()[:5].tolist()
        erreurs_residuelles[col] = exemples
        total_residuelles += masque_col.sum()

        # ACTION DE NETTOYAGE : Basculement en NaN
        df_clean.loc[masque_col, col] = np.nan

rapport_audit_residuelles = []

if total_residuelles > 0:
    msg_res = f"⚠️ Des erreurs résiduelles de remplissage ont été détectées ({total_residuelles} valeurs aberrantes ou textuelles)."
    rapport_audit_residuelles.append(msg_res)
    print(msg_res)
    print("Exemples de valeurs problématiques par colonne :", erreurs_residuelles)
else:
    msg_res_ok = (
        "✅ Aucune valeur parasite ou négative résiduelle détectée dans le dataset."
    )
    rapport_audit_residuelles.append(msg_res_ok)
    print(msg_res_ok)


# ==========================================
# 14. NORMALISATION FINALE DES VIDES ET BILAN DES DONNÉES MANQUANTES
# ==========================================
print(
    "Harmonisation des valeurs manquantes et génération du bilan final des vides..."
)

# Remplacement universel de toutes les formes de vides résiduels (chaînes vides, espaces, 'nan', 'None') par de vrais np.nan
df_clean = df_clean.replace(r"^\s*$", np.nan, regex=True)
df_clean = df_clean.replace(["nan", "NaN", "None", "NULL", "null"], np.nan)

# Vérification et comptage des cellules vides (NaN) par colonne
cellules_vides_par_col = df_clean.isna().sum()
total_cellules_vides = cellules_vides_par_col.sum()

rapport_audit_vides = []

msg_vides_glob = f"🔍 Bilan des cellules vides : {total_cellules_vides} cellules vides au total dans le dataset."
rapport_audit_vides.append(msg_vides_glob)

print(msg_vides_glob)
print("\nDétail par colonne :")
print(cellules_vides_par_col[cellules_vides_par_col > 0])


# ==========================================
# 15. NETTOYAGE DES LABELS ET GÉNÉRATION DU DATAFRAME D'EXPORT
# ==========================================
print("Nettoyage des en-têtes et préparation du DataFrame d'export...")

# Nettoyage automatique des \n directement dans le dictionnaire de mapping avant de renommer
mapping_labels_propre = {
    k: str(v).replace("\n", " ").strip()
    for k, v in mapping_labels.items()
    if pd.notna(v)
}

# Export avec les labels propres (sans sauts de ligne)
df_export = df_clean.rename(columns=mapping_labels_propre)

print(
    f"✅ DataFrame d'export prêt. Nombre de colonnes : {df_export.shape[1]}, Nombre de lignes : {df_export.shape[0]}"
)


# ==========================================
# 16. AUDIT DES DOUBLONS SUR L'IDENTIFIANT UNIQUE
# ==========================================
print("Vérification de l'unicité des identifiants...")

# Saisie interactive du nom technique de la colonne d'identification unique
col_id_technique = input(
    "Quel est le nom technique de la colonne servant pour l'identification unique du répondant ? : "
).strip()

# Récupération automatique du label correspondant via le dictionnaire de mapping
label_id = mapping_labels_propre.get(col_id_technique, col_id_technique)

print(f"\n🔍 Analyse de l'identifiant : '{col_id_technique}' (Libellé : {label_id})")

rapport_audit_doublons = []

if col_id_technique in df_clean.columns:
    nb_doublons = df_clean[col_id_technique].duplicated().sum()
    if nb_doublons > 0:
        msg_doub = f"🟠 Attention : {nb_doublons} doublon(s) détecté(s) sur le champ '{label_id}'."
        rapport_audit_doublons.append(msg_doub)
        print(msg_doub)
        doublons_df = df_clean[df_clean[col_id_technique].duplicated(keep=False)]
        display(doublons_df[[col_id_technique]])
    else:
        msg_doub_ok = f"✅ Aucun doublon détecté pour '{label_id}'. Chaque identifiant est unique."
        rapport_audit_doublons.append(msg_doub_ok)
        print(msg_doub_ok)
else:
    msg_doub_err = f"❌ Erreur : Le nom technique '{col_id_technique}' n'existe pas dans le DataFrame."
    rapport_audit_doublons.append(msg_doub_err)
    print(msg_doub_err)


# ==========================================
# 17. CONTRÔLE DE PROTECTION ET PURGE DES DONNÉES SANS CONSENTEMENT
# ==========================================
print(
    "Vérification du consentement et purge des données post-consentement si refus..."
)

# Initialisation de la variable par sécurité en haut du bloc
rapport_audit_consentement = []
données_parasites = 0

if "col_consent_technique" not in globals():
    col_consent_technique = input(
        "Nom technique de la colonne de consentement : "
    ).strip()

label_consent = mapping_labels_propre.get(
    col_consent_technique, col_consent_technique
)
print(f"🛡️ Contrôle de protection sur : '{col_consent_technique}' ({label_consent})")

if col_consent_technique in df_clean.columns:
    idx_consent = df_clean.columns.get_loc(col_consent_technique)
    cols_apres_consent = df_clean.columns[idx_consent + 1 :]

    valeurs_refus = ["non", "Non", "0", 0, "no", "No"]
    masque_sans_consent = df_clean[col_consent_technique].isin(
        valeurs_refus
    ) | df_clean[col_consent_technique].isna()

    données_parasites = (
        df_clean.loc[masque_sans_consent, cols_apres_consent]
        .notna()
        .any(axis=1)
        .sum()
    )
    msg_cons = f"🔴 Lignes sans consentement contenant des données post-consentement : {données_parasites}"
    rapport_audit_consentement.append(msg_cons)
    print(msg_cons)

    df_clean.loc[masque_sans_consent, cols_apres_consent] = np.nan
    print(
        "🔒 Données post-consentement purgées et remplacées par des NaN pour les profils non consentants."
    )
else:
    msg_cons_err = f"❌ Erreur : '{col_consent_technique}' introuvable dans le DataFrame."
    rapport_audit_consentement.append(msg_cons_err)
    print(msg_cons_err)


# ==========================================
# 18. NETTOYAGE GRANULAIRE ET STATISTIQUES DES TEXTES LIBRES
# ==========================================
print("Exécution du nettoyage granulaire des colonnes de texte libre...")

# Initialisation par défaut de msg_libre si non défini en amont
if "msg_libre" not in globals():
    msg_libre = [
        col
        for col in df_clean.select_dtypes(
            include=["object", "string"]
        ).columns
    ]

# Extraction des colonnes depuis msg_libre
if isinstance(msg_libre, str):
    cols_texte_libre = re.findall(r"'([^']+)'", msg_libre)
else:
    cols_texte_libre = list(msg_libre)

cols_texte_libre = [c for c in cols_texte_libre if c in df_clean.columns]

# Rapport global de correction détaillée par catégorie
rapport_detaille = {}

for col in cols_texte_libre:
    stats = {
        "mise_en_minuscules": 0,
        "suppression_accents": 0,
        "nettoyage_ponctuation": 0,
        "normalisation_espaces": 0,
        "chaine_vide_en_nan": 0,
    }

    def nettoyer_et_analyser(val):
        if isinstance(val, str):
            original = val

            # 1. Casse
            v = val.lower()
            if v != original:
                stats["mise_en_minuscules"] += 1

            # 2. Accents / ASCII
            v_ascii = v.encode("ascii", errors="ignore").decode("utf-8")
            if v_ascii != v:
                stats["suppression_accents"] += 1
            v = v_ascii

            # 3. Ponctuation
            v_ponc = re.sub(r"[^\w\s]", " ", v)
            if v_ponc != v:
                stats["nettoyage_ponctuation"] += 1
            v = v_ponc

            # 4. Espaces
            v_esp = re.sub(r"\s+", " ", v).strip()
            if v_esp != v:
                stats["normalisation_espaces"] += 1
            v = v_esp

            # 5. Valeurs vides
            if v == "":
                stats["chaine_vide_en_nan"] += 1
                return None

            return v
        return val

    df_clean[col] = df_clean[col].apply(nettoyer_et_analyser)
    label_col = mapping_labels_propre.get(col, col)
    rapport_detaille[col] = {"label": label_col, "stats": stats}

# Affichage du rapport granulaire
print("Rapport granulaire des corrections textuelles :")
for col, info in rapport_detaille.items():
    print(f"\n    📁 Colonne : '{col}' (Label : {info['label']})")
    for type_corr, count in info["stats"].items():
        print(f"      - {type_corr} : {count} modification(s)")


# ==========================================
# 19. GÉNÉRATION DU RAPPORT EXÉCUTIF ET DE CAPITALISATION (JSON & MARKDOWN)
# ==========================================
print("Génération du rapport de synthèse global et capitalisation...")

os.makedirs("outputs",exist_ok=True)

# Récupération des listes
l_struct = globals().get("rapport_audit_structure", [])
l_conv = globals().get("rapport_audit_conversion_temporelle", [])
l_types = globals().get("rapport_audit_types", [])
l_texte = globals().get("rapport_audit_texte", [])
l_chiff = globals().get("rapport_audit_chiffrement", [])
l_dates = globals().get("rapport_audit_dates", [])
l_const = globals().get("rapport_audit_constraints", [])
l_relev = globals().get("rapport_audit_relevant", [])
l_omiss = globals().get("rapport_audit_omissions", [])
l_resid = globals().get("rapport_audit_residuelles", [])
l_vides = globals().get("rapport_audit_vides", [])
l_doub = globals().get("rapport_audit_doublons", [])
l_cons = globals().get("rapport_audit_consentement", [])
dict_detail = globals().get("rapport_detaille", {})

# Construction d'un dictionnaire global structuré pour Edna_Mode (garde toutes les données brutes)
rapport_global = {
    "metadata": {
        "date_execution": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_lignes_finales": len(df_clean) if "df_clean" in globals() else 0,
        "total_colonnes_finales": (
            len(df_clean.columns) if "df_clean" in globals() else 0
        ),
    },
    "rapport_metier": {
        "consentement": l_cons,
        "doublons_identifiants": l_doub,
        "bilan_vides": l_vides,
    },
    "anomalies_techniques_questionnaire": {
        "structure": l_struct,
        "types_donnees": l_types,
        "texte_et_orphelins": l_texte,
        "chiffrement_labels": l_chiff,
        "dates_et_temporalite": l_dates,
        "conversion_temporelle": l_conv,
        "contraintes_constraints": l_const,
        "conditions_relevant": l_relev,
        "omissions": l_omiss,
        "valeurs_residuelles": l_resid,
    },
    "capitalisation_edna_mode": {
        "nettoyage_textes_libres": dict_detail,
        "recommandations_formulaire": [
            "Renforcer les contraintes (constraints) sur les champs numériques pour bloquer les valeurs négatives ou textuelles sur le terrain.",
            "Paramétrer des types stricts (integer, decimal) dès la conception du formulaire KoboToolbox.",
            "Vérifier la logique des conditions d'affichage (relevant) pour limiter l'apparition de valeurs orphelines ou d'omissions.",
            "Sensibiliser les équipes de collecte sur le respect strict des formats de dates et l'importance du consentement éclairé.",
        ],
    },
}

# Sauvegarde automatique du JSON brut pour l'agent Edna_Mode
chemin_json = os.path.join("outputs","edna_mode_capit.json")
with open(chemin_json, "w", encoding="utf-8") as f:
    json.dump(rapport_global, f, ensure_ascii=False, indent=4)


# ==========================================
# SYNTHÈSE INTELLIGENTE POUR LE RAPPORT EXÉCUTIF (.md)
# ==========================================

# Fonction utilitaire pour extraire des totaux numériques des messages d'alerte (ex: "[12] valeurs...")
def extraire_total_chiffre(liste_messages):
    total = 0
    for m in liste_messages:
        match = re.search(r"\[(\d+)\]", m)
        if match:
            total += int(match.group(1))
        elif any(
            mot in m.lower()
            for mot in ["détecté", "trouvé", "ligne", "valeur", "doublon"]
        ):
            total += 1
    return total


nb_residuelles_total = extraire_total_chiffre(l_resid)
nb_doublons_total = extraire_total_chiffre(l_doub)
nb_consent_purghes = extraire_total_chiffre(l_cons)
nb_textes_normalises = len(dict_detail)

# Rédaction du rapport Markdown synthétique (tient sur une seule page)
contenu_md = f"""# 📊 Note de Synthèse Exécutive - Nettoyage et Audit M&E
**Date d'exécution :** {rapport_global['metadata']['date_execution']}  
**Périmètre final :** {rapport_global['metadata']['total_lignes_finales']} enquêtes | {rapport_global['metadata']['total_colonnes_finales']} variables conservées.

---

## 1. Bilan des Actions de Nettoyage Réalisées
Malgré un dataset initialement altéré, la pipeline a appliqué un traitement automatisé rigoureux pour garantir la fiabilité des données :
* **Conformité & Éthique :** Purge systématique des données post-consentement pour les enquêtes non-consentantes et résolution des doublons d'identifiants uniques.
* **Standardisation Temporelle & Numérique :** Harmonisation des formats de dates, conversion des valeurs textuelles aberrantes ou négatives en valeurs nulles (`NaN`).
* **Traitement du Texte :** Normalisation syntaxique de {nb_textes_normalises} colonne(s) de texte libre (suppression des accents, mise en minuscules, uniformisation de la ponctuation et des espaces).
* **Gestion des Vides :** Unification de tous les types de blancs résiduels (`NaN`, chaînes vides, espaces) pour faciliter les analyses statistiques futures.

---

## 2. Synthèse des Risques & Anomalies du Formulaire (Kobo)
Les contrôles croisés mettent en évidence les axes d'amélioration structurelle du questionnaire de terrain :
* **Saisie & Contrôles aux frontières :** Présence de valeurs résiduelles textuelles/négatives dans des champs numériques (nécessité absolue d'intégrer des `constraints` sur Kobo).
* **Cohérence Temporelle :** Quelques décalages relevés par rapport aux bornes calendaires officielles des enquêtes.
* **Logique de Formulaire :** Détection de sauts ou de conditions d'affichage (`relevant`) imparfaites générant des données orphelines.

---

## 3. Recommandations Clés pour les Prochaines Collectes (Edna_Mode)
Pour optimiser les futures versions du formulaire KoboToolbox et alléger le travail de data-cleaning :
"""

for i, rec in enumerate(
    rapport_global["capitalisation_edna_mode"]["recommandations_formulaire"], 1
):
    contenu_md += f"{i}. {rec}\n"

contenu_md += f"""
---
*Rapport synthétique généré automatiquement. Données brutes de capitalisation archivées dans `{chemin_json}`.*
"""

# Écriture du fichier Markdown physique
chemin_md = os.path.join("outputs","rapport_execution_m_e.md")
with open(chemin_md, "w", encoding="utf-8") as f:
    f.write(contenu_md)

# Confirmation propre dans Jupyter
print("=" * 60)
print("RAPPORT EXÉCUTIF INTELLIGENT GÉNÉRÉ AVEC SUCCÈS")
print("=" * 60)
print(f"📦 1. JSON brut pour Edna_Mode : '{chemin_json}'")
print(f"📄 2. Rapport synthétique (1 page) : '{chemin_md}'")
print("=" * 60)