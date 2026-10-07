
import os
import sqlite3
import unicodedata
import pandas as pd


def _consentement_accepte(valeur):
  if pd.isna(valeur):
    return False

  texte = unicodedata.normalize("NFKD", str(valeur).strip().lower())
  texte = "".join(caractere for caractere in texte if not unicodedata.combining(caractere))
  if texte in {"oui", "yes", "y", "true", "accepted", "accepte", "d'accord"}:
    return True

  valeur_numerique = pd.to_numeric(texte, errors="coerce")
  return pd.notna(valeur_numerique) and valeur_numerique == 1


def ingest_data(df_clean, db_path="outputs/enquete_ms.db"):
  # S'assurer que le dossier de sortie existe
  os.makedirs(os.path.dirname(db_path), exist_ok=True)

  # Copie du DataFrame pour éviter de modifier l'original en mémoire
  df_clean = df_clean.copy()

  # Si la colonne id_menage n'existe pas, on la génère
  if "id_menage" not in df_clean.columns:
    df_clean = df_clean.reset_index()
    if "index" in df_clean.columns:
      df_clean = df_clean.rename(columns={"index": "id_menage"})
    else:
      df_clean.rename(columns={df_clean.columns[0]: "id_menage"}, inplace=True)
    df_clean["id_menage"] = "MENAGE_" + df_clean.index.astype(str)

  # Connexion à la base SQLite
  conn = sqlite3.connect(db_path)
  cursor = conn.cursor()

  # 1. Création du schéma relationnel 1:1 (id_menage PK partout)
  cursor.executescript("""
        CREATE TABLE IF NOT EXISTS META_ENQUETE (
            id_menage TEXT PRIMARY KEY,
            date_enquete TEXT,
            heure_debut TEXT,
            heure_fin TEXT,
            enqueteur TEXT,
            village TEXT,
            code_jeton INTEGER,
            code_initial_renseigne TEXT,
            presence_maison TEXT,
            volont TEXT,
            acpt_partage TEXT,
            remarques_enquete TEXT,
            duree_minutes REAL
        );

        CREATE TABLE IF NOT EXISTS MENAGE (
            id_menage TEXT PRIMARY KEY,
            repondant TEXT,
            age INTEGER,
            sexe TEXT,
            poss_carte TEXT,
            typedepiece TEXT,
            statmtr TEXT,
            decision TEXT,
            status TEXT,
            FOREIGN KEY (id_menage) REFERENCES META_ENQUETE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS STATUT_MENAGE (
            id_menage TEXT PRIMARY KEY,
            herber TEXT,
            environ TEXT,
            date_deplacement TEXT,
            date_retour TEXT,
            loyer_depl TEXT,
            loyer_depl_montant REAL,
            loyer_auto TEXT,
            loyer_auto_montant REAL,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS COMPOSITION_MENAGE (
            id_menage TEXT PRIMARY KEY,
            h_0_5 INTEGER, h_6_24 INTEGER, h_25_59 INTEGER, h_5_14 INTEGER, h_15_17 INTEGER, 
            h_18_49 INTEGER, h_50_59 INTEGER, h_plus60 INTEGER, 
            f_0_5 INTEGER, f_6_24 INTEGER, f_25_59 INTEGER, f_5_14 INTEGER, f_15_17 INTEGER, 
            f_18_49 INTEGER, f_50_59 INTEGER, f_plus60 INTEGER, 
            fem_enc TEXT, fem_all TEXT,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS VULNERABILITE_SANTE (
            id_menage TEXT PRIMARY KEY,
            vis_ss TEXT, hear_ss TEXT, mob_ss TEXT, cog_ss TEXT, sc_ss TEXT, com_ss TEXT,
            observation_0 TEXT, adultincap INTEGER, hand TEXT, malnut TEXT, 
            malnut_charge TEXT, malnut_charge_non TEXT,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS ECONOMIE_REVENU (
            id_menage TEXT PRIMARY KEY,
            source_reve TEXT,
            revenu INTEGER,
            dette TEXT,
            montant_dette INTEGER,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS SECURITE_ALIMENTAIRE (
            id_menage TEXT PRIMARY KEY,
            repas_a INTEGER, repas_e INTEGER, ressources TEXT, repas_r INTEGER, 
            suffisant TEXT, repas_f INTEGER, manque TEXT, repas_m INTEGER,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS BIENS_AME (
            id_menage TEXT PRIMARY KEY,
            nb_bidon INTEGER, nb_cass INTEGER, nb_bas INTEGER, nb_outil INTEGER, 
            nb_couch INTEGER, nb_couv INTEGER, nb_habit_femme INTEGER, nb_habit_e INTEGER, 
            nb_cale INTEGER, nb_jarre INTEGER, nb_seau INTEGER, nb_pot INTEGER,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS WASH_EAU (
            id_menage TEXT PRIMARY KEY,
            type_puisage TEXT,
            capacite INTEGER,
            type_stockage TEXT,
            capacites INTEGER,
            separer TEXT,
            raison TEXT,
            eau TEXT,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS AGRICULTURE (
            id_menage TEXT PRIMARY KEY,
            agro TEXT, date_agro TEXT, culture TEXT, marai TEXT, date_marai TEXT, 
            vivri TEXT, date_vivri TEXT, membre TEXT, personne INTEGER, age_agro INTEGER, 
            eau_point TEXT, type_eau TEXT, terre TEXT, outims TEXT, asso TEXT,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );

        CREATE TABLE IF NOT EXISTS PROTECTION (
            id_menage TEXT PRIMARY KEY,
            depl_bnf TEXT,
            depl_dist REAL,
            diff_deplac TEXT,
            type_diff TEXT,
            FOREIGN KEY (id_menage) REFERENCES MENAGE(id_menage)
        );
    """)

  colonnes_meta = {
      row[1] for row in cursor.execute("PRAGMA table_info(META_ENQUETE)")
  }
  if "code_initial_renseigne" not in colonnes_meta:
    cursor.execute(
        "ALTER TABLE META_ENQUETE ADD COLUMN code_initial_renseigne TEXT"
    )

  # 2. Nettoyage préventif par lots (pour éviter l'erreur "too many SQL variables")
  ids_a_inserer = df_clean["id_menage"].dropna().tolist()
  tables_toutes = [
      "META_ENQUETE",
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
  ]

  chunk_size = 500
  for i in range(0, len(ids_a_inserer), chunk_size):
    chunk = ids_a_inserer[i : i + chunk_size]
    placeholders = ",".join(["?"] * len(chunk))
    for table in tables_toutes:
      cursor.execute(
          f"DELETE FROM {table} WHERE id_menage IN ({placeholders})", chunk
      )
  conn.commit()

  # 3. Insertion dans META_ENQUETE (Tous les ménages : consentants et non-consentants)
  cols_meta = [
      c
      for c in [
          "id_menage",
          "date_enquete",
          "heure_debut",
          "heure_fin",
          "enqueteur",
          "village",
          "code_jeton",
          "code_initial_renseigne",
          "presence_maison",
          "volont",
          "acpt_partage",
          "remarques_enquete",
          "duree_minutes",
      ]
      if c in df_clean.columns
  ]
  df_clean[cols_meta].to_sql("META_ENQUETE", conn, if_exists="append", index=False)

  # 4. Filtrage strict des consentants pour la table MENAGE et les satellites
  if "volont" in df_clean.columns:
    df_consentants = df_clean[
        df_clean["volont"].map(_consentement_accepte)
    ].copy()
  else:
    df_consentants = df_clean.copy()

  # 5. Insertion dans MENAGE (Uniquement consentants)
  cols_menage = [
      c
      for c in [
          "id_menage",
          "repondant",
          "age",
          "sexe",
          "poss_carte",
          "typedepiece",
          "statmtr",
          "decision",
          "status",
      ]
      if c in df_consentants.columns
  ]
  df_consentants[cols_menage].to_sql("MENAGE", conn, if_exists="append", index=False)

  # 6. Fonction utilitaire pour insérer les tables satellites (id_menage comme PK)
  def insert_satellite(table_name, original_cols):
    available_cols = [c for c in original_cols if c in df_consentants.columns]
    if "id_menage" in available_cols:
      sub_df = df_consentants[available_cols].copy()
      sub_df.to_sql(table_name, conn, if_exists="append", index=False)

  # Remplissage des 9 tables satellites
  insert_satellite(
      "STATUT_MENAGE",
      [
          "id_menage",
          "herber",
          "environ",
          "date_deplacement",
          "date_retour",
          "loyer_depl",
          "loyer_depl_montant",
          "loyer_auto",
          "loyer_auto_montant",
      ],
  )
  insert_satellite(
      "COMPOSITION_MENAGE",
      [
          "id_menage",
          "h_0_5",
          "h_6_24",
          "h_25_59",
          "h_5_14",
          "h_15_17",
          "h_18_49",
          "h_50_59",
          "h_plus60",
          "f_0_5",
          "f_6_24",
          "f_25_59",
          "f_5_14",
          "f_15_17",
          "f_18_49",
          "f_50_59",
          "f_plus60",
          "fem_enc",
          "fem_all",
      ],
  )
  insert_satellite(
      "VULNERABILITE_SANTE",
      [
          "id_menage",
          "vis_ss",
          "hear_ss",
          "mob_ss",
          "cog_ss",
          "sc_ss",
          "com_ss",
          "observation_0",
          "adultincap",
          "hand",
          "malnut",
          "malnut_charge",
          "malnut_charge_non",
      ],
  )
  insert_satellite(
      "ECONOMIE_REVENU",
      ["id_menage", "source_reve", "revenu", "dette", "montant_dette"],
  )
  insert_satellite(
      "SECURITE_ALIMENTAIRE",
      [
          "id_menage",
          "repas_a",
          "repas_e",
          "ressources",
          "repas_r",
          "suffisant",
          "repas_f",
          "manque",
          "repas_m",
      ],
  )
  insert_satellite(
      "BIENS_AME",
      [
          "id_menage",
          "nb_bidon",
          "nb_cass",
          "nb_bas",
          "nb_outil",
          "nb_couch",
          "nb_couv",
          "nb_habit_femme",
          "nb_habit_e",
          "nb_cale",
          "nb_jarre",
          "nb_seau",
          "nb_pot",
      ],
  )
  insert_satellite(
      "WASH_EAU",
      [
          "id_menage",
          "type_puisage",
          "capacite",
          "type_stockage",
          "capacites",
          "separer",
          "raison",
          "eau",
      ],
  )
  insert_satellite(
      "AGRICULTURE",
      [
          "id_menage",
          "agro",
          "date_agro",
          "culture",
          "marai",
          "date_marai",
          "vivri",
          "date_vivri",
          "membre",
          "personne",
          "age_agro",
          "eau_point",
          "type_eau",
          "terre",
          "outims",
          "asso",
      ],
  )
  insert_satellite(
      "PROTECTION",
      ["id_menage", "depl_bnf", "depl_dist", "diff_deplac", "type_diff"],
  )

  conn.commit()
  lignes_par_table = {
      table: (
          len(df_clean)
          if table == "META_ENQUETE"
          else len(df_consentants)
      )
      for table in tables_toutes
  }
  conn.close()
  print(f"Ingestion réussie ! Base de données mise à jour dans : {db_path}")
  return {
      "lignes_meta": len(df_clean),
      "lignes_consentantes": len(df_consentants),
      "lignes_par_table": lignes_par_table,
  }


if __name__ == "__main__":
  nom_csv = "donnees_nettoyees.csv"
  chemin_csv = os.path.join("outputs", nom_csv)

  print(f"Chargement du fichier propre depuis : {chemin_csv}")
  df_clean = pd.read_csv(chemin_csv)

  # Lancement de l'ingestion globale
  ingest_data(df_clean, "outputs/enquete_ms.db")