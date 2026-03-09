"""
acquittify_taxonomy.py

Federal Criminal Defense (FCD) Taxonomy for Acquittify.

This module intentionally contains primarily data structures (minimal helpers only).

Exports (backward compatible):
- TAXONOMY: list[str] -- flattened FCD taxonomy codes (e.g., "FCD.ISS.DISCOVERY.BRADY")
- TAXONOMY_SET: set[str] -- membership checks for the flattened codes
- HIERARCHY: dict[str, dict] -- nested hierarchy (source of truth)
- normalize_area: callable -- small helper for comparisons

Additional exports (new, non-breaking):
- ROUTING_TAXONOMY: list[str] -- controlled vocabulary for router labels
- ROUTING_TAXONOMY_SET: set[str] -- membership checks for router labels
"""

from __future__ import annotations

# ---------------------------
# 1) Canonical hierarchical taxonomy (source of truth)
# ---------------------------

TAXONOMY_HIERARCHY = {
    "AUTH": {
        "CONST": {
            "1A": "First Amendment (speech, association)",
            "4A": "Fourth Amendment (search/seizure)",
            "5A": "Fifth Amendment (self-incrimination, due process, double jeopardy)",
            "6A": "Sixth Amendment (counsel, confrontation, jury, speedy trial)",
            "8A": "Eighth Amendment (excessive bail, cruel/unusual punishment)",
            "DP": "Due Process (5A/14A concepts in federal cases)",
            "EP": "Equal Protection concepts (as applied via federal doctrine)",
        },
        "STAT": {
            "USC": "United States Code",
            "USC.<title>.<section>": "Pattern: e.g., FCD.AUTH.STAT.USC.18.922",
            "USCAPP": "U.S.C. Appendix (e.g., CIPA)",
            "PUBLAW": "Public Laws / legislative history",
        },
        "RULE": {
            "FRCP": "Federal Rules of Criminal Procedure",
            "FRE": "Federal Rules of Evidence",
            "FRAP": "Federal Rules of Appellate Procedure",
            "LOCAL": "Local rules (district/circuit)",
        },
        "GUIDELINES": {
            "USSG": "U.S. Sentencing Guidelines (Guidelines + commentary)",
            "USSG.<section>": "Pattern: e.g., FCD.AUTH.USSG.2D1.1",
        },
        "REG": {
            "CFR": "Code of Federal Regulations",
            "BOP": "BOP regulations / program statements / policies",
        },
        "POLICY": {
            "DOJ.JM": "DOJ Justice Manual",
            "AGENCY": "Investigative agency manuals (FBI, DEA, ATF, etc.)",
        },
        "CASELAW": {
            "SCOTUS": "U.S. Supreme Court",
            "CIRCUIT": "U.S. Courts of Appeals",
            "DISTRICT": "U.S. District Courts",
        },
        "SECONDARY": {
            "TREATISE": "Treatises / practice guides",
            "TRAINING": "Training materials (benchbooks, defender manuals)",
            "SCHOLARSHIP": "Law review / empirical studies",
        },
    },
    "STG": {
        "INTAKE": "Client intake, retention/appointment, early case strategy",
        "INVESTIGATION": "Investigation / pre-charge representation",
        "CHARGING": "Complaint, information, indictment decision-making",
        "PRETRIAL": {
            "INITIAL_APPEARANCE": "Initial appearance",
            "COUNSEL": "Appointment of counsel / pro se",
            "DETENTION_RELEASE": "Release/detention pending trial",
            "TRANSFER_REMOVAL": "Offense in another district / removal",
            "WAIVER_INDICTMENT": "Waiver of indictment",
            "ARRAIGNMENT_PLEA": "Arraignment and plea",
            "CONFLICTS": "Joint representation / conflicts",
            "JURY_WAIVER": "Waiver of jury trial",
            "SPEEDY_TRIAL": "Speedy Trial Act",
            "JUVENILE_DELINQUENCY": "Delinquency proceedings",
            "COMPETENCY": "Mental competency issues pretrial",
            "MAGISTRATE": "Referrals to magistrate judges",
        },
        "GRAND_JURY": "Grand jury practice & litigation",
        "DISCOVERY": "Discovery & disclosure litigation",
        "MOTIONS": "Pretrial motions practice (all types)",
        "PLEA": "Plea negotiations and plea agreements",
        "TRIAL": {
            "JURY_SELECTION": "Jury selection / voir dire",
            "EVIDENCE": "Trial evidence issues",
            "JURY_INSTRUCTIONS": "Jury instructions",
            "VERDICT": "Verdict",
        },
        "POST_TRIAL": "Trial and post-trial motions",
        "SENTENCING": "Sentencing proceedings",
        "APPEAL": "Direct appeals",
        "POSTCONVICTION": "§2255 / habeas / other collateral relief",
        "CORRECTIONS": "BOP / incarceration issues",
        "SUPERVISION": "Probation / supervised release & revocation",
        "CAPITAL": "Federal death penalty procedures",
    },
    "ISS": {
        "JURISDICTION_VENUE": {
            "SUBJECT_MATTER": "Federal jurisdiction",
            "TERRITORIAL": "Territorial / extraterritorial reach",
            "VENUE": "Venue challenges",
            "TRANSFER": "Transfer of venue",
        },
        "COUNSEL_ETHICS": {
            "APPOINTMENT": "Appointment / CJA / retained counsel",
            "PRO_SE": "Self-representation",
            "CONFLICTS": "Conflicts / joint representation",
            "INEFFECTIVE_ASSISTANCE": "Strickland / IAC",
        },
        "BAIL": {
            "BRA_RELEASE": "Release (personal recognizance/conditions)",
            "BRA_DETENTION": "Detention",
            "HEARINGS_BURDENS": "Detention hearing procedure/burdens",
            "APPEALS": "Review/appeal of release/detention orders",
            "POSTCONVICTION_RELEASE": "Release pending sentencing/appeal",
        },
        "GRAND_JURY": {
            "SUBPOENAS": "Subpoenas / motions to quash",
            "PRIVILEGES": "Privileges (5A, 1A, etc.)",
            "CONTEMPT": "Contempt procedures",
            "IMMUNITY": "Statutory immunity (18 USC 6002-6003)",
            "MISCONDUCT": "Prosecutorial abuse / grand jury error",
            "EXCULPATORY_EVIDENCE": "Policies/arguments re exculpatory evidence",
        },
        "CHARGING": {
            "ELEMENTS_MENS_REA": "Elements, mens rea, proof",
            "MULTIPLICITY_DUPLICITY": "Multiplicity/duplicity",
            "STATUTE_LIMITATIONS": "Statute of limitations",
            "SELECTIVE_VINDICTIVE": "Selective/vindictive prosecution",
            "CONSTRUCTIVE_AMENDMENT": "Constructive amendment / variance",
        },
        "ASSET_FORFEITURE": {
            "SEIZURE_RESTRAINT": "Seizure warrants, restraining orders, asset freezes",
            "CRIMINAL_FORFEITURE": "Criminal forfeiture (21 USC 853, Rule 32.2)",
            "CIVIL_FORFEITURE": "Civil forfeiture litigation (18 USC 983, 19 USC 1600s)",
            "ADMINISTRATIVE": "Administrative forfeiture procedures",
            "ANCILLARY": "Ancillary proceedings / third-party claims",
            "SUBSTITUTE_ASSETS": "Substitute assets and relation-back issues",
            "INTERNATIONAL": "International forfeiture / MLAT / cross-border restraint",
            "EQUITABLE_SHARING": "Equitable sharing and adoption policies",
            "FEES_COSTS": "Attorney fees, costs, and litigation expenses",
            "DISPOSITION": "Use, disposition, remission/mitigation of forfeited assets",
        },
        "DISCOVERY": {
            "FRCP16": "Rule 16",
            "BRADY": "Brady (exculpatory evidence)",
            "GIGLIO": "Giglio (impeachment)",
            "JENCKS": "Jencks Act / Rule 26.2",
            "PROTECTIVE_ORDERS": "Protective orders",
            "SUBPOENAS_RULE17": "Rule 17 subpoenas",
            "EXPERTS_FORENSICS": "Forensic discovery, lab reports, expert disclosures",
            "ELECTRONIC_COMMS": "Electronic communications / digital discovery",
            "CIPA_CLASSIFIED": "Classified discovery & CIPA",
            "FOIA": "FOIA as defense tool",
        },
        "SUPPRESSION": {
            "4A_SEARCH_SEIZURE": "Search & seizure suppression",
            "WARRANTS": "Warrants / probable cause",
            "EXCEPTIONS": "Exceptions (consent, exigency, etc.)",
            "BORDER": "Border search doctrine",
            "ELECTRONIC_SURVEILLANCE": "Wiretaps, Title III, tracking, CSLI, etc.",
            "STATEMENTS": "Suppression of statements (Miranda/voluntariness)",
            "IDENTIFICATION": "Suppression of identifications",
            "FRUIT_POISONOUS_TREE": "Derivative evidence doctrine",
        },
        "MOTIONS": {
            "DISMISS": "Motions to dismiss (legal insufficiency)",
            "BILL_OF_PARTICULARS": "Bill of particulars",
            "SEVERANCE_JOINDER": "Severance/joinder",
            "LIMINE": "Motions in limine",
            "COMPEL_DISCOVERY": "Motions to compel",
            "SANCTIONS": "Sanctions for violations",
        },
        "TRIAL_RIGHTS": {
            "SPEEDY_TRIAL": "Speedy trial (constitutional/statutory)",
            "CONFRONTATION": "Confrontation Clause",
            "COMPULSORY_PROCESS": "Compulsory process",
            "PUBLIC_TRIAL": "Public trial / closures",
            "DOUBLE_JEOPARDY": "Double jeopardy",
            "DUE_PROCESS": "Fair trial / due process",
        },
        "JURY": {
            "VOIR_DIRE": "Voir dire practice",
            "BATSON": "Batson challenges",
            "ANONYMOUS_JURY": "Anonymous juries",
            "INSTRUCTIONS": "Jury instruction litigation",
            "MISTRIAL": "Mistrial",
        },
        "EVIDENCE": {
            "HEARSAY": "Hearsay rules & exceptions",
            "PRIVILEGES": "Privileges (AC, spousal, etc.)",
            "EXPERTS_DAUBERT": "Daubert / expert admissibility",
            "IMPEACHMENT": "Impeachment, bias, prior acts",
            "AUTHENTICATION": "Authentication, chain of custody",
        },
        "DEFENSES": {
            "MENTAL_HEALTH": "Competency/insanity/mental condition defenses",
            "ENTRAPMENT": "Entrapment",
            "DURESS_NECESSITY": "Duress/necessity",
            "SELF_DEFENSE": "Self-defense/justification",
            "PUBLIC_AUTHORITY": "Public authority / entrapment by estoppel",
            "WITHDRAWAL_RENUNCIATION": "Withdrawal defenses",
        },
        "PROSECUTORIAL_MISCONDUCT": {
            "BRADY_GIGLIO": "Disclosure misconduct",
            "IMPROPER_ARGUMENT": "Improper argument",
            "GRAND_JURY_ABUSE": "Grand jury abuse",
            "VINDICTIVE_SELECTIVE": "Vindictive/selective prosecution",
        },
        "SENTENCING": {
            "GUIDELINES": "Guideline calculation",
            "3553A": "3553(a) factors / variance",
            "MANDATORY_MIN": "Mandatory minimums / enhancements",
            "DEPARTURES": "Departures",
            "RESTITUTION": "Restitution",
            "FINES_FEES": "Fines/fees/special assessments",
            "FORFEITURE": "Criminal forfeiture",
        },
        "POSTCONVICTION": {
            "DIRECT_APPEAL": "Direct appeal issues",
            "2255": "28 USC §2255",
            "2241": "28 USC §2241",
            "SENTENCE_REDUCTION": "3582(c), retroactivity",
        },
        "CORRECTIONS_SUPERVISION": {
            "BOP": "BOP issues (designation, credits, programs)",
            "SUPERVISED_RELEASE": "Supervised release conditions",
            "REVOCATION": "Revocation proceedings",
        },
    },
    "OFF": {
        "USC.<title>.<section>": "Pattern: attach exact statute(s) when detected",
        "INCHOATE_LIABILITY": {
            "AID_ABET": "Aiding and abetting",
            "CONSPIRACY": "Conspiracy",
            "ATTEMPT": "Attempt",
            "ACCESSORY": "Accessory after the fact",
            "MISPRISION": "Misprision of felony",
            "ESCAPE_FTA": "Escape / failure to appear",
        },
        "FRAUD_FINANCIAL": {
            "MAIL_WIRE": "Mail/wire fraud",
            "BANK": "Bank fraud",
            "SECURITIES": "Securities fraud",
            "HEALTHCARE": "Health care fraud",
            "IDENTITY": "Identity theft & fraud",
            "TAX": "Tax crimes",
            "PROGRAM_FRAUD": "Program fraud/bribery (e.g., 18 USC 666)",
            "FCPA_FEPA": "Foreign bribery / FCPA / FEPA",
            "MONEY_LAUNDERING": "Money laundering / structuring",
        },
        "PROPERTY": {
            "THEFT": "Theft, stolen property",
            "VEHICLE_AIRCRAFT": "Motor vehicle/aircraft theft",
            "ARSON": "Arson (if not tagged in firearms/public safety)",
            "BURGLARY_ROBBERY": "If charged as property/robbery",
        },
        "ROBBERY_EXTORTION": {
            "ROBBERY": "Robbery",
            "HOBBS": "Hobbs Act / extortion",
            "CARJACKING": "Carjacking",
        },
        "VIOLENT_PERSON": {
            "HOMICIDE": "Homicide/murder/manslaughter",
            "ASSAULT": "Assault",
            "KIDNAPPING": "Kidnapping/unlawful restraint",
            "THREATS_STALKING": "Threats/stalking",
            "DOMESTIC_VIOLENCE": "Domestic violence-related federal crimes",
        },
        "DRUGS": {
            "TRAFFICKING": "Distribution/trafficking",
            "CONSPIRACY": "Drug conspiracies",
            "IMPORT_EXPORT": "Import/export",
            "CCE": "Continuing criminal enterprise",
            "PARAPHERNALIA": "Paraphernalia/precursors",
        },
        "RACKETEERING_ENTERPRISE": {
            "RICO": "RICO",
            "GANGS": "Gang/enterprise cases",
        },
        "SEX": {
            "TRAFFICKING": "Sex trafficking",
            "EXPLOITATION": "Child exploitation",
            "CHILD_PORN": "Child pornography offenses",
            "PROSTITUTION": "Commercial sex acts",
        },
        "ADMIN_JUSTICE": {
            "OBSTRUCTION": "Obstruction",
            "PERJURY_FALSE_STATEMENTS": "Perjury/false statements",
            "WITNESS_TAMPERING": "Witness tampering/retaliation",
            "CONTEMPT": "Contempt",
        },
        "FIREARMS_PUBLIC_SAFETY": {
            "FIREARMS_POSSESSION": "Firearms possession",
            "FIREARMS_TRAFFICKING": "Firearms trafficking",
            "924C": "Use/carry in relation to crimes",
            "EXPLOSIVES": "Explosives",
            "ARSON": "Arson",
        },
        "IMMIGRATION_BORDER": {
            "ENTRY_REENTRY": "Illegal entry/reentry",
            "SMUGGLING": "Alien smuggling",
            "BORDER_CROSSING": "Border crossing offenses",
            "DOCUMENT_FRAUD": "Passport/visa/document fraud",
        },
        "CYBER_IP": {
            "CFAA": "Computer Fraud and Abuse Act / intrusions",
            "RANSOMWARE_EXTORTION": "Ransomware/digital extortion",
            "DIGITAL_ASSETS": "Crypto/digital asset crime",
            "IP": "Intellectual property crimes",
        },
        "NATSEC": {
            "TERRORISM": "Terrorism",
            "ESPIONAGE": "Espionage",
            "EXPORT_CONTROLS": "Export controls/sanctions",
            "CYBER": "National security cyber cases",
        },
        "ENVIRONMENT": "Environmental crimes",
        "CIVIL_RIGHTS": "Civil rights / hate crimes",
        "ANTITRUST": "Antitrust crimes",
        "ELECTION": "Election / campaign finance crimes",
        "MISC": "Catch-all (aviation piracy, rare Title 18 offenses, etc.)",
    },
    "CTX": {
        "NONCITIZEN": "Non-citizen defendants & immigration consequences",
        "INDIAN_COUNTRY": "Indian Country jurisdiction/charges",
        "JUVENILE": "Juvenile delinquency proceedings",
        "CAPITAL": "Federal death penalty",
        "NATSEC_CLASSIFIED": "National security / classified information / CIPA",
        "CORPORATE": "Corporate defendants",
        "MULTIDEFENDANT": "Multi-defendant cases",
        "EXTRADITION_MLAT": "Extradition / MLAT / international process",
        "MENTAL_HEALTH": "Mental health/competency/insanity context",
        "VICTIMS_CVRA": "Crime Victims’ Rights Act issues",
    },
    "GOV": {
        "DISCOVERY": {
            "BRADY_GIGLIO_POLICY": "DOJ disclosure policy (Brady/Giglio)",
            "GIGLIO_LAW_ENFORCEMENT": "Giglio policy re law enforcement witnesses",
            "FORENSICS_EXPERTS": "Forensic evidence/expert discovery guidance",
        },
        "GRAND_JURY": {
            "EXCULPATORY_DISCLOSURE_POLICY": "DOJ policy re exculpatory evidence to GJ",
        },
        "PLEAS": {
            "FRCP11": "DOJ plea policies linked to Rule 11",
            "NC_ALFORD": "Nolo contendere / Alford approvals",
            "APPEAL_WAIVERS": "Appeal waivers in plea agreements",
            "RESTITUTION_FORFEITURE": "Restitution/forfeiture provisions",
        },
        "PROSECUTION_PRINCIPLES": {
            "PROBABLE_CAUSE": "Probable cause requirement",
            "SUBSTANTIAL_FED_INTEREST": "Substantial federal interest",
            "ALTERNATIVES": "Non-criminal alternatives",
            "MANDATORY_MINIMUMS": "Charging mandatory minimums/enhancements",
            "COOP_NPA_DPA": "Cooperation, NPAs, DPAs",
            "SENTENCING_POSITIONS": "Gov role at sentencing",
        },
        "OFFENSE_SPECIFIC": {
            "PROGRAM_FRAUD_666": "Policy for 18 USC 666",
            "FCPA_FEPA": "Policy for FCPA/FEPA",
            "CYBER_IP": "Cyber/IP enforcement programs",
            "IMMIGRATION": "Immigration enforcement guidance",
        },
    },
    "PRAC": {
        "INVESTIGATION": "Defense investigation strategy",
        "EXPERTS": "Experts (forensic, mental health, digital, etc.)",
        "MITIGATION": "Mitigation development & sentencing narratives",
        "MOTION_WRITING": "Templates, exemplars, motion practice craft",
        "TRIAL_ADVOCACY": "Trial skills, outlines, checklists",
        "APPELLATE": "Appellate strategy and writing",
    },
}

# Alias for code that expects TAXONOMY_HIERARCHY by name.
HIERARCHY = TAXONOMY_HIERARCHY


# ---------------------------
# 2) Flattened code list (FCD.*) for classification/membership checks
# ---------------------------

def flatten_taxonomy(hierarchy: dict, prefix: str = "FCD") -> list[str]:
    codes: list[str] = []
    for key, value in hierarchy.items():
        code = f"{prefix}.{key}"
        if isinstance(value, dict):
            codes.extend(flatten_taxonomy(value, code))
        else:
            codes.append(code)
    return codes


# Canonical flattened taxonomy codes
TAXONOMY = flatten_taxonomy(TAXONOMY_HIERARCHY)
TAXONOMY_SET = set(TAXONOMY)


# ---------------------------
# 3) Router controlled vocabulary (kept separate so it doesn't overwrite TAXONOMY codes)
# ---------------------------

ROUTING_TAXONOMY = [
    "Fourth Amendment / Suppression",
    "Charging / Elements",
    "Mens Rea",
    "Discovery / Brady / Jencks",
    "Trial Procedure",
    "Sentencing",
    "Appeals / Standards of Review",
    "Jurisdiction / Venue",
    "General Federal Criminal Law",
]

ROUTING_TAXONOMY_SET = set(ROUTING_TAXONOMY)


# ---------------------------
# 4) Small helper
# ---------------------------

def normalize_area(name: str) -> str:
    """Normalize a taxonomy area name for comparisons."""
    if not name:
        return ""
    return name.strip()


__all__ = [
    "TAXONOMY_HIERARCHY",
    "HIERARCHY",
    "TAXONOMY",
    "TAXONOMY_SET",
    "ROUTING_TAXONOMY",
    "ROUTING_TAXONOMY_SET",
    "normalize_area",
]
