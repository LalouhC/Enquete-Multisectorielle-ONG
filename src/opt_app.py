"""Point d'entrée Streamlit de l'interface locale."""

import streamlit as st
import requests
import pandas as pd
import os
import hashlib

st.set_page_config(page_title="Interface M&E - Gestion des Enquêtes", page_icon="👥", layout="wide")

# CSS pour neutraliser le contour rouge natif de Streamlit sur les champs de texte/password
st.markdown("""
    <style>
    /* Cible le conteneur du champ de saisie et force une bordure neutre/bleue au focus */
    div[data-baseweb="input"] {
        border-color: #4b5563 !important;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 1px #3b82f6 !important;
    }
    /* Neutralise spécifiquement l'état d'erreur rouge natif de BaseWeb/Streamlit */
    div[data-baseweb="input"][data-error="true"], 
    div[data-baseweb="input"]:has(input:invalid) {
        border-color: #4b5563 !important;
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

st.title("👥 Interface de Gestion et de Suivi M&E")

# =========================================================
# 1. BARRE LATÉRALE & AUTHENTIFICATION BLOQUANTE
# =========================================================
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
st.sidebar.header("📂 Navigation")
menu = st.sidebar.radio(
    "Choisir une action :",
    (
        "📋 Lister les enquêtes (CSV propre)",
        "🔍 Consulter par Code Jeton",
        "➕ Importer / Ajouter des enquêtes",
        "✏️ Modifier une enquête (Non technique)",
        "🗑️ Supprimer un ménage",
    ),
)

# =========================================================
# 2. LISTER LES ENQUÊTES
# =========================================================
if menu == "📋 Lister les enquêtes (CSV propre)":
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
                        with st.expander(f"📁 Section : {table.upper()}", expanded=True):
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
# 4. IMPORTER / AJOUTER
# =========================================================
elif menu == "➕ Importer / Ajouter des enquêtes":
    st.header("➕ Ajouter ou réhabiliter une enquête")
    mode_ajout = st.radio(
        "Choisir le parcours :",
        ("Nouvel export Kobo", "Réhabiliter une enquête supprimée"),
        horizontal=True,
    )

    if mode_ajout == "Nouvel export Kobo":
        st.caption(
            "Importez l'export brut Kobo et le XLSForm exact correspondant. "
            "Le catalogue CSV est facultatif si le XLSForm contient une feuille choices."
        )
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