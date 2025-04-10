# utils/ocr_parser.py

from re import sub, match, fullmatch

from rapidfuzz.fuzz import ratio

# Constantes et patterns
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]
IMMATRICULATION_PATTERN = r"^[A-Z]{2}[-.\s]?\d{2,4}[-.\s]?[A-Z]{1,3}$"  # Exemple : AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"  # Exemple : 13/09/2024
NUM_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.(?:I)?[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|(?:I)?[A-Z]+(?:\s[A-Z]+)+)$"
TITULAIRE_PREFIX_PATTERN = r'^M(?::|\s)?(?:\.?\s?I)?\s?'
CYLINDREE_PATTERN = r"^\d{2,7}\s*cm3$"


def fuzzy_match(word: str, target: str, threshold=70):
    """
    Compare deux chaînes en minuscule via rapidfuzz et renvoie True si le score >= threshold.
    """
    score = ratio(word.lower(), target.lower())
    return score >= threshold


def detect_document_type(extracted_text):
    """
    Détecte si l'image correspond plutôt à un recto ou un verso,
    en comptant les mots-clés ou regex attendus.
    Renvoie 'recto', 'verso' ou None si non reconnu.
    """
    recto_keywords = ["immatriculation", "titulaire", "adresse"]
    verso_keywords = ["energie", "puissance", "vin", "marque", "cylindrée"]

    recto_score = 0
    verso_score = 0

    for word in extracted_text:
        wlower = word.lower()
        if any(fuzzy_match(wlower, kw, 65) for kw in recto_keywords):
            recto_score += 1
        if match(IMMATRICULATION_PATTERN, word):
            recto_score += 1
        if any(fuzzy_match(wlower, kw, 65) for kw in verso_keywords):
            verso_score += 1
        if match(r"^[A-Z0-9]{17}$", word.upper()):
            verso_score += 1

    if recto_score > verso_score:
        return "recto"
    elif verso_score > recto_score:
        return "verso"
    else:
        return None


def parse_cgr_recto_text(extracted_text):
    """
    Analyse la liste de mots (recto) et retourne un dictionnaire contenant :
      - date_mise_en_circulation
      - numero_immatriculation
      - titulaire, nom, prenom
      - numero_titulaire
      - adresse_commune
    """
    data = {
        "date_mise_en_circulation": None,
        "numero_immatriculation": None,
        "titulaire": None,
        "nom": None,
        "prenom": None,
        "numero_titulaire": None,
        "adresse_commune": None
    }

    print(">>> Début du parsing du recto")
    print("Texte extrait :", extracted_text)

    for i, word in enumerate(extracted_text):
        if match(IMMATRICULATION_PATTERN, word):
            data["numero_immatriculation"] = word
            print(f"  -> Immatriculation trouvée : {word}")

        if fuzzy_match(word, "Date Immatriculation", 70):
            print(f"  -> Mot déclencheur pour date détecté : '{word}'")
            for offset in [1, 2, 3, 4]:
                idx = i + offset
                if idx < len(extracted_text) and match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    print(f"     -> Date trouvée à l'index {idx}: {extracted_text[idx]}")
                    break
                else:
                    if idx < len(extracted_text):
                        print(f"     -> Index {idx} ('{extracted_text[idx]}') ne correspond pas au pattern de date")

        # Vérifie si le mot correspond au pattern complet d’un nom titulaire
        if fullmatch(FULLNAME_TITULAIRE_PATTERN, word):
            full_name = word

            # Cas 1 : le mot commence par un préfixe (fusionné)
            if match(TITULAIRE_PREFIX_PATTERN, word):
                cleaned = sub(TITULAIRE_PREFIX_PATTERN, '', word).strip()
            # Cas 2 : mot précédent est un préfixe (séparé)
            elif i > 0 and match(TITULAIRE_PREFIX_PATTERN, extracted_text[i - 1]):
                full_name = f"{extracted_text[i - 1]} {word}"
                cleaned = sub(TITULAIRE_PREFIX_PATTERN, '', full_name).strip()

            # Assignation
            data["titulaire"] = full_name
            parts = cleaned.split()
            if len(parts) >= 2:
                data["nom"] = parts[0]
                data["prenom"] = " ".join(parts[1:])
            else:
                print(f"[WARN] Titulaire détecté '{full_name}' mais nom/prénom mal séparés")

        # if fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6, 16):
        #     data["titulaire"] = word
        #     print(f"  -> Titulaire détecté à l'index {i}: {word}")
        #     cleaned = sub(r'^(?:M\.I?\s?|MI\s?|M\s?)', '', word).lstrip()
        #     print(f"     -> Après suppression du préfixe: '{cleaned}'")
        #     splitted = cleaned.split()
        #     if len(splitted) > 1:
        #         data["nom"] = splitted[0]
        #         data["prenom"] = " ".join(splitted[1:])
        #         print(f"     -> Nom: '{data['nom']}', Prénom: '{data['prenom']}'")
        #     else:
        #         print("     -> Impossible de séparer nom et prénom (moins de 2 mots)")
        #

        if fullmatch(NUM_TITULAIRE_PATTERN, word):
            data["numero_titulaire"] = word
            print(f"  -> Numéro titulaire trouvé : {word}")

        if (fuzzy_match(word, "adresse commune", 70) or
            fuzzy_match(word, "adresse", 65) or
            fuzzy_match(word, "commune", 60)) and i + 2 < len(extracted_text):
            print(f"  -> Mot déclencheur pour adresse détecté à l'index {i}: '{word}'")
            if len(extracted_text[i + 1]) >= 7:
                data["adresse_commune"] = extracted_text[i + 1]
                print(f"     -> Adresse commune trouvée à l'index {i + 1}: '{extracted_text[i + 1]}'")
            elif i + 2 < len(extracted_text) and len(extracted_text[i + 2]) >= 7:
                data["adresse_commune"] = extracted_text[i + 2]
                print(f"     -> Adresse commune trouvée à l'index {i + 2}: '{extracted_text[i + 2]}'")
            elif i + 3 < len(extracted_text) and len(extracted_text[i + 3]) >= 7:
                data["adresse_commune"] = extracted_text[i + 3]
                print(f"     -> Adresse commune trouvée à l'index {i + 3}: '{extracted_text[i + 3]}'")
            else:
                print("     -> Aucune adresse commune trouvée avec une longueur suffisante.")

    print(">>> Fin du parsing, données extraites :", data)
    return data


def parse_cgr_verso_text(extracted_text):
    """
    Analyse la liste de mots (verso) et retourne un dictionnaire contenant :
      - energie, puissance, vin, marque, cylindree.
    """
    data = {
        "energie": None,
        "puissance": None,
        "vin": None,
        "marque": None,
        "cylindree": None
    }

    for i, word in enumerate(extracted_text):
        wlower = word.lower()
        for eng in ENERGIES:
            if fuzzy_match(wlower, eng, 70):
                data["energie"] = word

        if match(r"^(\d+)\s?CV$", word):
            data["puissance"] = word

        if match(r"^[A-Z0-9]{17}$", word.upper()):
            data["vin"] = word

        if fuzzy_match(wlower, "marque", 65) and i + 1 < len(extracted_text):
            data["marque"] = extracted_text[i + 1]

        if match(CYLINDREE_PATTERN, wlower):
            data["cylindree"] = word
        elif fuzzy_match(wlower, "cylindrée", 80) and i + 1 < len(extracted_text):
            data["cylindree"] = extracted_text[i + 1]

    return data
