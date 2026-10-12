"""Point d'entrée FastAPI utilisé par Uvicorn."""

from datetime import datetime
import json
import os
import io
import sqlite3
import tempfile
import math
import re
import unicodedata
import logging
import uuid
from contextlib import closing, redirect_stdout
from datetime import datetime
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
import pandas as pd

from .partie1_pipeline_nettoyage import executer_nettoyage_global
from .partie2_ingest_db import ingest_data

app = FastAPI(title="API M&E - Gestion Locale", version="2.2")
DB_PATH = "outputs/enquete_ms.db"
RAPPORT_PATH = "outputs/rapport_execution_m_e.md"
CACHE_SUPPRESSIONS_DIR = Path(__file__).resolve().parent.parent / "cache" / "suppressions"
DOSSIER_IMPORTS_EN_ATTENTE = Path("outputs/imports_en_attente")
API_KEY_SECRETE = os.environ.get("M_E_API_KEY", "").strip()
LOGGER = logging.getLogger(__name__)

def verifier_acces_api(x_api_key: str = Header(...)):
    if not API_KEY_SECRETE:
        raise HTTPException(
            status_code=503,
            detail="La clé API n'est pas configurée sur le serveur.",
        )
    if x_api_key != API_KEY_SECRETE:
        raise HTTPException(status_code=403, detail="Accès refusé : Clé d'API invalide.")
    return x_api_key

def ecrire_rapport_execution(action: str, details: str):
    os.makedirs(os.path.dirname(RAPPORT_PATH), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ligne = f"\n- **[{timestamp}]** - Action: `{action}` - Détails: {details}"
    with open(RAPPORT_PATH, "a", encoding="utf-8") as f:
        f.write(ligne)

    with open(RAPPORT_PATH, "r+", encoding="utf-8") as f:
        lignes = f.readlines()
        if os.path.exists(DB_PATH):
            with closing(sqlite3.connect(DB_PATH)) as conn:
                compte = conn.execute(
                    """
                    SELECT
                        COUNT(*),
                        COALESCE(SUM(
                            CASE
                                WHEN volont IS NULL
                                  OR (
                                      lower(trim(CAST(volont AS TEXT))) NOT IN
                                          ('oui', 'yes', 'y', 'true', 'accepted', 'accepte', 'd''accord')
                                      AND CAST(volont AS REAL) != 1
                                  )
                                THEN 1
                                ELSE 0
                            END
                        ), 0)
                    FROM META_ENQUETE
                    """
                ).fetchone()
            marqueur_perimetre = re.compile(
                r"(?m)^([ \t]*\* \*\*Périmètre final validé :\*\* )"
                r"\d+( \(dont )\d+"
                r"( enquêtes non-consentantes filtrées conformément à l'éthique\)\.)"
            )
            texte_rapport = "".join(lignes)
            correspondances_perimetre = list(
                marqueur_perimetre.finditer(texte_rapport)
            )
            if correspondances_perimetre:
                correspondance = correspondances_perimetre[-1]
                nouveau_perimetre = (
                    f"{correspondance.group(1)}{compte[0]}"
                    f"{correspondance.group(2)}{compte[1]}"
                    f"{correspondance.group(3)}"
                )
                texte_rapport = (
                    texte_rapport[:correspondance.start()]
                    + nouveau_perimetre
                    + texte_rapport[correspondance.end():]
                )
                lignes = texte_rapport.splitlines(keepends=True)

        marqueur = "Dernière mise à jour (Synchronisation / API)"
        correspondances = [
            index for index, ligne in enumerate(lignes) if marqueur in ligne
        ]
        if correspondances:
            index = correspondances[-1]
            ligne = lignes[index]
            fin_ligne = "\r\n" if ligne.endswith("\r\n") else "\n" if ligne.endswith("\n") else ""
            fin_libelle = ligne.index(":**", ligne.index(marqueur)) + len(":**")
            lignes[index] = f"{ligne[:fin_libelle]} {timestamp}{fin_ligne}"
        else:
            lignes.append(
                f"\n- **Dernière mise à jour (Synchronisation / API) :** {timestamp}\n"
            )
        f.seek(0)
        f.writelines(lignes)
        f.truncate()


class ModificationPayload(BaseModel):
    colonne: str
    valeur: str | list[str]


class ArchiveRestaurationPayload(BaseModel):
    nom_fichier: str


class IngestionImportPreparePayload(BaseModel):
    import_id: str
    variables_par_table: dict[str, list[str]]


def charger_questionnaire():
    fichiers_questionnaire = list(
        (Path(__file__).resolve().parent.parent / "data").glob("*.xlsx")
    )
    if len(fichiers_questionnaire) != 1:
        raise RuntimeError(
            "Un seul fichier questionnaire Excel doit être présent dans le dossier data."
        )

    questionnaire = fichiers_questionnaire[0]
    survey = pd.read_excel(questionnaire, sheet_name="survey")
    choices = pd.read_excel(questionnaire, sheet_name="choices")
    survey.columns = survey.columns.astype(str).str.strip().str.lower()
    choices.columns = choices.columns.astype(str).str.strip().str.lower()
    if "code" not in choices.columns and "name" in choices.columns:
        choices = choices.rename(columns={"name": "code"})
    return survey, choices


COLONNES_SQL_GEREES = {
    "date_enquete", "heure_debut", "heure_fin", "enqueteur", "village",
    "code_jeton", "code_initial_renseigne", "presence_maison", "volont",
    "acpt_partage", "remarques_enquete", "duree_minutes", "repondant", "age",
    "sexe", "poss_carte", "typedepiece", "statmtr", "decision", "status",
    "herber", "environ", "date_deplacement", "date_retour", "loyer_depl",
    "loyer_depl_montant", "loyer_auto", "loyer_auto_montant", "h_0_5",
    "h_6_24", "h_25_59", "h_5_14", "h_15_17", "h_18_49", "h_50_59",
    "h_plus60", "f_0_5", "f_6_24", "f_25_59", "f_5_14", "f_15_17",
    "f_18_49", "f_50_59", "f_plus60", "fem_enc", "fem_all", "vis_ss",
    "hear_ss", "mob_ss", "cog_ss", "sc_ss", "com_ss", "observation_0",
    "adultincap", "hand", "malnut", "malnut_charge", "malnut_charge_non",
    "source_reve", "revenu", "dette", "montant_dette", "repas_a", "repas_e",
    "ressources", "repas_r", "suffisant", "repas_f", "manque", "repas_m",
    "nb_bidon", "nb_cass", "nb_bas", "nb_outil", "nb_couch", "nb_couv",
    "nb_habit_femme", "nb_habit_e", "nb_cale", "nb_jarre", "nb_seau",
    "nb_pot", "type_puisage", "capacite", "type_stockage", "capacites",
    "separer", "raison", "eau", "agro", "date_agro", "culture", "marai",
    "date_marai", "vivri", "date_vivri", "membre", "personne", "age_agro",
    "eau_point", "type_eau", "terre", "outims", "asso", "depl_bnf",
    "depl_dist", "diff_deplac", "type_diff",
}
TYPES_XLSFORM_NON_STOCKES = (
    "begin group", "end group", "begin_group", "end_group", "begin repeat",
    "end repeat", "note", "calculate", "hidden",
)


def destinations_sql_personnalisees() -> dict[str, str]:
    destinations = {}
    if not os.path.exists(DB_PATH):
        return destinations

    with closing(sqlite3.connect(DB_PATH)) as conn:
        for table in sorted(TABLES_DESTINATION_IMPORT):
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if not existe:
                continue
            for colonne in conn.execute(f'PRAGMA table_info("{table}")'):
                nom_colonne = colonne[1]
                if (
                    nom_colonne == "id_menage"
                    or nom_colonne in COLONNES_SQL_GEREES
                ):
                    continue
                if nom_colonne in destinations and destinations[nom_colonne] != table:
                    raise RuntimeError(
                        f"La variable SQL personnalisée '{nom_colonne}' existe "
                        "dans plusieurs tables."
                    )
                destinations[nom_colonne] = table
    return destinations


def lire_export_televerse(contenu: bytes, nom_fichier: str) -> pd.DataFrame:
    extension = Path(nom_fichier).suffix.lower()
    if extension == ".csv":
        return pd.read_csv(
            io.BytesIO(contenu), encoding="utf-8-sig", low_memory=False
        )
    if extension == ".xlsx":
        return pd.read_excel(io.BytesIO(contenu))
    raise HTTPException(
        status_code=400,
        detail="Format de fichier brut non pris en charge. Utilisez CSV ou XLSX.",
    )


def charger_questionnaire_televerse(
    contenu_xlsx: bytes, contenu_catalogue: bytes | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    classeur = pd.ExcelFile(io.BytesIO(contenu_xlsx))
    feuilles = {nom.strip().lower(): nom for nom in classeur.sheet_names}
    if "survey" not in feuilles:
        raise HTTPException(
            status_code=400,
            detail="Le XLSForm doit contenir une feuille nommée 'survey'.",
        )
    survey = pd.read_excel(classeur, sheet_name=feuilles["survey"])
    survey.columns = (
        survey.columns.astype(str).str.strip().str.lower().str.lstrip("\ufeff")
    )
    if not {"name", "type"}.issubset(survey.columns):
        raise HTTPException(
            status_code=400,
            detail="La feuille 'survey' doit contenir les colonnes 'name' et 'type'.",
        )

    if contenu_catalogue is not None:
        choices = pd.read_csv(
            io.BytesIO(contenu_catalogue), encoding="utf-8-sig"
        )
    elif "choices" in feuilles:
        choices = pd.read_excel(classeur, sheet_name=feuilles["choices"])
    else:
        raise HTTPException(
            status_code=400,
            detail="Le XLSForm n'a pas de feuille 'choices'. Fournissez le catalogue CSV.",
        )
    choices.columns = (
        choices.columns.astype(str).str.strip().str.lower().str.lstrip("\ufeff")
    )
    if "code" not in choices.columns and "name" in choices.columns:
        choices = choices.rename(columns={"name": "code"})
    label_column = next(
        (col for col in choices.columns if col == "label" or col.startswith("label::")),
        None,
    )
    if label_column and label_column != "label":
        choices = choices.rename(columns={label_column: "label"})
    if not {"list_name", "code", "label"}.issubset(choices.columns):
        raise HTTPException(
            status_code=400,
            detail=(
                "Le catalogue de choix doit contenir 'list_name', 'code' (ou 'name') "
                "et 'label' (ou 'label::langue')."
            ),
        )
    return survey, choices


def preparer_previsualisation_import(
    contenu_brut: bytes,
    nom_brut: str,
    contenu_xlsform: bytes,
    contenu_catalogue: bytes | None,
    nom_consentement: str,
    nom_identifiant: str,
    nom_date_enquete: str,
    date_debut: str,
    date_fin: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    df_brut = lire_export_televerse(contenu_brut, nom_brut)
    survey, choices = charger_questionnaire_televerse(
        contenu_xlsform, contenu_catalogue
    )
    if survey["name"].isna().all():
        raise HTTPException(
            status_code=400,
            detail="La feuille 'survey' ne contient aucun nom de variable exploitable.",
        )

    df_brut.columns = df_brut.columns.astype(str).str.strip().str.lower()
    if df_brut.columns.duplicated().any():
        colonnes_doubles = df_brut.columns[df_brut.columns.duplicated()].tolist()
        raise HTTPException(
            status_code=400,
            detail=f"Le fichier brut contient des en-têtes répétés : {colonnes_doubles}.",
        )

    noms_variables = (
        survey["name"].dropna().astype(str).str.strip().str.lower()
    )
    types_par_variable = (
        survey.assign(
            name=survey["name"].fillna("").astype(str).str.strip().str.lower(),
            type=survey["type"].fillna("").astype(str).str.strip().str.lower(),
        )
        .drop_duplicates(subset=["name"])
        .set_index("name")["type"]
        .to_dict()
    )
    variables_survey = {
        nom
        for nom in noms_variables[noms_variables.ne("")]
        if not types_par_variable.get(nom, "").startswith(TYPES_XLSFORM_NON_STOCKES)
    }
    colonnes_brutes = set(df_brut.columns)
    consentement = nom_consentement.strip().lower()
    identifiant = nom_identifiant.strip().lower()
    date_enquete = nom_date_enquete.strip().lower()
    if not consentement or not identifiant:
        raise HTTPException(
            status_code=400,
            detail="Indiquez le nom de la colonne d'identifiant et de consentement.",
        )
    if consentement == identifiant:
        raise HTTPException(
            status_code=400,
            detail="Les colonnes d'identifiant et de consentement doivent être différentes.",
        )
    for libelle, nom_colonne in (
        ("identifiant", identifiant),
        ("consentement", consentement),
    ):
        if nom_colonne not in variables_survey or nom_colonne not in colonnes_brutes:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La colonne de {libelle} '{nom_colonne}' doit figurer "
                    "dans le XLSForm et dans le fichier brut."
                ),
            )
    if date_enquete and (
        date_enquete not in variables_survey or date_enquete not in colonnes_brutes
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"La colonne de date '{date_enquete}' doit figurer dans le XLSForm "
                "et dans le fichier brut."
            ),
        )
    if bool(date_debut.strip()) != bool(date_fin.strip()):
        raise HTTPException(
            status_code=400,
            detail="Renseignez les deux bornes de dates ou laissez-les toutes les deux vides.",
        )
    if date_debut.strip():
        try:
            debut = datetime.strptime(date_debut.strip(), "%d-%m-%Y").date()
            fin = datetime.strptime(date_fin.strip(), "%d-%m-%Y").date()
        except ValueError as erreur:
            raise HTTPException(
                status_code=400,
                detail="Les dates doivent respecter le format JJ-MM-AAAA.",
            ) from erreur
        if fin < debut:
            raise HTTPException(
                status_code=400,
                detail="La date de fin doit être égale ou postérieure à la date de début.",
            )
        if not date_enquete:
            raise HTTPException(
                status_code=400,
                detail="Indiquez la colonne de date si vous renseignez des bornes.",
            )

    variables_questionnaire = {
        nom
        for nom in variables_survey
        if not types_par_variable.get(nom, "").startswith(TYPES_XLSFORM_NON_STOCKES)
    }
    destinations_personnalisees = destinations_sql_personnalisees()
    variables_sql_deja_classees = {
        nom: destinations_personnalisees[nom]
        for nom in variables_questionnaire
        if nom in destinations_personnalisees
    }
    variables_remplacees = {identifiant, consentement}
    if date_enquete:
        variables_remplacees.add(date_enquete)
    variables_sql_non_gerees = sorted(
        variables_questionnaire
        - COLONNES_SQL_GEREES
        - set(destinations_personnalisees)
        - variables_remplacees
    )
    variables_absentes = sorted(variables_survey - colonnes_brutes)
    colonnes_inconnues = sorted(colonnes_brutes - variables_survey)
    textes_libres = sum(
        1
        for nom, type_question in types_par_variable.items()
        if nom in variables_survey and type_question == "text"
    )
    avertissements = []
    if variables_absentes:
        avertissements.append(
            "Certaines questions du XLSForm sont absentes du fichier brut. "
            "Elles peuvent être conditionnelles, mais vérifiez qu'il s'agit du bon export."
        )
    if colonnes_inconnues:
        avertissements.append(
            "Des colonnes du fichier brut ne figurent pas dans le XLSForm; "
            "le nettoyage peut les ignorer."
        )
    if textes_libres:
        avertissements.append(
            "Le fichier contient des réponses libres. Le nettoyage harmonise leur forme, "
            "mais ne détecte pas nécessairement les noms ou autres informations "
            "personnelles et ne garantit pas leur anonymisation."
        )
    if variables_sql_non_gerees:
        avertissements.append(
            "Certaines questions ne correspondent pas encore aux colonnes de la base. "
            "Elles pourront être classées dans une rubrique SQL après le nettoyage."
        )
    avertissements.append(
        "Vérifiez que l'export et le XLSForm correspondent à la même enquête et à la "
        "même version du formulaire. Après validation, le nettoyage et le chargement "
        "SQL modifieront les fichiers locaux de outputs/."
    )
    bilan = {
        "lignes_brutes": len(df_brut),
        "colonnes_brutes": len(colonnes_brutes),
        "questions_xlsform": len(variables_survey),
        "questions_textuelles_libres": textes_libres,
        "variables_absentes": variables_absentes,
        "colonnes_inconnues": colonnes_inconnues,
        "variables_sql_non_gerees": variables_sql_non_gerees,
        "variables_sql_deja_classees": variables_sql_deja_classees,
        "avertissements": avertissements,
        "import_sql_possible": not variables_sql_non_gerees,
    }
    return df_brut, survey, choices, bilan


def normaliser_consentement_import(valeur):
    if pd.isna(valeur):
        return valeur

    texte = unicodedata.normalize("NFKD", str(valeur).strip().lower())
    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(caractere)
    )
    if texte in {"oui", "yes", "y", "true", "accepted", "accepte", "d'accord"}:
        return "oui"
    if texte in {"non", "no", "n", "false", "refused", "refuse"}:
        return "non"

    valeur_numerique = pd.to_numeric(texte, errors="coerce")
    if pd.notna(valeur_numerique) and valeur_numerique == 1:
        return "oui"
    if pd.notna(valeur_numerique) and valeur_numerique == 0:
        return "non"
    return valeur


def charger_metadonnees_modification():
    survey, choices = charger_questionnaire()
    choix_par_liste = {}
    for _, row in choices.iterrows():
        nom_liste = str(row.get("list_name", "")).strip().lower()
        valeur = row.get("label")
        if (
            not nom_liste
            or nom_liste.lower() == "nan"
            or pd.isna(valeur)
            or str(valeur).strip() == ""
        ):
            continue
        choix_par_liste.setdefault(nom_liste, []).append(str(valeur).strip())

    metadonnees = {}
    for _, row in survey.iterrows():
        nom = str(row.get("name", "")).strip().lower()
        type_question = str(row.get("type", "text")).strip().lower()
        if not nom or nom.lower() == "nan" or "group" in type_question:
            continue

        morceaux_type = type_question.split(maxsplit=1)
        liste_choix = (
            choix_par_liste.get(morceaux_type[1], [])
            if morceaux_type[0] in {"select_one", "select_multiple"}
            and len(morceaux_type) == 2
            else []
        )
        metadonnees[nom] = {
            "type": type_question,
            "choices": list(dict.fromkeys(liste_choix)),
        }
    return metadonnees


def trier_menages_par_identifiant(df: pd.DataFrame) -> pd.DataFrame:
    if "id_menage" not in df.columns:
        return df

    resultat = df.copy()
    numeros = resultat["id_menage"].astype("string").str.extract(
        r"(?i)^MENAGE_(\d+)$", expand=False
    )
    resultat["_ordre_menage"] = pd.to_numeric(numeros, errors="coerce")
    resultat["_ordre_initial"] = range(len(resultat))
    resultat.sort_values(
        ["_ordre_menage", "_ordre_initial"],
        kind="stable",
        na_position="last",
        inplace=True,
    )
    resultat.drop(columns=["_ordre_menage", "_ordre_initial"], inplace=True)
    return resultat


def synchroniser_csv_propre(df_nouvelles_lignes: pd.DataFrame):
    csv_path = Path("outputs/donnees_nettoyees.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    nouvelles = df_nouvelles_lignes.copy()
    nouvelles["id_menage"] = nouvelles["id_menage"].astype("string")
    if csv_path.exists():
        existantes = pd.read_csv(
            csv_path,
            dtype={"id_menage": "string", "code_jeton": "string"},
        )
        if "id_menage" in existantes.columns:
            existantes = existantes[
                ~existantes["id_menage"].isin(nouvelles["id_menage"])
            ]
        colonnes = list(dict.fromkeys([*existantes.columns, *nouvelles.columns]))
        df_csv = pd.concat(
            [
                existantes.reindex(columns=colonnes),
                nouvelles.reindex(columns=colonnes),
            ],
            ignore_index=True,
        )
    else:
        df_csv = nouvelles

    df_csv = trier_menages_par_identifiant(df_csv)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix="donnees_nettoyees_",
        dir=csv_path.parent,
        delete=False,
    ) as fichier_temp:
        chemin_temp = fichier_temp.name
        df_csv.to_csv(fichier_temp, index=False)
    try:
        os.replace(chemin_temp, csv_path)
    finally:
        if os.path.exists(chemin_temp):
            os.remove(chemin_temp)


def prochains_identifiants_menage(nombre: int) -> list[str]:
    ids_existants = set()
    if os.path.exists(DB_PATH):
        with closing(sqlite3.connect(DB_PATH)) as conn:
            table_meta = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'META_ENQUETE'"
            ).fetchone()
            if table_meta:
                ids_existants.update(
                    row[0]
                    for row in conn.execute(
                        "SELECT id_menage FROM META_ENQUETE "
                        "WHERE id_menage IS NOT NULL"
                    )
                )

    csv_path = Path("outputs/donnees_nettoyees.csv")
    if csv_path.exists():
        df_csv = pd.read_csv(csv_path, usecols=["id_menage"], dtype=str)
        ids_existants.update(df_csv["id_menage"].dropna().tolist())

    if CACHE_SUPPRESSIONS_DIR.exists():
        for archive in CACHE_SUPPRESSIONS_DIR.glob("menage_*.csv"):
            correspondance = re.search(r"(?i)MENAGE_(\d+)", archive.stem)
            if correspondance:
                ids_existants.add(f"MENAGE_{correspondance.group(1)}")

    indices = [
        int(correspondance.group(1))
        for identifiant in ids_existants
        if (
            correspondance := re.fullmatch(
                r"(?i)MENAGE_(\d+)", str(identifiant)
            )
        )
    ]
    prochain = max(indices, default=0) + 1
    return [f"MENAGE_{indice}" for indice in range(prochain, prochain + nombre)]


def charger_labels_depuis_excel():
    mapping = {}
    chemin_ref = "data/Questionnaire Vulnérabilités Fictif.xlsx"
    if os.path.exists(chemin_ref):
        try:
            xls = pd.ExcelFile(chemin_ref)
            for sheet_name in xls.sheet_names:
                df_ref = pd.read_excel(xls, sheet_name=sheet_name)
                df_ref.columns = [str(c).strip().lower() for c in df_ref.columns]
                if "name" in df_ref.columns and "label" in df_ref.columns:
                    for _, row in df_ref.iterrows():
                        code = str(row["name"]).strip()
                        label = str(row["label"]).strip()
                        if code and label and code.lower() != "nan" and label.lower() != "nan":
                            mapping[code] = label
        except Exception as e:
            print(f"Erreur lecture labels API : {e}")
    return mapping

@app.get("/enquetes", dependencies=[Depends(verifier_acces_api)])
def lister_enquetes(limite: int = 50):
    try:
        csv_path = "outputs/donnees_nettoyees.csv"
        
        # Si le fichier CSV propre existe, on le lit en priorité
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
        else:
            # Fallback sur la base de données SQLite si le CSV n'existe pas encore
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query(
                """
                SELECT * FROM META_ENQUETE
                ORDER BY
                    CASE
                        WHEN id_menage GLOB 'MENAGE_[0-9]*'
                        THEN CAST(substr(id_menage, 8) AS INTEGER)
                        ELSE NULL
                    END,
                    id_menage
                """,
                conn,
            )
            conn.close()
        df = trier_menages_par_identifiant(df)
            
        # Application de la limite demandée
        df = df.head(limite)
        df = df.astype(object).where(pd.notnull(df), None)
        
        return {
            "statut": "succes",
            "source": "donnees_nettoyees.csv" if os.path.exists(csv_path) else "SQLite (META_ENQUETE)",
            "total_retourne": len(df),
            "donnees": df.to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/enquetes/supprimer/{identifiant}", dependencies=[Depends(verifier_acces_api)])
def supprimer_enquete(identifiant: str):
    csv_path = "outputs/donnees_nettoyees.csv"
    csv_temp_path = None
    archive_temp_path = None
    archive_path = None
    conn = None
    transaction_committed = False
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("BEGIN IMMEDIATE")
        enquetes = conn.execute(
            """
            SELECT id_menage
            FROM META_ENQUETE
            WHERE id_menage = ? OR CAST(code_jeton AS TEXT) = ?
            """,
            (identifiant, identifiant),
        ).fetchall()
        jeton_numerique = pd.to_numeric(identifiant, errors="coerce")
        if pd.notna(jeton_numerique) and float(jeton_numerique).is_integer():
            supplementaires = conn.execute(
                """
                SELECT id_menage
                FROM META_ENQUETE
                WHERE CAST(code_jeton AS INTEGER) = ?
                  AND id_menage != ?
                """,
                (int(jeton_numerique), identifiant),
            ).fetchall()
            ids_deja_trouves = {ligne[0] for ligne in enquetes}
            enquetes.extend(
                ligne for ligne in supplementaires if ligne[0] not in ids_deja_trouves
            )

        if not enquetes:
            raise HTTPException(status_code=404, detail="Ménage introuvable.")
        if len(enquetes) > 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Ce code jeton correspond à plusieurs ménages. "
                        "Supprimez le ménage par son identifiant technique."
                    ),
                    "identifiants_menage": [ligne[0] for ligne in enquetes],
                },
            )

        id_menage = enquetes[0][0]
        if os.path.exists(csv_path):
            csv_nettoye = pd.read_csv(
                csv_path,
                dtype={"id_menage": "string", "code_jeton": "string"},
            )
            masque_cible = pd.Series(False, index=csv_nettoye.index)
            if "id_menage" in csv_nettoye.columns:
                masque_cible |= csv_nettoye["id_menage"].eq(id_menage).fillna(False)
            if "code_jeton" in csv_nettoye.columns:
                jetons_csv = csv_nettoye["code_jeton"].str.strip()
                masque_jeton = jetons_csv.eq(identifiant).fillna(False)
                jeton_numerique = pd.to_numeric(identifiant, errors="coerce")
                if pd.notna(jeton_numerique):
                    masque_jeton |= pd.to_numeric(
                        jetons_csv, errors="coerce"
                    ).eq(jeton_numerique).fillna(False)
                masque_cible |= masque_jeton
            csv_nettoye = csv_nettoye.loc[~masque_cible]

            csv_dir = os.path.dirname(csv_path) or "."
            os.makedirs(csv_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix=".csv",
                prefix="donnees_nettoyees_",
                dir=csv_dir,
                delete=False,
            ) as fichier_temp:
                csv_temp_path = fichier_temp.name
                csv_nettoye.to_csv(fichier_temp, index=False)

        tables_liees = (
            "MENAGE",
            "STATUT_MENAGE",
            "COMPOSITION_MENAGE",
            "VULNERABILITE_SANTE",
            "ECONOMIE_REVENU",
            "SECURITE_ALIMENTAIRE",
            "BIENS_AME",
            "WASH_EAU",
            "AGRICULTURE",
            "PROTECTION",
        )
        tables_existantes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        tables_a_archiver = ("META_ENQUETE",) + tuple(
            table for table in tables_liees if table in tables_existantes
        )
        ligne_archive = {}
        for table in tables_a_archiver:
            colonnes = {
                row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
            }
            if "id_menage" not in colonnes:
                continue
            resultat = conn.execute(
                f'SELECT * FROM "{table}" WHERE "id_menage" = ?',
                (id_menage,),
            )
            ligne = resultat.fetchone()
            if ligne is None:
                continue
            for colonne, valeur in zip(
                [description[0] for description in resultat.description],
                ligne,
            ):
                if colonne == "id_menage":
                    ligne_archive.setdefault(colonne, valeur)
                elif colonne not in ligne_archive:
                    ligne_archive[colonne] = valeur
                elif ligne_archive[colonne] != valeur:
                    ligne_archive[f"{table}__{colonne}"] = valeur

        archive_dir = CACHE_SUPPRESSIONS_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        id_fichier = re.sub(r"[^A-Za-z0-9_-]+", "_", str(id_menage)).strip("_")
        id_fichier = re.sub(r"(?i)^MENAGE_", "", id_fichier)
        nom_archive = f"menage_{id_fichier}.csv"
        suffixe = 2
        while (archive_dir / nom_archive).exists():
            nom_archive = f"menage_{id_fichier}_{suffixe}.csv"
            suffixe += 1
        archive_path = archive_dir / nom_archive
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            suffix=".csv",
            prefix="archive_",
            dir=archive_dir,
            delete=False,
        ) as fichier_archive:
            archive_temp_path = fichier_archive.name
            pd.DataFrame([ligne_archive]).to_csv(fichier_archive, index=False)

        os.replace(archive_temp_path, archive_path)
        archive_temp_path = None

        for table in tables_liees:
            if table in tables_existantes:
                conn.execute(f'DELETE FROM "{table}" WHERE id_menage = ?', (id_menage,))
        conn.execute("DELETE FROM META_ENQUETE WHERE id_menage = ?", (id_menage,))
        conn.commit()
        transaction_committed = True

        if csv_temp_path:
            os.replace(csv_temp_path, csv_path)
            csv_temp_path = None

        total_menages_restants = conn.execute(
            "SELECT COUNT(*) FROM META_ENQUETE"
        ).fetchone()[0]
        ecrire_rapport_execution(
            "SUPPRESSION_DONNEES",
            f"Ménage {id_menage} supprimé de META_ENQUETE et des tables liées. "
            f"Archive CSV : {archive_path.relative_to(archive_dir.parent.parent)}.",
        )
        return {
            "statut": "succes",
            "message": f"Le ménage '{identifiant}' et ses données liées ont été supprimés.",
            "id_menage": id_menage,
            "archive_csv": str(archive_path.relative_to(archive_dir.parent.parent)),
            "total_menages_restants": total_menages_restants,
        }
    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise
    except Exception as e:
        if conn is not None:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            conn.close()
        if csv_temp_path and os.path.exists(csv_temp_path):
            os.remove(csv_temp_path)
        if archive_temp_path and os.path.exists(archive_temp_path):
            os.remove(archive_temp_path)
        if (
            archive_path
            and archive_path.exists()
            and not transaction_committed
        ):
            archive_path.unlink()

@app.get("/menages/jeton/{code_jeton}/profil", dependencies=[Depends(verifier_acces_api)])
def obtenir_profil_par_jeton(code_jeton: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM META_ENQUETE WHERE code_jeton = ? OR id_menage = ?", (code_jeton, code_jeton))
        meta = cursor.fetchone()
        if not meta:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Ménage introuvable pour '{code_jeton}'.")

        record_id = meta["id_menage"]
        profil = {"meta_enquete": dict(meta)}

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence';")
        for (table,) in cursor.fetchall():
            if table.upper() == "META_ENQUETE":
                continue
            cursor.execute(f"PRAGMA table_info({table});")
            if "id_menage" in [col[1] for col in cursor.fetchall()]:
                cursor.execute(f"SELECT * FROM {table} WHERE id_menage = ?", (record_id,))
                rows = cursor.fetchall()
                if rows:
                    profil[table.lower()] = [dict(r) for r in rows] if len(rows) > 1 else dict(rows[0])

        conn.close()
        labels_dict = charger_labels_depuis_excel()
        return {"statut": "succes", "code_jeton": code_jeton, "id_menage": record_id, "profil_complet": profil, "labels":labels_dict}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/enquetes/previsualiser-nettoyage",
    dependencies=[Depends(verifier_acces_api)],
)
def previsualiser_nettoyage_streamlit(
    file: UploadFile = File(...),
    questionnaire: UploadFile = File(...),
    catalogue: UploadFile = File(None),
    colonne_identifiant: str = Form(...),
    colonne_consentement: str = Form(...),
    colonne_date: str = Form(""),
    date_debut: str = Form(""),
    date_fin: str = Form(""),
):
    nom_fichier = file.filename or "export.csv"
    _, _, _, bilan = preparer_previsualisation_import(
        file.file.read(),
        nom_fichier,
        questionnaire.file.read(),
        catalogue.file.read() if catalogue is not None else None,
        colonne_consentement,
        colonne_identifiant,
        colonne_date,
        date_debut,
        date_fin,
    )
    return bilan


TABLES_DESTINATION_IMPORT = {
    "MENAGE",
    "STATUT_MENAGE",
    "COMPOSITION_MENAGE",
    "VULNERABILITE_SANTE",
    "ECONOMIE_REVENU",
    "SECURITE_ALIMENTAIRE",
    "BIENS_AME",
    "WASH_EAU",
    "AGRICULTURE",
    "PROTECTION",
}


@app.post(
    "/enquetes/nettoyer-pour-import",
    dependencies=[Depends(verifier_acces_api)],
)
def nettoyer_pour_import_streamlit(
    file: UploadFile = File(...),
    questionnaire: UploadFile = File(...),
    catalogue: UploadFile = File(None),
    colonne_identifiant: str = Form(...),
    colonne_consentement: str = Form(...),
    colonne_date: str = Form(""),
    date_debut: str = Form(""),
    date_fin: str = Form(""),
):
    nom_fichier = Path(file.filename or "export.csv").name
    df_brut, survey, choices, bilan = preparer_previsualisation_import(
        file.file.read(),
        nom_fichier,
        questionnaire.file.read(),
        catalogue.file.read() if catalogue is not None else None,
        colonne_consentement,
        colonne_identifiant,
        colonne_date,
        date_debut,
        date_fin,
    )
    identifiant = colonne_identifiant.strip().lower()
    consentement = colonne_consentement.strip().lower()
    date_enquete = colonne_date.strip().lower()
    df_brut[consentement] = df_brut[consentement].map(
        normaliser_consentement_import
    )

    jetons_reserves = set()
    if os.path.exists(DB_PATH):
        with closing(sqlite3.connect(DB_PATH)) as conn:
            table_meta = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'META_ENQUETE'"
            ).fetchone()
            if table_meta:
                jetons_reserves = {
                    str(ligne[0]).strip()
                    for ligne in conn.execute(
                        "SELECT code_jeton FROM META_ENQUETE "
                        "WHERE code_jeton IS NOT NULL"
                    )
                }

    dossier_sortie = Path("outputs")
    DOSSIER_IMPORTS_EN_ATTENTE.mkdir(parents=True, exist_ok=True)
    identifiant_import = str(uuid.uuid4())
    chemin_csv = DOSSIER_IMPORTS_EN_ATTENTE / (
        f"{identifiant_import}_donnees_nettoyees.csv"
    )
    chemin_metadonnees = DOSSIER_IMPORTS_EN_ATTENTE / (
        f"{identifiant_import}.json"
    )
    sortie_console = dossier_sortie / "rapport_nettoyage_console.txt"
    journal_console = io.StringIO()
    try:
        with redirect_stdout(journal_console):
            df_clean = executer_nettoyage_global(
                df_brut,
                survey,
                choices,
                date_debut_saisie=date_debut.strip(),
                date_fin_saisie=date_fin.strip(),
                col_consent_technique=consentement,
                col_id_technique=identifiant,
                col_date_enquete=date_enquete or None,
                generer_rapport=True,
                codes_jetons_reserves=jetons_reserves,
            )
            if identifiant != "code_jeton":
                df_clean["code_jeton"] = df_clean[identifiant]
            if consentement != "volont":
                df_clean["volont"] = df_clean[consentement]
            if date_enquete and date_enquete != "date_enquete":
                df_clean["date_enquete"] = df_clean[date_enquete].map(
                    lambda valeur: (
                        valeur.isoformat()
                        if pd.notna(valeur) and hasattr(valeur, "isoformat")
                        else valeur
                    )
                )
            for colonne in df_clean.select_dtypes(
                include=["datetime", "datetimetz"]
            ).columns:
                df_clean[colonne] = df_clean[colonne].map(
                    lambda valeur: (
                        valeur.isoformat() if pd.notna(valeur) else None
                    )
                )
            if df_clean.empty:
                raise HTTPException(
                    status_code=400,
                    detail="Aucune ligne ne reste après le nettoyage.",
                )
            df_clean.to_csv(chemin_csv, index=False)

        types_par_variable = (
            survey.assign(
                name=survey["name"].fillna("").astype(str).str.strip().str.lower(),
                type=survey["type"].fillna("").astype(str).str.strip().str.lower(),
            )
            .drop_duplicates(subset=["name"])
            .set_index("name")["type"]
            .to_dict()
        )
        metadonnees = {
            "nom_fichier": nom_fichier,
            "lignes_nettoyees": len(df_clean),
            "variables_sql_non_gerees": bilan["variables_sql_non_gerees"],
            "variables_sql_deja_classees": bilan[
                "variables_sql_deja_classees"
            ],
            "types_par_variable": types_par_variable,
        }
        chemin_metadonnees.write_text(
            json.dumps(metadonnees, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except HTTPException:
        raise
    except Exception as erreur:
        LOGGER.exception("Échec du nettoyage pour le fichier %s", nom_fichier)
        raise HTTPException(
            status_code=500,
            detail=(
                "Le nettoyage a échoué. Aucun CSV propre n'a été préparé; "
                "contactez le support avec l'heure de l'erreur."
            ),
        ) from erreur
    finally:
        sortie_console.write_text(journal_console.getvalue(), encoding="utf-8")

    return {
        "statut": "nettoyage_termine",
        "import_id": identifiant_import,
        "message": (
            "Le nettoyage est terminé. Le rangement SQL des questions restantes "
            "peut maintenant être configuré."
        ),
        "lignes_nettoyees": len(df_clean),
        "variables_sql_a_classer": bilan["variables_sql_non_gerees"],
        "fichier_nettoye": str(chemin_csv),
        "fichiers_generes": [
            str(chemin_csv),
            str(dossier_sortie / "rapport_execution_m_e.md"),
            str(dossier_sortie / "edna_mode_capit.json"),
            str(sortie_console),
        ],
        "rapport_console": journal_console.getvalue()[-30000:],
        "rapport_console_tronque": len(journal_console.getvalue()) > 30000,
        "rapport_execution": (
            (dossier_sortie / "rapport_execution_m_e.md").read_text(
                encoding="utf-8"
            )
            if (dossier_sortie / "rapport_execution_m_e.md").is_file()
            else ""
        ),
        "avertissements": bilan["avertissements"],
    }


@app.post(
    "/enquetes/ingrer-import-prepare",
    dependencies=[Depends(verifier_acces_api)],
)
def ingerer_import_prepare(payload: IngestionImportPreparePayload):
    try:
        import_id = str(uuid.UUID(payload.import_id))
    except ValueError as erreur:
        raise HTTPException(
            status_code=400, detail="Identifiant de nettoyage invalide."
        ) from erreur

    chemin_csv = DOSSIER_IMPORTS_EN_ATTENTE / (
        f"{import_id}_donnees_nettoyees.csv"
    )
    chemin_metadonnees = DOSSIER_IMPORTS_EN_ATTENTE / f"{import_id}.json"
    if not chemin_csv.is_file() or not chemin_metadonnees.is_file():
        raise HTTPException(
            status_code=404,
            detail="Le fichier nettoyé n'est plus disponible. Relancez le nettoyage.",
        )

    metadonnees = json.loads(chemin_metadonnees.read_text(encoding="utf-8"))
    variables_a_classer = set(metadonnees["variables_sql_non_gerees"])
    affectations = {
        variable: table
        for table, variables in payload.variables_par_table.items()
        for variable in variables
    }
    if (
        set(affectations) != variables_a_classer
        or len(affectations)
        != sum(len(variables) for variables in payload.variables_par_table.values())
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Chaque nouvelle question doit être affectée à une seule boîte SQL."
            ),
        )
    if any(
        table not in TABLES_DESTINATION_IMPORT
        for table in payload.variables_par_table
    ):
        raise HTTPException(
            status_code=422,
            detail="Une boîte SQL sélectionnée n'est pas prise en charge.",
        )
    variables_invalides = sorted(
        variable
        for variable in variables_a_classer
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", variable)
    )
    if variables_invalides:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "Certaines variables XLSForm ne sont pas des noms de colonnes "
                    "SQL valides. Demandez au support de les renommer dans le formulaire."
                ),
                "variables": variables_invalides,
            },
        )

    nom_fichier = metadonnees["nom_fichier"]
    try:
        df_clean = pd.read_csv(
            chemin_csv,
            encoding="utf-8-sig",
            low_memory=False,
            dtype={"code_jeton": "string", "id_menage": "string"},
        )
        df_clean["id_menage"] = prochains_identifiants_menage(len(df_clean))
        jetons = (
            df_clean["code_jeton"]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
            if "code_jeton" in df_clean.columns
            else []
        )
        if jetons and os.path.exists(DB_PATH):
            with closing(sqlite3.connect(DB_PATH)) as conn:
                table_meta = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'META_ENQUETE'"
                ).fetchone()
                if table_meta:
                    placeholders = ",".join("?" for _ in jetons)
                    deja_presents = conn.execute(
                        "SELECT code_jeton FROM META_ENQUETE "
                        f"WHERE CAST(code_jeton AS TEXT) IN ({placeholders})",
                        jetons,
                    ).fetchall()
                    if deja_presents:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Un ou plusieurs identifiants existent déjà dans "
                                "la base. Vérifiez le fichier avant de recommencer."
                            ),
                        )

        variables_par_table = {
            table: [
                variable
                for variable, destination in metadonnees[
                    "variables_sql_deja_classees"
                ].items()
                if destination == table
            ]
            for table in TABLES_DESTINATION_IMPORT
        }
        for table, variables in payload.variables_par_table.items():
            variables_par_table.setdefault(table, []).extend(variables)
        types_par_variable = metadonnees["types_par_variable"]
        bilan_sql = ingest_data(
            df_clean,
            str(Path(DB_PATH).resolve()),
            variables_par_table=variables_par_table,
            types_par_variable=types_par_variable,
        )
        synchroniser_csv_propre(df_clean)
        ecrire_rapport_execution(
            "NETTOYAGE_ET_INGESTION_STREAMLIT",
            f"Fichier {nom_fichier} nettoyé puis chargé dans SQLite "
            f"({len(df_clean)} lignes).",
        )
    except HTTPException:
        raise
    except Exception as erreur:
        LOGGER.exception(
            "Échec de l'ingestion SQL pour le fichier nettoyé %s", nom_fichier
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Le chargement SQL a échoué. Le fichier propre préparé reste "
                "disponible dans outputs/imports_en_attente/; contactez le support "
                "avec l'heure de l'erreur."
            ),
        ) from erreur

    chemin_csv.unlink(missing_ok=True)
    chemin_metadonnees.unlink(missing_ok=True)
    chemin_rapport = Path(RAPPORT_PATH)
    sortie_console = Path("outputs/rapport_nettoyage_console.txt")
    return {
        "statut": "succes",
        "message": (
            f"'{nom_fichier}' a été nettoyé puis chargé automatiquement dans SQL."
        ),
        "lignes_traitees": len(df_clean),
        "lignes_consentantes": bilan_sql["lignes_consentantes"],
        "lignes_par_table": bilan_sql["lignes_par_table"],
        "fichiers_generes": [
            "outputs/donnees_nettoyees.csv",
            str(chemin_rapport),
            "outputs/edna_mode_capit.json",
            str(sortie_console),
        ],
        "rapport_execution": (
            chemin_rapport.read_text(encoding="utf-8")
            if chemin_rapport.is_file()
            else ""
        ),
        "rapport_console": (
            sortie_console.read_text(encoding="utf-8")
            if sortie_console.is_file()
            else ""
        )[-30000:],
        "rapport_console_tronque": (
            sortie_console.stat().st_size > 30000
            if sortie_console.is_file()
            else False
        ),
        "lignes_par_table": bilan_sql["lignes_par_table"],
    }


@app.post(
    "/enquetes/nettoyer-et-integrer",
    dependencies=[Depends(verifier_acces_api)],
)
def nettoyer_et_integrer_fichier_streamlit(
    file: UploadFile = File(...),
    questionnaire: UploadFile = File(...),
    catalogue: UploadFile = File(None),
    colonne_identifiant: str = Form(...),
    colonne_consentement: str = Form(...),
    colonne_date: str = Form(""),
    date_debut: str = Form(""),
    date_fin: str = Form(""),
):
    nom_fichier = Path(file.filename or "export.csv").name
    df_brut, survey, choices, bilan = preparer_previsualisation_import(
        file.file.read(),
        nom_fichier,
        questionnaire.file.read(),
        catalogue.file.read() if catalogue is not None else None,
        colonne_consentement,
        colonne_identifiant,
        colonne_date,
        date_debut,
        date_fin,
    )
    if not bilan["import_sql_possible"]:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "L'import est arrêté : des questions ne sont pas prévues dans "
                    "la base SQL actuelle."
                ),
                "variables_non_gerees": bilan["variables_sql_non_gerees"],
            },
        )

    identifiant = colonne_identifiant.strip().lower()
    consentement = colonne_consentement.strip().lower()
    date_enquete = colonne_date.strip().lower()
    df_brut[consentement] = df_brut[consentement].map(
        normaliser_consentement_import
    )

    jetons_reserves = set()
    if os.path.exists(DB_PATH):
        with closing(sqlite3.connect(DB_PATH)) as conn:
            table_meta = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                "AND name = 'META_ENQUETE'"
            ).fetchone()
            if table_meta:
                jetons_reserves = {
                    str(ligne[0]).strip()
                    for ligne in conn.execute(
                        "SELECT code_jeton FROM META_ENQUETE "
                        "WHERE code_jeton IS NOT NULL"
                    )
                }

    dossier_sortie = Path("outputs")
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    chemin_csv = dossier_sortie / "donnees_nettoyees.csv"
    sortie_console = dossier_sortie / "rapport_nettoyage_console.txt"
    journal_console = io.StringIO()
    try:
        with redirect_stdout(journal_console):
            df_clean = executer_nettoyage_global(
                df_brut,
                survey,
                choices,
                date_debut_saisie=date_debut.strip(),
                date_fin_saisie=date_fin.strip(),
                col_consent_technique=consentement,
                col_id_technique=identifiant,
                col_date_enquete=date_enquete or None,
                generer_rapport=True,
                codes_jetons_reserves=jetons_reserves,
            )
            if identifiant != "code_jeton":
                df_clean["code_jeton"] = df_clean[identifiant]
            if consentement != "volont":
                df_clean["volont"] = df_clean[consentement]
            if date_enquete and date_enquete != "date_enquete":
                df_clean["date_enquete"] = df_clean[date_enquete].map(
                    lambda valeur: (
                        valeur.isoformat()
                        if pd.notna(valeur) and hasattr(valeur, "isoformat")
                        else valeur
                    )
                )
            for colonne in df_clean.select_dtypes(
                include=["datetime", "datetimetz"]
            ).columns:
                df_clean[colonne] = df_clean[colonne].map(
                    lambda valeur: (
                        valeur.isoformat() if pd.notna(valeur) else None
                    )
                )
            if df_clean.empty:
                raise HTTPException(
                    status_code=400,
                    detail="Aucune ligne ne reste après le nettoyage.",
                )

            df_clean["id_menage"] = prochains_identifiants_menage(len(df_clean))
            jetons = (
                df_clean["code_jeton"]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
            if jetons and os.path.exists(DB_PATH):
                with closing(sqlite3.connect(DB_PATH)) as conn:
                    table_meta = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                        "AND name = 'META_ENQUETE'"
                    ).fetchone()
                    if table_meta:
                        placeholders = ",".join("?" for _ in jetons)
                        deja_presents = conn.execute(
                            "SELECT code_jeton FROM META_ENQUETE "
                            f"WHERE CAST(code_jeton AS TEXT) IN ({placeholders})",
                            jetons,
                        ).fetchall()
                        if deja_presents:
                            raise HTTPException(
                                status_code=409,
                                detail=(
                                    "Un ou plusieurs identifiants existent déjà "
                                    "dans la base. Vérifiez le fichier avant de recommencer."
                                ),
                            )

            bilan_sql = ingest_data(df_clean, str(Path(DB_PATH).resolve()))
            synchroniser_csv_propre(df_clean)
            ecrire_rapport_execution(
                "NETTOYAGE_ET_INGESTION_STREAMLIT",
                f"Fichier {nom_fichier} nettoyé puis chargé dans SQLite "
                f"({len(df_clean)} lignes).",
            )
            print(
                "✅ Ingestion SQL automatique terminée à partir du tableau "
                "nettoyé ci-dessus."
            )
    except HTTPException:
        raise
    except Exception as erreur:
        LOGGER.exception(
            "Échec du nettoyage ou de l'ingestion pour le fichier %s",
            nom_fichier,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Le nettoyage ou le chargement SQL a échoué. "
                "Aucun résultat de succès n'a été confirmé; contactez le support "
                "avec l'heure de l'erreur."
            ),
        ) from erreur

    texte_console = journal_console.getvalue()
    sortie_console.write_text(texte_console, encoding="utf-8")
    chemin_rapport = dossier_sortie / "rapport_execution_m_e.md"
    chemin_capitalisation = dossier_sortie / "edna_mode_capit.json"
    contenu_rapport = (
        chemin_rapport.read_text(encoding="utf-8")
        if chemin_rapport.is_file()
        else ""
    )
    return {
        "statut": "succes",
        "message": (
            f"'{nom_fichier}' a été nettoyé puis chargé automatiquement dans SQL."
        ),
        "lignes_traitees": len(df_clean),
        "lignes_consentantes": bilan_sql["lignes_consentantes"],
        "lignes_par_table": bilan_sql["lignes_par_table"],
        "fichiers_generes": [
            str(chemin_csv),
            str(chemin_rapport),
            str(chemin_capitalisation),
            str(sortie_console),
        ],
        "rapport_execution": contenu_rapport,
        "rapport_console": texte_console[-30000:],
        "rapport_console_tronque": len(texte_console) > 30000,
        "avertissements": bilan["avertissements"],
    }


@app.post("/enquetes/importer-fichier", dependencies=[Depends(verifier_acces_api)])
def importer_fichier_kobo(
    file: UploadFile = File(...),
):
    try:
        survey, choices = charger_questionnaire()
        survey["name"] = survey["name"].astype(str).str.strip().str.lower()
        variables_survey = set(survey["name"])
        col_consent_technique = "volont"
        if col_consent_technique not in variables_survey:
            raise HTTPException(
                status_code=500,
                detail="La colonne de consentement 'volont' est introuvable dans l'onglet survey.",
            )

        contents = file.file.read()
        nom_fichier = file.filename or "fichier_kobo"
        extension = Path(nom_fichier).suffix.lower()
        if extension == ".csv":
            df_input = pd.read_csv(io.BytesIO(contents), encoding="utf-8-sig")
        elif extension == ".xlsx":
            df_input = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(
                status_code=400,
                detail="Format non pris en charge. Importez un fichier CSV ou XLSX.",
            )
        colonnes_brutes = {
            str(colonne).strip().lower() for colonne in df_input.columns
        }
        if col_consent_technique not in colonnes_brutes:
            raise HTTPException(
                status_code=400,
                detail=f"La colonne de consentement '{col_consent_technique}' est absente du fichier Kobo.",
            )
        colonne_consent_brute = next(
            colonne
            for colonne in df_input.columns
            if str(colonne).strip().lower() == col_consent_technique
        )
        df_input[colonne_consent_brute] = df_input[
            colonne_consent_brute
        ].map(normaliser_consentement_import)

        jetons_reserves = set()
        if os.path.exists(DB_PATH):
            with closing(sqlite3.connect(DB_PATH)) as conn:
                table_meta = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'META_ENQUETE'"
                ).fetchone()
                if table_meta:
                    jetons_reserves = {
                        str(ligne[0]).strip()
                        for ligne in conn.execute(
                            "SELECT code_jeton FROM META_ENQUETE "
                            "WHERE code_jeton IS NOT NULL"
                        )
                    }

        df_clean = executer_nettoyage_global(
            df_input,
            survey,
            choices,
            date_debut_saisie="",
            date_fin_saisie="",
            col_consent_technique=col_consent_technique,
            col_id_technique="code_jeton",
            sauvegarder_csv=False,
            generer_rapport=False,
            codes_jetons_reserves=jetons_reserves,
        )
        if df_clean.empty:
            raise HTTPException(status_code=400, detail="Données vides après nettoyage.")

        df_clean["id_menage"] = prochains_identifiants_menage(len(df_clean))
        jetons = (
            df_clean["code_jeton"].dropna().astype(str).str.strip().unique().tolist()
            if "code_jeton" in df_clean.columns
            else []
        )
        if jetons and os.path.exists(DB_PATH):
            with closing(sqlite3.connect(DB_PATH)) as conn:
                table_meta = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'META_ENQUETE'"
                ).fetchone()
                if table_meta:
                    placeholders = ",".join("?" for _ in jetons)
                    deja_presents = conn.execute(
                        "SELECT code_jeton FROM META_ENQUETE "
                        f"WHERE CAST(code_jeton AS TEXT) IN ({placeholders})",
                        jetons,
                    ).fetchall()
                    if deja_presents:
                        raise HTTPException(
                            status_code=409,
                            detail="Un ou plusieurs codes jeton existent déjà dans la base. "
                            "Utilisez la réhabilitation du cache pour restaurer une enquête supprimée.",
                        )

        bilan_sql = ingest_data(df_clean, DB_PATH)
        synchroniser_csv_propre(df_clean)
        global nb_lignes_ajoutees_api
        nb_lignes_ajoutees_api = globals().get("nb_lignes_ajoutees_api", 0) + len(
            df_clean
        )
        ecrire_rapport_execution(
            "IMPORT_FICHIER",
            f"Fichier {nom_fichier} nettoyé par le pipeline puis intégré "
            f"dans SQLite et le CSV propre ({len(df_clean)} lignes).",
        )
        return {
            "statut": "succes",
            "message": f"Fichier '{nom_fichier}' nettoyé et intégré dans SQLite et le CSV propre.",
            "lignes_traitees": len(df_clean),
            "lignes_consentantes": bilan_sql["lignes_consentantes"],
            "lignes_par_table": bilan_sql["lignes_par_table"],
            "perimetre_total_estime": nb_lignes_ajoutees_api,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/enquetes/config-import", dependencies=[Depends(verifier_acces_api)])
def obtenir_configuration_import():
    try:
        survey, _ = charger_questionnaire()
        colonnes = []
        for _, row in survey.iterrows():
            nom = str(row.get("name", "")).strip().lower()
            type_question = str(row.get("type", "")).strip().lower()
            if (
                nom
                and nom != "nan"
                and not type_question.startswith(("begin group", "end group"))
            ):
                colonnes.append({"name": nom, "type": type_question})
        return {"colonnes": colonnes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/enquetes/archives-suppressions", dependencies=[Depends(verifier_acces_api)])
def lister_archives_suppressions():
    archives = []
    if not CACHE_SUPPRESSIONS_DIR.exists():
        return {"archives": archives}

    for chemin in sorted(
        CACHE_SUPPRESSIONS_DIR.glob("menage_*.csv"),
        key=lambda fichier: fichier.stat().st_mtime,
        reverse=True,
    ):
        try:
            apercu = pd.read_csv(
                chemin,
                usecols=lambda colonne: colonne in {"id_menage", "code_jeton"},
                nrows=1,
                dtype=str,
            )
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            continue
        archives.append(
            {
                "nom_fichier": chemin.name,
                "id_menage": (
                    apercu["id_menage"].iloc[0]
                    if "id_menage" in apercu.columns and not apercu.empty
                    else ""
                ),
                "code_jeton": (
                    apercu["code_jeton"].iloc[0]
                    if "code_jeton" in apercu.columns and not apercu.empty
                    else ""
                ),
            }
        )
    return {"archives": archives}


@app.post("/enquetes/restaurer-archive", dependencies=[Depends(verifier_acces_api)])
def restaurer_archive_suppression(payload: ArchiveRestaurationPayload):
    nom_fichier = Path(payload.nom_fichier).name
    if nom_fichier != payload.nom_fichier or not nom_fichier.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Nom d'archive invalide.")

    chemin_archive = CACHE_SUPPRESSIONS_DIR / nom_fichier
    if not chemin_archive.is_file():
        raise HTTPException(status_code=404, detail="Archive de suppression introuvable.")

    try:
        df_archive = pd.read_csv(chemin_archive, encoding="utf-8-sig")
        if len(df_archive) != 1 or "id_menage" not in df_archive.columns:
            raise HTTPException(
                status_code=400,
                detail="L'archive ne contient pas une enquête restaurable valide.",
            )

        id_menage = str(df_archive.iloc[0]["id_menage"]).strip()
        if not id_menage or id_menage.lower() == "nan":
            raise HTTPException(
                status_code=400,
                detail="L'identifiant du ménage est absent de l'archive.",
            )
        df_archive["id_menage"] = id_menage

        if os.path.exists(DB_PATH):
            with closing(sqlite3.connect(DB_PATH)) as conn:
                existe_id = conn.execute(
                    "SELECT 1 FROM META_ENQUETE WHERE id_menage = ?",
                    (id_menage,),
                ).fetchone()
                jeton = df_archive.iloc[0].get("code_jeton")
                existe_jeton = None
                if pd.notna(jeton):
                    existe_jeton = conn.execute(
                        "SELECT 1 FROM META_ENQUETE "
                        "WHERE CAST(code_jeton AS TEXT) = ? AND id_menage != ?",
                        (str(jeton).strip(), id_menage),
                    ).fetchone()
                if existe_id or existe_jeton:
                    raise HTTPException(
                        status_code=409,
                        detail="Cette enquête ou son code jeton existe déjà dans la base.",
                    )

        bilan_sql = ingest_data(df_archive, DB_PATH)
        try:
            synchroniser_csv_propre(df_archive)
        except Exception:
            with closing(sqlite3.connect(DB_PATH)) as conn:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (table,) in tables:
                    colonnes = {
                        row[1]
                        for row in conn.execute(f'PRAGMA table_info("{table}")')
                    }
                    if "id_menage" in colonnes:
                        conn.execute(
                            f'DELETE FROM "{table}" WHERE id_menage = ?',
                            (id_menage,),
                        )
                conn.commit()
            raise
        ecrire_rapport_execution(
            "REHABILITATION_ENQUETE",
            f"Ménage {id_menage} restauré depuis cache/suppressions/{nom_fichier} "
            "dans SQLite et le CSV propre (archive déjà nettoyée, pipeline non rejoué).",
        )
        try:
            chemin_archive.unlink()
            archive_supprimee = True
            avertissement = None
        except OSError as erreur_cache:
            archive_supprimee = False
            avertissement = f"Archive conservée dans le cache : {erreur_cache}"
        return {
            "statut": "succes",
            "message": f"L'enquête {id_menage} a été réhabilitée.",
            "id_menage": id_menage,
            "archive_supprimee": archive_supprimee,
            "avertissement": avertissement,
            "lignes_par_table": bilan_sql["lignes_par_table"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/enquetes/champs-modifiables", dependencies=[Depends(verifier_acces_api)])
def lister_champs_modifiables():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="La base de données n'est pas encore initialisée.")

    try:
        metadonnees = charger_metadonnees_modification()
        conn = sqlite3.connect(DB_PATH)
        try:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            colonnes_par_table = {}
            for (table,) in tables:
                colonnes_par_table[table] = {
                    row[1]
                    for row in conn.execute(f'PRAGMA table_info("{table}")')
                }
        finally:
            conn.close()

        champs = []
        for nom, metadata in metadonnees.items():
            tables_champ = [
                table
                for table, colonnes in colonnes_par_table.items()
                if nom in colonnes and nom != "id_menage"
            ]
            if len(tables_champ) == 1:
                champs.append(
                    {
                        "name": nom,
                        "type": metadata["type"],
                        "choices": metadata["choices"],
                    }
                )

        return {"champs": champs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/enquetes/modifier-champ/{code_jeton}", dependencies=[Depends(verifier_acces_api)])
def modifier_champ_enquete(code_jeton: str, payload: ModificationPayload):
    csv_path = "outputs/donnees_nettoyees.csv"
    csv_temp_path = None
    conn = None
    try:
        colonne = payload.colonne
        metadonnees = charger_metadonnees_modification()
        if colonne not in metadonnees:
            raise HTTPException(
                status_code=400,
                detail=f"La colonne '{colonne}' n'existe pas dans l'onglet survey.",
            )

        metadata = metadonnees[colonne]
        type_question = metadata["type"]
        choix_valides = metadata["choices"]
        type_base = type_question.split(maxsplit=1)[0]
        valeur_brute = payload.valeur

        if type_base == "select_one":
            if not isinstance(valeur_brute, str) or valeur_brute not in choix_valides:
                raise HTTPException(status_code=400, detail="La valeur ne fait pas partie des choix autorisés.")
            valeur_nettoyee = valeur_brute
        elif type_base == "select_multiple":
            if not isinstance(valeur_brute, list) or any(
                not isinstance(value, str) or value not in choix_valides
                for value in valeur_brute
            ):
                raise HTTPException(status_code=400, detail="Une ou plusieurs valeurs ne font pas partie des choix autorisés.")
            valeur_nettoyee = ", ".join(valeur_brute)
        elif type_base == "integer":
            try:
                valeur_nettoyee = int(valeur_brute)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Une valeur entière est requise.")
        elif type_base == "decimal":
            try:
                valeur_nettoyee = float(valeur_brute)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Une valeur décimale est requise.")
            if not math.isfinite(valeur_nettoyee):
                raise HTTPException(status_code=400, detail="La valeur décimale doit être finie.")
        elif type_base == "date":
            try:
                valeur_nettoyee = datetime.strptime(str(valeur_brute), "%Y-%m-%d").date().isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail="La date doit être au format AAAA-MM-JJ.")
        elif type_base in {"start", "end", "datetime"}:
            try:
                valeur_nettoyee = datetime.fromisoformat(
                    str(valeur_brute).replace("Z", "+00:00")
                ).isoformat()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="La date et l'heure doivent être au format ISO 8601.",
                )
        elif type_base == "time":
            heure = str(valeur_brute)
            valeur_nettoyee = None
            for format_heure in ("%H:%M", "%H:%M:%S"):
                try:
                    valeur_nettoyee = datetime.strptime(heure, format_heure).strftime(
                        format_heure
                    )
                    break
                except ValueError:
                    continue
            if valeur_nettoyee is None:
                raise HTTPException(
                    status_code=400,
                    detail="L'heure doit être au format HH:MM ou HH:MM:SS.",
                )
        else:
            if not isinstance(valeur_brute, str):
                raise HTTPException(status_code=400, detail="Une valeur textuelle est requise.")
            valeur_nettoyee = valeur_brute

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        tables_champ = []
        for (table,) in tables:
            colonnes_table = {
                row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
            }
            if colonne in colonnes_table and "id_menage" in colonnes_table:
                tables_champ.append(table)
        if len(tables_champ) != 1:
            raise HTTPException(
                status_code=400,
                detail=f"La colonne '{colonne}' n'est pas disponible dans une table de la base.",
            )

        table = tables_champ[0]
        colonnes_table = {
            row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
        }
        conditions_identifiant = ['"id_menage" = ?']
        parametres_identifiant = [code_jeton]
        conditions_identifiant.append('CAST("code_jeton" AS TEXT) = ?')
        parametres_identifiant.append(code_jeton)
        jeton_numerique = pd.to_numeric(code_jeton, errors="coerce")
        if pd.notna(jeton_numerique):
            conditions_identifiant.append('CAST("code_jeton" AS INTEGER) = ?')
            parametres_identifiant.append(int(jeton_numerique))

        menages = conn.execute(
            "SELECT id_menage FROM META_ENQUETE "
            f'WHERE {" OR ".join(conditions_identifiant)}',
            parametres_identifiant,
        ).fetchall()
        if not menages:
            raise HTTPException(
                status_code=404,
                detail="Ménage introuvable.",
            )
        if len(menages) > 1:
            raise HTTPException(
                status_code=409,
                detail="Ce code jeton correspond à plusieurs ménages. Utilisez l'identifiant du ménage.",
            )

        record_id = menages[0]["id_menage"]
        enregistrements = conn.execute(
            f'SELECT "{colonne}" FROM "{table}" WHERE "id_menage" = ?',
            (record_id,),
        ).fetchall()
        if not enregistrements:
            raise HTTPException(
                status_code=404,
                detail="Cette réponse n'est pas enregistrée pour le ménage (par exemple, question non applicable ou ménage non consentant).",
            )

        ancienne_valeur = enregistrements[0][colonne]
        if str(ancienne_valeur) == str(valeur_nettoyee):
            return {
                "statut": "info",
                "message": f"Aucun changement détecté pour le champ '{colonne}'. Valeur inchangée.",
                "valeur_appliquee": valeur_nettoyee,
            }

        if os.path.exists(csv_path):
            df_csv = pd.read_csv(
                csv_path,
                dtype={"id_menage": "string", "code_jeton": "string"},
            )
            masque_cible = pd.Series(False, index=df_csv.index)
            if "id_menage" in df_csv.columns:
                masque_cible |= df_csv["id_menage"].eq(record_id).fillna(False)
            if "code_jeton" in df_csv.columns:
                jetons_csv = df_csv["code_jeton"].str.strip()
                masque_cible |= jetons_csv.eq(code_jeton).fillna(False)
                jeton_numerique = pd.to_numeric(code_jeton, errors="coerce")
                if pd.notna(jeton_numerique):
                    masque_cible |= pd.to_numeric(
                        jetons_csv, errors="coerce"
                    ).eq(jeton_numerique).fillna(False)
            if not masque_cible.any():
                raise HTTPException(
                    status_code=409,
                    detail="Le ménage existe dans SQLite mais pas dans le CSV propre; modification annulée pour éviter des données désynchronisées.",
                )
            if colonne not in df_csv.columns:
                df_csv[colonne] = pd.NA
            else:
                df_csv[colonne] = df_csv[colonne].astype("object")
            df_csv.loc[masque_cible, colonne] = valeur_nettoyee
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix=".csv",
                prefix="donnees_nettoyees_",
                dir=os.path.dirname(csv_path) or ".",
                delete=False,
            ) as fichier_temp:
                csv_temp_path = fichier_temp.name
                df_csv.to_csv(fichier_temp, index=False)

        conn.execute(
            f'UPDATE "{table}" SET "{colonne}" = ? WHERE "id_menage" = ?',
            (valeur_nettoyee, record_id),
        )
        conn.commit()
        if csv_temp_path:
            os.replace(csv_temp_path, csv_path)
            csv_temp_path = None

        json_path = "outputs/edna_mode_capit.json"
        try:
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data_json = json.load(f)
                    if not isinstance(data_json, list):
                        data_json = [data_json]
            else:
                data_json = []

            data_json.append(
                {
                    "code_jeton": code_jeton,
                    "colonne_corrigee": colonne,
                    "nouvelle_valeur": valeur_nettoyee,
                    "contexte": "Correction manuelle validée par un agent",
                }
            )
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data_json, f, ensure_ascii=False, indent=4)
        except Exception as json_err:
            print(f"Avertissement - Écriture JSON impossible : {json_err}")

        ecrire_rapport_execution(
            "MODIFICATION_CHAMP",
            f"Ménage {code_jeton} - Colonne '{colonne}' modifiée dans {table} "
            f"({valeur_nettoyee}).",
        )
        return {
            "statut": "succes",
            "message": f"Champ '{colonne}' mis à jour dans la base et le CSV propre.",
            "valeur_appliquee": valeur_nettoyee,
        }
    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise
    except Exception as e:
        if conn is not None:
            conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            conn.close()
        if csv_temp_path and os.path.exists(csv_temp_path):
            os.remove(csv_temp_path)
