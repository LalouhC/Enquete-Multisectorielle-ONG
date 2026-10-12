"""Module technique de calcul des indicateurs de vulnérabilité.

Les fonctions sont appelées par les analyses et ne lisent ni n'écrivent de base de données.
Le DataFrame d'entrée contient les tables relationnelles aplaties; un profil
validé peut relier ses colonnes et modalités aux notions attendues. Les variables
absentes rendent leurs indicateurs indisponibles sans bloquer les autres calculs.
Le résultat conserve les variables d'origine et ajoute les indicateurs calculés.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Mapping

import pandas as pd


RACINE_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_PROFILS_QUESTIONNAIRES = RACINE_PROJET / "config" / "profils_questionnaires"
VERSION_PROFIL_QUESTIONNAIRE = 1

BAREMES_ABRI_OPTIONNELS = {
    "B": {},
    "D": {},
    "E": {},
    "F": {},
    "G": {},
}

BAREME_AME = {
    "nb_bidon": [(16, 1000, 0), (13.7, 16, 0), (11.4, 13.7, .5), (9.1, 11.4, 1), (6.8, 9.1, 1.5), (4.5, 6.8, 2), (3.5, 4.5, 2.5), (2.5, 3.5, 3), (1.7, 2.5, 3.5), (.8, 1.7, 4), (0, .8, 4.5), (-1, 0, 5)],
    "nb_cass": [(5, 1000, 0), (4.4, 5, 0), (3.8, 4.4, .5), (3.2, 3.8, 1), (2.6, 3.2, 1.5), (2, 2.6, 2), (1.5, 2, 2.5), (1, 1.5, 3), (.67, 1, 3.5), (.33, .67, 4), (0, .33, 4.5), (-1, 0, 5)],
    "nb_bas": [(4, 1000, 0), (3.4, 4, 0), (2.8, 3.4, .5), (2.2, 2.8, 1), (1.6, 2.2, 1.5), (1, 1.6, 2), (.75, 1, 2.5), (.5, .75, 3), (.33, .5, 3.5), (.17, .33, 4), (0, .17, 4.5), (-1, 0, 5)],
    "nb_outil": [(5, 1000, 0), (4.6, 5, 0), (4.2, 4.6, .5), (3.8, 4.2, 1), (3.4, 3.8, 1.5), (3, 3.4, 2), (2, 3, 2.5), (1, 2, 3), (.7, 1, 3.5), (.3, .7, 4), (0, .3, 4.5), (-1, 0, 5)],
    "nb_couch": [(1, 1000, 0), (.88, 1, 0), (.76, .88, .5), (.64, .76, 1), (.52, .64, 1.5), (.4, .52, 2), (.3, .4, 2.5), (.2, .3, 3), (.13, .2, 3.5), (.07, .13, 4), (0, .07, 4.5), (-1, 0, 5)],
    "nb_couv": [(1, 1000, 0), (.88, 1, 0), (.76, .88, .5), (.64, .76, 1), (.52, .64, 1.5), (.4, .52, 2), (.3, .4, 2.5), (.2, .3, 3), (.13333, .2, 3.5), (.06667, .13333, 4), (0, .06667, 4.5), (-1, 0, 5)],
    "nb_habit_femme": [(5, 1000, 0), (4.6, 5, 0), (4.2, 4.6, .5), (3.8, 4.2, 1), (3.4, 3.8, 1.5), (3, 3.4, 2), (2.25, 3, 2.5), (1.5, 2.25, 3), (1, 1.5, 3.5), (.5, 1, 4), (0, .5, 4.5), (-1, 0, 5)],
    "nb_habit_e": [(5, 1000, 0), (4.6, 5, 0), (4.2, 4.6, .5), (3.8, 4.2, 1), (3.4, 3.8, 1.5), (3, 3.4, 2), (2.25, 3, 2.5), (1.5, 2.25, 3), (1, 1.5, 3.5), (.5, 1, 4), (0, .5, 4.5), (-1, 0, 5)],
}
ARTICLES_PONDERES_PAR_TAILLE = {"nb_bidon", "nb_couch", "nb_couv"}

_GROUPES_AGE = ["0_5", "6_24", "25_59", "5_14", "15_17", "18_49", "50_59", "plus60"]
_COLONNES_COMPOSITION = [
    f"{sexe}_{groupe}"
    for sexe in ("h", "f")
    for groupe in _GROUPES_AGE
]
_COLONNES_REQUISES = set(
    _COLONNES_COMPOSITION
    + [
        "fem_enc", "fem_all", "adultincap", "hand",
        "malnut", "vis_ss", "hear_ss", "mob_ss", "cog_ss", "sc_ss", "com_ss",
        "status", "observation_0", "lieu_hab", "environ",
        "ressources", "repas_r", "suffisant", "repas_f", "manque", "repas_m",
        "nb_bidon", "nb_cass", "nb_bas", "nb_outil", "nb_couch", "nb_couv",
        "nb_habit_femme", "nb_habit_e", "statmtr", "decision",
        "revenu", "montant_dette", "loyer_depl_montant", "loyer_auto_montant",
        "capacite", "capacites", "eau", "separer",
        "agro", "terre", "outims", "personne", "eau_point", "asso",
        "date_agro", "date_enquete",
    ]
)
VARIABLES_PAR_INDICATEUR = {
    "taille_menage": {"taille_menage"},
    "ratio_dependance": set(_COLONNES_COMPOSITION),
    "handicap_wg": {"vis_ss", "hear_ss", "mob_ss", "cog_ss", "sc_ss", "com_ss"},
    "score_abri_reduit": {"status", "observation_0", "lieu_hab", "environ"},
    "score_hhs_total": {"ressources", "repas_r", "suffisant", "repas_f", "manque", "repas_m"},
    "score_ame_global": {"taille_menage", *BAREME_AME},
    "score_genre_vulnerabilite_critique": {"statmtr", "decision"},
    "indicateurs_economiques": {
        "revenu", "montant_dette", "loyer_depl_montant", "loyer_auto_montant",
    },
    "score_global_wash": {
        "taille_menage", "capacite", "capacites", "eau", "separer",
    },
    "score_global_agro": {
        "agro", "terre", "outims", "personne", "eau_point", "asso",
        "date_agro", "date_enquete",
    },
}
INDICATEURS_METHODE_INCOMPLETE = {
    "score_abri_officiel": "Les barèmes des critères B à G ne sont pas configurés."
}

__all__ = [
    "ARTICLES_PONDERES_PAR_TAILLE",
    "BAREME_AME",
    "BAREMES_ABRI_OPTIONNELS",
    "calculer_handicap_washington_group",
    "calculer_hhs",
    "calculer_score_abri_partiel",
    "calculer_score_ame_officiel",
    "calculer_scores",
    "calculer_empreinte_questionnaire",
    "charger_profil_questionnaire",
    "enregistrer_profil_questionnaire",
    "indicateur_oui_non",
    "normaliser_texte",
    "proposer_correspondances",
    "verifier_profil_questionnaire",
    "pipeline_agro_severite_complet",
    "pipeline_demographie_et_handicap",
    "pipeline_indicateurs_economiques",
    "pipeline_vulnerabilite_sociale_decisionnelle",
    "pipeline_wash_severite_complet",
    "trouver_score_par_intervalle",
]


def normaliser_texte(valeur: object) -> str:
    """Normalise un libellé pour comparer accents, casse et ponctuation."""
    if pd.isna(valeur):
        return ""
    texte = unicodedata.normalize("NFKD", str(valeur))
    texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere))
    return re.sub(r"[^a-z0-9]+", " ", texte.lower()).strip()


def indicateur_oui_non(serie: pd.Series) -> pd.Series:
    """Recodage strict oui/non ; toute autre réponse reste manquante."""
    return serie.map(normaliser_texte).map({"oui": 1, "non": 0}).astype("Int64")


def _valider_identifiant_profil(identifiant: str) -> str:
    if not isinstance(identifiant, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identifiant):
        raise ValueError("L'identifiant du profil doit contenir uniquement lettres, chiffres, '_' ou '-'.")
    return identifiant


def _chaine_non_nulle(valeur: object) -> str:
    return "" if pd.isna(valeur) else str(valeur).strip()


def _libelle_question(question: Mapping[str, object]) -> str:
    for cle, valeur in question.items():
        if str(cle).lower().startswith("label"):
            texte = _chaine_non_nulle(valeur)
            if texte:
                return texte
    return ""


def _signature_table_xlsform(table: pd.DataFrame) -> dict:
    colonnes = sorted(str(colonne) for colonne in table.columns)
    lignes = [
        {
            colonne: _chaine_non_nulle(ligne[colonne])
            for colonne in colonnes
        }
        for _, ligne in table.iterrows()
    ]
    return {"colonnes": colonnes, "lignes": lignes}


def calculer_empreinte_questionnaire(
    questions: pd.DataFrame,
    choix: pd.DataFrame | None = None,
) -> str:
    """Calcule une empreinte SHA-256 des lignes, règles et choix des onglets XLSForm."""
    if not isinstance(questions, pd.DataFrame):
        raise TypeError("questions doit être un pandas.DataFrame issu de l'onglet survey.")
    if choix is not None and not isinstance(choix, pd.DataFrame):
        raise TypeError("choix doit être un pandas.DataFrame issu de l'onglet choices.")
    contenu = json.dumps(
        {
            "survey": _signature_table_xlsform(questions),
            "choices": _signature_table_xlsform(choix) if choix is not None else None,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def verifier_profil_questionnaire(
    profil: dict,
    questions: pd.DataFrame,
    choix: pd.DataFrame | None = None,
) -> str:
    """Vérifie que le profil enregistré correspond au XLSForm chargé."""
    empreinte_enregistree = profil.get("empreinte_questionnaire") if isinstance(profil, dict) else None
    if not isinstance(empreinte_enregistree, str) or not re.fullmatch(r"[0-9a-f]{64}", empreinte_enregistree):
        raise ValueError("Le profil doit contenir l'empreinte SHA-256 du XLSForm validé.")
    empreinte_actuelle = calculer_empreinte_questionnaire(questions, choix)
    if empreinte_actuelle != empreinte_enregistree:
        raise ValueError(
            "Le XLSForm sélectionné ne correspond pas à celui du profil. "
            "Vérifiez et revalidez les correspondances avant de calculer les scores."
        )
    return empreinte_actuelle


def charger_profil_questionnaire(identifiant: str) -> dict:
    """Charge un profil versionné du projet, sans appliquer de correspondance non validée."""
    identifiant = _valider_identifiant_profil(identifiant)
    chemin = DOSSIER_PROFILS_QUESTIONNAIRES / f"{identifiant}.json"
    if not chemin.is_file():
        raise FileNotFoundError(f"Aucun profil questionnaire enregistré pour '{identifiant}': {chemin}")
    with chemin.open(encoding="utf-8") as fichier:
        profil = json.load(fichier)
    if not isinstance(profil, dict) or profil.get("version_schema") != VERSION_PROFIL_QUESTIONNAIRE:
        raise ValueError(f"Version ou structure de profil non prise en charge dans {chemin}.")
    if profil.get("identifiant") != identifiant:
        raise ValueError(f"L'identifiant déclaré dans {chemin} ne correspond pas au nom du fichier.")
    if not isinstance(profil.get("correspondances"), dict):
        raise ValueError(f"Le profil {identifiant} doit contenir un objet 'correspondances'.")
    if not isinstance(profil.get("empreinte_questionnaire"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", profil["empreinte_questionnaire"]
    ):
        raise ValueError(f"Le profil {identifiant} doit contenir une empreinte SHA-256 valide du XLSForm.")
    return profil


def enregistrer_profil_questionnaire(profil: dict) -> Path:
    """Enregistre les correspondances et leur validation dans le projet."""
    if not isinstance(profil, dict):
        raise TypeError("profil doit être un dictionnaire.")
    identifiant = _valider_identifiant_profil(profil.get("identifiant"))
    if profil.get("version_schema") != VERSION_PROFIL_QUESTIONNAIRE:
        raise ValueError(f"version_schema doit valoir {VERSION_PROFIL_QUESTIONNAIRE}.")
    correspondances = profil.get("correspondances")
    if not isinstance(correspondances, dict):
        raise ValueError("profil doit contenir un objet 'correspondances'.")
    empreinte = profil.get("empreinte_questionnaire")
    if not isinstance(empreinte, str) or not re.fullmatch(r"[0-9a-f]{64}", empreinte):
        raise ValueError("profil doit contenir l'empreinte SHA-256 du XLSForm validé.")
    for notion, correspondance in correspondances.items():
        if notion not in _COLONNES_REQUISES | {"taille_menage"}:
            raise ValueError(f"Notion de score inconnue dans le profil: {notion}")
        if not isinstance(correspondance, dict) or not isinstance(correspondance.get("source"), str):
            raise ValueError(f"La correspondance '{notion}' doit définir une variable 'source'.")
        if not correspondance["source"].strip():
            raise ValueError(f"La variable source de '{notion}' ne peut pas être vide.")
        if not isinstance(correspondance.get("validee"), bool):
            raise ValueError(f"La correspondance '{notion}' doit préciser 'validee' à true ou false.")
        modalites = correspondance.get("modalites", {})
        if not isinstance(modalites, dict) or not all(
            isinstance(code, str) and isinstance(valeur, str)
            for code, valeur in modalites.items()
        ):
            raise ValueError(f"Les modalités de '{notion}' doivent associer des codes et valeurs textuels.")

    DOSSIER_PROFILS_QUESTIONNAIRES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_PROFILS_QUESTIONNAIRES / f"{identifiant}.json"
    profil_a_enregistrer = {
        "version_schema": VERSION_PROFIL_QUESTIONNAIRE,
        **profil,
        "identifiant": identifiant,
    }
    with chemin.open("w", encoding="utf-8", newline="\n") as fichier:
        json.dump(profil_a_enregistrer, fichier, ensure_ascii=False, indent=2)
        fichier.write("\n")
    return chemin


def proposer_correspondances(
    questions: pd.DataFrame,
    profils: list[dict] | None = None,
    *,
    seuil: float = 0.62,
) -> list[dict]:
    """Suggère des variables similaires à des correspondances validées antérieures."""
    if not isinstance(questions, pd.DataFrame):
        raise TypeError("questions doit être un pandas.DataFrame issu de l'onglet survey.")
    if not 0 <= seuil <= 1:
        raise ValueError("seuil doit être compris entre 0 et 1.")
    if profils is None:
        profils = [
            charger_profil_questionnaire(chemin.stem)
            for chemin in sorted(DOSSIER_PROFILS_QUESTIONNAIRES.glob("*.json"))
        ] if DOSSIER_PROFILS_QUESTIONNAIRES.is_dir() else []

    questions_cibles = []
    for _, ligne in questions.iterrows():
        nom = _chaine_non_nulle(ligne.get("name", ""))
        if not nom:
            continue
        questions_cibles.append({
            "source": nom,
            "libelle": _libelle_question(ligne),
            "type": _chaine_non_nulle(ligne.get("type", "")),
        })

    suggestions = []
    for profil in profils:
        if not isinstance(profil, dict) or not isinstance(profil.get("correspondances"), dict):
            raise ValueError("Chaque profil utilisé pour les suggestions doit contenir 'correspondances'.")
        for notion, reference in profil["correspondances"].items():
            if not isinstance(reference, dict) or not reference.get("validee", False):
                continue
            nom_reference = _chaine_non_nulle(reference.get("source", ""))
            libelle_reference = _chaine_non_nulle(reference.get("libelle", ""))
            type_reference = _chaine_non_nulle(reference.get("type", ""))
            candidats = []
            for question in questions_cibles:
                score_nom = SequenceMatcher(
                    None, normaliser_texte(nom_reference), normaliser_texte(question["source"]), autojunk=False
                ).ratio()
                libelle_cible = normaliser_texte(question["libelle"])
                score_libelle = SequenceMatcher(
                    None, normaliser_texte(libelle_reference), libelle_cible, autojunk=False
                ).ratio() if libelle_reference and libelle_cible else 0.0
                score = max(score_nom, score_libelle)
                type_reference_normalise = normaliser_texte(type_reference).split(" ")[0]
                type_cible_normalise = normaliser_texte(question["type"]).split(" ")[0]
                if type_reference_normalise and type_cible_normalise:
                    score += 0.05 if type_reference_normalise == type_cible_normalise else -0.15
                score = min(1.0, max(0.0, score))
                if score >= seuil:
                    candidats.append((score, question))
            if candidats:
                score, candidat = max(candidats, key=lambda element: element[0])
                suggestions.append({
                    "notion": notion,
                    "source_suggeree": candidat["source"],
                    "libelle_suggere": candidat["libelle"],
                    "score_similarite": round(score, 3),
                    "profil_source": profil.get("identifiant", ""),
                    "validee": False,
                })
    return sorted(suggestions, key=lambda suggestion: (-suggestion["score_similarite"], suggestion["notion"]))


def _preparer_variables_score(
    df: pd.DataFrame,
    correspondances: Mapping[str, str] | None,
    modalites: Mapping[str, Mapping[str, str]] | None,
) -> tuple[pd.DataFrame, set[str], dict[str, list[str]]]:
    resultat = df.copy()
    colonnes_disponibles = set(resultat.columns)
    sources_utilisees = set()
    for notion, source in (correspondances or {}).items():
        if notion not in _COLONNES_REQUISES | {"taille_menage"}:
            raise ValueError(f"Variable cible de score inconnue: {notion}")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"La source de la correspondance '{notion}' doit être un nom de colonne.")
        if source not in colonnes_disponibles:
            raise ValueError(f"La colonne source '{source}' de '{notion}' est absente du DataFrame.")
        if source in sources_utilisees:
            raise ValueError(f"La colonne source '{source}' est utilisée pour plusieurs notions de score.")
        if source != notion:
            resultat[notion] = resultat[source]
        sources_utilisees.add(source)

    modalites_non_reconnues = {}
    for notion, table_modalites in (modalites or {}).items():
        if notion not in resultat.columns:
            raise ValueError(f"Les modalités de '{notion}' ne peuvent pas être appliquées sans cette variable.")
        if not isinstance(table_modalites, Mapping) or not all(
            isinstance(code, str) and isinstance(valeur, str)
            for code, valeur in table_modalites.items()
        ):
            raise ValueError(f"La table des modalités de '{notion}' doit contenir des valeurs textuelles.")
        table_normalisee = {normaliser_texte(code): valeur for code, valeur in table_modalites.items()}
        if table_normalisee:
            inconnues = sorted({
                str(valeur)
                for valeur in resultat[notion].dropna().unique()
                if normaliser_texte(valeur) not in table_normalisee
            })
            if inconnues:
                modalites_non_reconnues[notion] = inconnues
        resultat[notion] = resultat[notion].map(
            lambda valeur: table_normalisee.get(normaliser_texte(valeur), valeur)
        )

    disponibles = set(resultat.columns)
    for variable in _COLONNES_REQUISES - disponibles:
        resultat[variable] = pd.NA
    return resultat, disponibles, modalites_non_reconnues


def pipeline_demographie_et_handicap(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule taille, ratio de dépendance et alertes démographiques séparément."""
    df = df.copy()
    df[_COLONNES_COMPOSITION] = df[_COLONNES_COMPOSITION].apply(pd.to_numeric, errors="coerce")
    taille_calculee = df[_COLONNES_COMPOSITION].sum(axis=1, min_count=len(_COLONNES_COMPOSITION))
    if "taille_menage" in df:
        taille_fournie = pd.to_numeric(df["taille_menage"], errors="coerce")
        df["taille_menage"] = taille_fournie.where(taille_fournie.notna(), taille_calculee)
    else:
        df["taille_menage"] = taille_calculee

    dependants = [
        f"{sexe}_{groupe}"
        for sexe in ("h", "f")
        for groupe in ("0_5", "6_24", "25_59", "5_14", "15_17", "plus60")
    ]
    actifs = [f"{sexe}_{groupe}" for sexe in ("h", "f") for groupe in ("18_49", "50_59")]
    n_dependants = df[dependants].sum(axis=1, min_count=len(dependants))
    n_actifs = df[actifs].sum(axis=1, min_count=len(actifs)).where(lambda valeurs: valeurs > 0)
    df["ratio_dependance"] = n_dependants / n_actifs
    connu = df["ratio_dependance"].notna()
    df["cible_ratio_dependance_critique"] = df["ratio_dependance"].gt(2).astype("Int64").where(connu)
    df["niveau_ratio_dependance"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df.loc[connu & df["ratio_dependance"].gt(2), "niveau_ratio_dependance"] = "Critique (> 2)"
    df.loc[connu & df["ratio_dependance"].le(2), "niveau_ratio_dependance"] = "Seuil critique non atteint"

    df["cible_femme_enceinte"] = indicateur_oui_non(df["fem_enc"])
    df["cible_femme_allaitante"] = indicateur_oui_non(df["fem_all"])
    incap = pd.to_numeric(df["adultincap"], errors="coerce")
    df["cible_adulte_incapable"] = incap.gt(0).astype("Int64").where(incap.notna())
    df["cible_handicap_menage_declare"] = indicateur_oui_non(df["hand"])
    df["cible_malnutrition_declaree"] = indicateur_oui_non(df["malnut"])
    return df


def calculer_handicap_washington_group(df: pd.DataFrame) -> pd.DataFrame:
    """Recodage WG-SS : niveau détaillé et indicateur binaire sévère."""
    df = df.copy()
    domaines = ["vis_ss", "hear_ss", "mob_ss", "cog_ss", "sc_ss", "com_ss"]
    codes = {
        "pas du tout": 1,
        "un peu": 2,
        "beaucoup": 3,
        "je ne vois rien du tout": 4,
        "je n entends rien du tout": 4,
        "je suis incapable de le faire": 4,
        "je ne peux pas me concentrer ou me rappeler du tout": 4,
    }
    reponses = df[domaines].apply(lambda colonne: colonne.map(normaliser_texte).map(codes))
    renseigne = reponses.notna().any(axis=1)
    severe = reponses.ge(3).any(axis=1)
    df["score_handicap_wg"] = severe.astype("Int64").where(renseigne)

    niveau = pd.Series(pd.NA, index=df.index, dtype="string")
    niveau.loc[renseigne & severe] = "Sévère (code 3 ou 4)"
    niveau.loc[renseigne & ~severe & reponses.eq(2).any(axis=1)] = "Modéré (code 2)"
    niveau.loc[renseigne & ~severe & reponses.eq(1).all(axis=1)] = "Aucune difficulté (code 1)"
    niveau.loc[renseigne & niveau.isna()] = "Réponses incomplètes"
    df["categorie_handicap_wg"] = niveau
    df["cible_binaire_handicap"] = df["score_handicap_wg"]
    return df


def calculer_score_abri_partiel(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les critères disponibles, le score réduit et le complet sur 7."""
    df = df.copy()
    bareme_statut = {
        "deplace": 1.0,
        "refugie": 1.0,
        "retourne": 1.5,
        "non deplace autochtone famille d accueil": 1.75,
        "non deplace autochtone non famille d accueil": 2.0,
    }
    note_statut = df["status"].map(normaliser_texte).map(bareme_statut)
    note_adaptation_proxy = df["observation_0"].map(normaliser_texte).map({"non": 1.0, "oui": 5.0})
    df["note_abri_statut"] = note_statut
    df["note_abri_adaptation_proxy"] = note_adaptation_proxy
    df["score_abri_critere_a"] = note_statut * note_adaptation_proxy

    bareme_lieu = {
        "famille d accueil": 2.5,
        "centre collectif": 1.5,
        "belle etoile": 1.0,
        "site spontanne": 1.75,
        "occupation gratuite": 2.0,
        "colocataire maison louee": 3.0,
        "locataire": 3.5,
        "propre parcelle": 4.0,
    }
    bareme_environnement = {
        "environnement dangereux promiscuite des abris moins 1 5m": 1.0,
        "environnement dangereux": 1.5,
        "environnement non dangereux promiscuite des abris moins 1 5m": 1.75,
        "environnement non dangereux": 2.5,
    }
    note_lieu = df["lieu_hab"].map(normaliser_texte).map(bareme_lieu)
    note_environnement = df["environ"].map(normaliser_texte).map(bareme_environnement)
    df["note_abri_lieu"] = note_lieu
    df["note_abri_environnement"] = note_environnement
    df["score_abri_critere_c"] = note_lieu * note_environnement

    scores_criteres = {
        "A": "score_abri_critere_a",
        "B": None,
        "C": "score_abri_critere_c",
        "D": None,
        "E": None,
        "F": None,
        "G": None,
    }
    for critere, baremes_variables in BAREMES_ABRI_OPTIONNELS.items():
        if not baremes_variables or not all(colonne in df.columns for colonne in baremes_variables):
            scores_criteres[critere] = None
            continue
        notes = []
        for colonne, bareme in baremes_variables.items():
            bareme_normalise = {
                normaliser_texte(modalite): note for modalite, note in bareme.items()
            }
            notes.append(df[colonne].map(normaliser_texte).map(bareme_normalise))
        notes_df = pd.concat(notes, axis=1)
        complets = notes_df.notna().all(axis=1)
        nom_score = f"score_abri_critere_{critere.lower()}"
        df[nom_score] = notes_df.prod(axis=1).where(complets)
        scores_criteres[critere] = nom_score

    colonnes_presentes = [
        colonne for colonne in scores_criteres.values()
        if colonne is not None and colonne in df.columns
    ]
    matrice_criteres = df[colonnes_presentes].apply(pd.to_numeric, errors="coerce")
    df["nb_criteres_abri_calculables"] = matrice_criteres.notna().sum(axis=1)
    df["score_card_abri_reduit"] = matrice_criteres.mean(axis=1)

    colonnes_officielles = [scores_criteres[critere] for critere in ("A", "B", "C", "D", "E", "F", "G")]
    criteres_tous_calcules = all(
        colonne is not None and colonne in df.columns for colonne in colonnes_officielles
    )
    df["score_card_abri_officiel"] = pd.Series(pd.NA, index=df.index, dtype="Float64")
    if criteres_tous_calcules:
        notes_officielles = df[colonnes_officielles].apply(pd.to_numeric, errors="coerce")
        sept_notes_disponibles = notes_officielles.notna().all(axis=1)
        df.loc[sept_notes_disponibles, "score_card_abri_officiel"] = (
            notes_officielles.sum(axis=1) / 7
        ).loc[sept_notes_disponibles]
    return df


def calculer_hhs(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule le HHS à partir des occurrences et fréquences numériques sur 30 jours."""
    df = df.copy()

    def scorer(occurrence: object, frequence: object) -> float:
        reponse = normaliser_texte(occurrence)
        if reponse == "non":
            return 0.0
        if reponse != "oui":
            return float("nan")
        nombre = pd.to_numeric(pd.Series([frequence]), errors="coerce").iloc[0]
        if pd.isna(nombre) or nombre <= 0:
            return float("nan")
        return 2.0 if nombre > 10 else 1.0

    questions = [
        ("ressources", "repas_r", "score_hhs_q1"),
        ("suffisant", "repas_f", "score_hhs_q2"),
        ("manque", "repas_m", "score_hhs_q3"),
    ]
    for occurrence, frequence, resultat in questions:
        df[resultat] = [scorer(a, b) for a, b in zip(df[occurrence], df[frequence])]
    colonnes = [resultat for _, _, resultat in questions]
    df["score_hhs_total"] = df[colonnes].sum(axis=1, min_count=3)
    connu = df["score_hhs_total"].notna()
    df["categorie_hhs"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df.loc[connu & df["score_hhs_total"].le(1), "categorie_hhs"] = "Peu ou pas de faim (0-1)"
    df.loc[connu & df["score_hhs_total"].between(2, 3), "categorie_hhs"] = "Faim modérée (2-3)"
    df.loc[connu & df["score_hhs_total"].between(4, 6), "categorie_hhs"] = "Faim sévère (4-6)"
    df["cible_hhs_severe"] = df["score_hhs_total"].ge(4).astype("Int64").where(connu)
    return df


def trouver_score_par_intervalle(valeur: object, grille: list[tuple[float, float, float]]) -> float:
    """Retourne le score du premier intervalle (borne basse exclue, haute incluse)."""
    if pd.isna(valeur):
        return float("nan")
    for minimum, maximum, score in grille:
        if valeur > minimum and valeur <= maximum:
            return score
    return float("nan")


def calculer_score_ame_officiel(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les sous-scores AME et leur moyenne à poids égaux."""
    df = df.copy()
    taille = pd.to_numeric(df["taille_menage"], errors="coerce").where(lambda valeurs: valeurs > 0)
    colonnes = []
    for article, bareme in BAREME_AME.items():
        quantite = pd.to_numeric(df[article], errors="coerce")
        mesure = quantite / taille if article in ARTICLES_PONDERES_PAR_TAILLE else quantite
        nom = f"score_{article}"
        df[nom] = mesure.map(lambda valeur: trouver_score_par_intervalle(valeur, bareme))
        colonnes.append(nom)
    df["nb_articles_ame_scores"] = df[colonnes].notna().sum(axis=1)
    df["score_ame_global"] = df[colonnes].mean(axis=1)
    connu = df["score_ame_global"].notna()
    df["categorie_ame_phase"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df.loc[connu & df["score_ame_global"].lt(3), "categorie_ame_phase"] = "Faible ou modérée (< 3)"
    df.loc[connu & df["score_ame_global"].ge(3) & df["score_ame_global"].lt(4), "categorie_ame_phase"] = "Aigüe modérée / urgence (3 à <4)"
    df.loc[connu & df["score_ame_global"].ge(4), "categorie_ame_phase"] = "Aigüe sévère / crise (4 à 5)"
    df["cible_binaire_ame"] = df["score_ame_global"].ge(3).astype("Int64").where(connu)
    return df


def pipeline_vulnerabilite_sociale_decisionnelle(df: pd.DataFrame) -> pd.DataFrame:
    """Combine le proxy d'isolement matrimonial et la décision financière."""
    df = df.copy()
    statut = df["statmtr"].map(normaliser_texte)
    statuts_isoles = {"veuf veuve", "divorce e separe e", "celibataire"}
    statuts_connus = statuts_isoles | {"marie e en couple"}
    statut_connu = statut.isin(statuts_connus)
    isole = statut.isin(statuts_isoles)
    df["score_isolement_matrimonial_proxy"] = isole.astype("Int64").where(statut_connu)

    decision = df["decision"].map(normaliser_texte)
    decisions_connues = {
        "homme chef de menage",
        "femme du chef de menage",
        "les deux ensembles",
        "par une personne tierce du menage",
    }
    decision_connue = decision.isin(decisions_connues)
    exclusion_decisionnelle = decision.eq("par une personne tierce du menage")
    df["cible_exclusion_decisionnelle"] = exclusion_decisionnelle.astype("Int64").where(decision_connue)
    df["score_genre_vulnerabilite_critique"] = (
        (isole & exclusion_decisionnelle).astype("Int64")
        .where(statut_connu & decision_connue)
    )
    return df


def pipeline_indicateurs_economiques(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les ratios économiques sans imputer les montants manquants."""
    df = df.copy()
    for colonne in ("revenu", "montant_dette", "loyer_depl_montant", "loyer_auto_montant"):
        df[colonne] = pd.to_numeric(df[colonne], errors="coerce")
    revenu = df["revenu"].where(df["revenu"].gt(0))
    df["ratio_loyer_revenu"] = df["loyer_depl_montant"] / revenu
    df["ratio_revenu_locatif"] = df["loyer_auto_montant"] / revenu
    df["ratio_dette_revenu"] = df["montant_dette"] / revenu
    df["cible_surcharge_loyer"] = df["ratio_loyer_revenu"].gt(.4).astype("Int64").where(df["ratio_loyer_revenu"].notna())
    df["cible_endettement_critique"] = df["ratio_dette_revenu"].gt(3).astype("Int64").where(df["ratio_dette_revenu"].notna())
    df["cible_dette_positive"] = df["montant_dette"].gt(0).astype("Int64").where(df["montant_dette"].notna())
    df["cible_revenu_locatif"] = df["loyer_auto_montant"].gt(0).astype("Int64").where(df["loyer_auto_montant"].notna())
    return df


def pipeline_wash_severite_complet(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule les alertes WASH et les niveaux définis pour l'enquête."""
    df = df.copy()
    taille = pd.to_numeric(df["taille_menage"], errors="coerce").where(lambda valeurs: valeurs > 0)
    capacites = df[["capacite", "capacites"]].apply(pd.to_numeric, errors="coerce")
    df["stockage_total_litres"] = capacites.sum(axis=1, min_count=1)
    df["stockage_par_habitant"] = df["stockage_total_litres"] / taille

    source = df["eau"].map(normaliser_texte)
    sources_connues = {
        "puits avec pompe", "source amenagee", "source non amenagee non captee",
        "eau de surface riviere ruisseau mare lac", "borne fontaine",
    }
    source_traditionnelle = source.eq("puits traditionnel")
    source_connue = source.isin(sources_connues) | source_traditionnelle
    df["categorie_source_eau"] = pd.Series(pd.NA, index=df.index, dtype="string")
    df.loc[source.isin({"puits avec pompe", "source amenagee", "borne fontaine"}), "categorie_source_eau"] = "Améliorée (selon le questionnaire)"
    df.loc[source.isin({"source non amenagee non captee", "eau de surface riviere ruisseau mare lac"}), "categorie_source_eau"] = "Non améliorée / eau de surface"
    df.loc[source_traditionnelle, "categorie_source_eau"] = "Puits traditionnel - classification séparée"
    sources_non_ameliorees = {
        "source non amenagee non captee",
        "eau de surface riviere ruisseau mare lac",
    }
    a_risque = source.isin(sources_non_ameliorees)
    df["cible_wash_eau_critique"] = a_risque.astype("Int64").where(source_connue & ~source_traditionnelle)
    df["cible_wash_stockage_insuffisant"] = df["stockage_par_habitant"].lt(15).astype("Int64").where(df["stockage_par_habitant"].notna())
    separer = indicateur_oui_non(df["separer"])
    df["cible_wash_absence_separation"] = separer.eq(0).astype("Int64").where(separer.notna())
    colonnes = [
        "cible_wash_eau_critique",
        "cible_wash_stockage_insuffisant",
        "cible_wash_absence_separation",
    ]
    df["score_wash_composantes"] = df[colonnes].sum(axis=1, min_count=3)

    source_non_amelioree = df["cible_wash_eau_critique"].eq(1)
    score_complet = df["score_wash_composantes"].notna()
    df["score_global_wash"] = df["score_wash_composantes"].where(score_complet)
    df.loc[source_non_amelioree, "score_global_wash"] = 3

    niveau = pd.Series(pd.NA, index=df.index, dtype="string")
    niveau_critique = df["score_global_wash"].eq(3)
    niveau_tension = df["score_global_wash"].eq(2)
    niveau_faible = df["score_global_wash"].between(0, 1)
    niveau.loc[niveau_critique] = "Niveau 3 - Critique"
    niveau.loc[niveau_tension] = "Niveau 2 - Tension"
    niveau.loc[niveau_faible] = "Niveau 0-1 - Vulnérabilité faible ou modérée"
    df["niveau_wash"] = niveau
    return df


def pipeline_agro_severite_complet(df: pd.DataFrame) -> pd.DataFrame:
    """Calcule un score de 0 à 5 pour les ménages déclarant pratiquer l'agriculture."""
    df = df.copy()
    pratique = indicateur_oui_non(df["agro"])
    agricole = pratique.eq(1)
    df["cible_pratique_agro"] = pratique

    terre = indicateur_oui_non(df["terre"])
    outils = indicateur_oui_non(df["outims"])
    df["cible_precarite_productive"] = (terre.eq(0) | outils.eq(0)).astype("Int64").where(
        agricole & terre.notna() & outils.notna()
    )

    personnes = pd.to_numeric(df["personne"], errors="coerce")
    df["cible_agro_sans_main_doeuvre"] = personnes.eq(0).astype("Int64").where(
        agricole & personnes.notna()
    )
    eau = indicateur_oui_non(df["eau_point"])
    df["cible_agro_sans_eau"] = eau.eq(0).astype("Int64").where(agricole & eau.notna())
    asso = indicateur_oui_non(df["asso"])
    df["cible_agro_sans_association"] = asso.eq(0).astype("Int64").where(agricole & asso.notna())

    debut = pd.to_datetime(df["date_agro"], errors="coerce")
    enquete = pd.to_datetime(df["date_enquete"], errors="coerce")
    experience = (enquete - debut).dt.days / 365.25
    experience_valide = agricole & experience.ge(0)
    df["experience_agro_annees"] = experience.where(experience_valide)
    df["cible_agro_novice"] = experience.lt(2).astype("Int64").where(experience_valide)

    composantes = [
        "cible_precarite_productive",
        "cible_agro_sans_main_doeuvre",
        "cible_agro_sans_eau",
        "cible_agro_sans_association",
        "cible_agro_novice",
    ]
    df["score_global_agro"] = df[composantes].sum(axis=1, min_count=len(composantes)).where(agricole)
    df["cible_vulnerabilite_agro_severe"] = (
        df["score_global_agro"].ge(2).astype("Int64").where(df["score_global_agro"].notna())
    )
    return df


def calculer_scores(
    df: pd.DataFrame,
    *,
    verifier_colonnes: bool | None = None,
    correspondances: Mapping[str, str] | None = None,
    modalites: Mapping[str, Mapping[str, str]] | None = None,
    profil: dict | str | None = None,
) -> pd.DataFrame:
    """Applique les scores du notebook d'indicateurs et retourne une copie enrichie.

    Les correspondances de variables et modalités sont des décisions métier
    explicites. Un profil fourni active le mode tolérant : les indicateurs sans
    variables suffisantes restent manquants et sont décrits dans les attributs
    ``diagnostic_indicateurs`` du DataFrame retourné.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df doit être un pandas.DataFrame déjà joint au niveau ménage.")
    if isinstance(profil, str):
        profil = charger_profil_questionnaire(profil)
    if profil is not None:
        if not isinstance(profil, dict) or profil.get("version_schema") != VERSION_PROFIL_QUESTIONNAIRE:
            raise ValueError("Le profil fourni a une structure ou une version non prise en charge.")
        if not isinstance(profil.get("empreinte_questionnaire"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", profil["empreinte_questionnaire"]
        ):
            raise ValueError("Le profil fourni doit contenir l'empreinte SHA-256 du XLSForm validé.")
        if not isinstance(profil.get("correspondances"), dict):
            raise ValueError("Le profil doit contenir un objet 'correspondances'.")
        if correspondances is not None or modalites is not None:
            raise ValueError("Fournissez un profil ou des correspondances directes, pas les deux.")
        correspondances_profil = {}
        modalites_profil = {}
        for notion, details in profil.get("correspondances", {}).items():
            if not isinstance(details, dict):
                raise ValueError(f"La correspondance '{notion}' du profil doit être un objet.")
            if not isinstance(details.get("validee"), bool):
                raise ValueError(f"La correspondance '{notion}' doit préciser 'validee' à true ou false.")
            if details.get("validee") is True:
                if not isinstance(details.get("source"), str) or not details["source"].strip():
                    raise ValueError(f"La correspondance validée '{notion}' doit préciser une variable source.")
                correspondances_profil[notion] = details.get("source")
                modalites_notion = details.get("modalites", {})
                if not isinstance(modalites_notion, dict):
                    raise ValueError(f"Les modalités de '{notion}' doivent être un objet.")
                modalites_profil[notion] = modalites_notion
        correspondances = correspondances_profil
        modalites = modalites_profil

    verifier = (profil is None and correspondances is None) if verifier_colonnes is None else verifier_colonnes
    entree_preparee, colonnes_disponibles, modalites_non_reconnues = _preparer_variables_score(
        df, correspondances, modalites
    )
    if verifier:
        manquantes = sorted(_COLONNES_REQUISES - colonnes_disponibles)
        if manquantes:
            raise ValueError(
                "Le DataFrame joint ne contient pas toutes les variables nécessaires "
                "au calcul des scores : " + ", ".join(manquantes)
            )

    resultat = pipeline_demographie_et_handicap(entree_preparee)
    resultat = calculer_handicap_washington_group(resultat)
    resultat = calculer_score_abri_partiel(resultat)
    resultat = calculer_hhs(resultat)
    resultat = calculer_score_ame_officiel(resultat)
    resultat = pipeline_vulnerabilite_sociale_decisionnelle(resultat)
    resultat = pipeline_indicateurs_economiques(resultat)
    resultat = pipeline_wash_severite_complet(resultat)
    resultat = pipeline_agro_severite_complet(resultat)
    diagnostic = {}
    for indicateur, variables in VARIABLES_PAR_INDICATEUR.items():
        manquantes = set(variables - colonnes_disponibles)
        if "taille_menage" in manquantes and set(_COLONNES_COMPOSITION) <= colonnes_disponibles:
            manquantes.remove("taille_menage")
        diagnostic[indicateur] = {
            "etat": "calculable" if not manquantes else "indisponible",
            "variables_manquantes": sorted(manquantes),
        }
    diagnostic.update({
        indicateur: {"etat": "méthode_incomplète", "variables_manquantes": [], "raison": raison}
        for indicateur, raison in INDICATEURS_METHODE_INCOMPLETE.items()
    })
    resultat.attrs["diagnostic_indicateurs"] = diagnostic
    resultat.attrs["modalites_non_reconnues"] = modalites_non_reconnues
    return resultat