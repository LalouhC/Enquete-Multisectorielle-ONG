```mermaid
erDiagram
    META_ENQUETE {
        string id_menage PK
        date date_enquete
        date heure_debut
        date heure_fin
        string enqueteur
        string village
        int code_jeton
        string presence_maison
        string volont
        string acpt_partage
        string remarques_enquete
        float duree_minutes
    }

    MENAGE {
        string id_menage PK, FK
        string repondant
        int age
        string sexe
        string poss_carte
        string typedepiece
        string statmtr
        string decision
        string status
    }

    STATUT_MENAGE {
        string id_statut PK
        string id_menage FK
        string herber
        string environ
        date date_deplacement
        date date_retour
        string loyer_depl
        float loyer_depl_montant
        string loyer_auto
        float loyer_auto_montant
    }

    COMPOSITION_MENAGE {
        string id_comp PK
        string id_menage FK
        int h_0_5
        int h_6_24
        int h_25_59
        int h_5_14
        int h_15_17
        int h_18_49
        int h_50_59
        int h_plus60
        int f_0_5
        int f_6_24
        int f_25_59
        int f_5_14
        int f_15_17
        int f_18_49
        int f_50_59
        int f_plus60
        string fem_enc
        string fem_all
    }

    VULNERABILITE_SANTE {
        string id_sante PK
        string id_menage FK
        string vis_ss
        string hear_ss
        string mob_ss
        string cog_ss
        string sc_ss
        string com_ss
        string observation_0
        int adultincap
        string hand
        string malnut
        string malnut_charge
        string malnut_charge_non
    }

    ECONOMIE_REVENU {
        string id_eco PK
        string id_menage FK
        string source_reve
        int revenu
        string dette
        int montant_dette
    }

    SECURITE_ALIMENTAIRE {
        string id_alim PK
        string id_menage FK
        int repas_a
        int repas_e
        string ressources
        int repas_r
        string suffisant
        int repas_f
        string manque
        int repas_m
    }

    BIENS_AME {
        string id_ame PK
        string id_menage FK
        int nb_bidon
        int nb_cass
        int nb_bas
        int nb_outil
        int nb_couch
        int nb_couv
        int nb_habit_femme
        int nb_habit_e
        int nb_cale
        int nb_jarre
        int nb_seau
        int nb_pot
    }

    WASH_EAU {
        string id_wash PK
        string id_menage FK
        string type_puisage
        int capacite
        string type_stockage
        int capacites
        string separer
        string raison
        string eau
    }

    AGRICULTURE {
        string id_agro PK
        string id_menage FK
        string agro
        date date_agro
        string culture
        string marai
        date date_marai
        string vivri
        date date_vivri
        string membre
        int personne
        int age_agro
        string eau_point
        string type_eau
        string terre
        string outims
        string asso
    }

    PROTECTION {
        string id_protec PK
        string id_menage FK
        string depl_bnf
        float depl_dist
        string diff_deplac
        string type_diff
    }

    META_ENQUETE ||--|| MENAGE : "concerne"
    MENAGE ||--o{ STATUT_MENAGE : "precise"
    MENAGE ||--o{ COMPOSITION_MENAGE : "compose"
    MENAGE ||--o{ VULNERABILITE_SANTE : "declare"
    MENAGE ||--o{ ECONOMIE_REVENU : "possede"
    MENAGE ||--o{ SECURITE_ALIMENTAIRE : "rapporte"
    MENAGE ||--o{ BIENS_AME : "detient"
    MENAGE ||--o{ WASH_EAU : "utilise"
    MENAGE ||--o{ AGRICULTURE : "pratique"
    MENAGE ||--o{ PROTECTION : "affronte"