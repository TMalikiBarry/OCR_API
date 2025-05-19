# utils/ocr_parser.py

from re import sub, match, fullmatch, compile
from typing import Optional

from rapidfuzz.fuzz import ratio

# Constantes et patterns
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]
# IMMATRICULATION_PATTERN = r"^[A-Z]{2}[-.\s]?\d{2,4}[-.\s]?[A-Z]{1,3}$"  # Exemple : AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"  # Exemple : 13/09/2024
NUM_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
# FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.(?:I)?[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|(?:I)?[A-Z]+(?:\s[A-Z]+)+)$"
FULLNAME_TITULAIRE_PATTERN = r'^(?:M(?:[:\.]\s?)?(?:I\s?)?)?[A-Z]+(?:\s[A-Z]+)+$'
# TITULAIRE_PREFIX_PATTERN = r'^M(?::|\s)?(?:\.?\s?I)?\s?'
TITULAIRE_PREFIX_PATTERN = r'^M(?:[:\.]\s?)?(?:I\s?)?'
CYLINDREE_PATTERN = r"^\d{2,7}\s*cm3$"

# IMMATRICULATION_PATTERN = r"^(?:[A-Z]{2}[\s-]?[0-9]{2,4}[\s-]?[A-Z]{1,3})(?:[\s-]?[A-Z]{1,3})?$"

# Nouveau pattern strict pour les plaques d'immatriculation françaises/sénégalaises :
# 2 lettres, séparateur optionnel, 3 chiffres, séparateur optionnel, 2 lettres.
NEW_IMMATRICULATION_PATTERN = r"^[A-Z]{2}[-\s]?[0-9]{3}[-\s]?[A-Z]{2}$"

# Dictionnaire des ambiguïtés fréquentes (à titre d'exemple)
AMBIGUOUS_MAP = {
    '4': 'A',
    '0': 'O',
    '1': 'I',
    '8': 'B',
    # Dans l'autre sens (mais nous ne corrigerons pas si c'est déjà correct)
    'A': '4',
    'O': '0',
    'I': '1',
    'B': '8'
}

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
        if match(NEW_IMMATRICULATION_PATTERN, word):
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
    data: dict[str, Optional[str]] = {
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
        # if match(IMMATRICULATION_PATTERN, word):
        #     data["numero_immatriculation"] = word
        #     print(f"  -> Immatriculation trouvée : {word}")

        if fuzzy_match(word, "Date Immatriculation", 70):
            print(f"  -> Mot déclencheur pour date détecté : '{word}'")
            for offset in [1, 2, 3, 4]:
                idx = i + offset
                if idx < len(extracted_text) and match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    print(f"     -> Date trouvée à l'index {idx}: {extracted_text[idx]}")
                    break

        # Vérifie si le mot correspond au pattern complet d’un nom titulaire
        if fullmatch(FULLNAME_TITULAIRE_PATTERN, word):
            full_name = word
            cleaned = None
            # Cas 1 : le mot commence par un préfixe (fusionné)
            if match(TITULAIRE_PREFIX_PATTERN, word):
                cleaned = sub(TITULAIRE_PREFIX_PATTERN, '', word).strip()
            # Cas 2 : mot précédent est un préfixe (séparé)
            elif i > 0 and match(TITULAIRE_PREFIX_PATTERN, extracted_text[i - 1]):
                full_name = f"{extracted_text[i - 1]} {word}"
                cleaned = sub(TITULAIRE_PREFIX_PATTERN, '', full_name).strip()

            # Assignation
            data["titulaire"] = full_name
            if cleaned is not None:
                parts = cleaned.split()
                if len(parts) >= 2:
                    data["nom"] = parts[0]
                    data["prenom"] = " ".join(parts[1:])
            else:
                print(f"[WARN] Titulaire détecté '{full_name}' mais nom/prénom mal séparés")


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

        c_word = correct_immatriculation(word)

        if c_word is not None:
            data["numero_immatriculation"] = c_word
            print(f"  -> Immatriculation trouvée : {corrected}")

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


def parse_cni_recto_text(extracted_text: list[str]) -> dict[str, Optional[str]]:
    """
    Extrait du recto de la CNI sénégalaise :
     - prenoms (MAJUSCULES)
     - nom (MAJUSCULE)
     - date_naissance (première date)
     - lieu_naissance (token après le label 'lieu' ou 'lieu de naissance')
     - date_expiration (3ᵉ date ou 2ᵉ si seulement délivrance+expiration)
     - taille (valeur en cm)
     - adresse_domicile (token après 'adresse')
     - sexe (F ou M)
    """
    data: dict[str, Optional[str]] = {
        "prenoms": None,
        "nom": None,
        "date_naissance": None,
        "lieu_naissance": None,
        "date_expiration": None,
        "taille": None,
        "adresse_domicile": None,
        "sexe": None
    }

    dates: list[str] = []
    for i, w in enumerate(extracted_text):
        lw = w.lower()

        # 1) Prénoms
        if fuzzy_match(lw, "prenom", 67) and i + 1 < len(extracted_text):
            data["prenoms"] = extracted_text[i + 1].upper()

        # 2) Nom
        if fuzzy_match(lw, "nom", 67) and i + 1 < len(extracted_text):
            if not fuzzy_match(extracted_text[i + 1].lower(), "prenom", 70):
                data["nom"] = extracted_text[i + 1].upper()

        # 3) Dates
        if fullmatch(DATE_PATTERN, w):
            dates.append(w)

        # 4) Adresse du domicile
        if (fuzzy_match(lw, "adresse du domicile", 70) or
            fuzzy_match(lw, "adresse", 65) or
            fuzzy_match(lw, "domicile", 60)) and i + 1 < len(extracted_text):
            data["adresse_domicile"] = extracted_text[i + 1]

        # 5) Lieu de naissance
        # Repère soit 'lieu', soit 'lieu de naissance'
        if (fuzzy_match(lw, "lieu", 60) or fuzzy_match(lw, "lieu de naissance", 65)) \
                and i + 1 < len(extracted_text):
            data["lieu_naissance"] = extracted_text[i + 1].upper()

        # 6) Taille
        if "cm" in lw and data["taille"] is None:
            data["taille"] = w
            if data["lieu_naissance"] is None:
                data["lieu_naissance"] = extracted_text[i + 1]

        # 7) Sexe (juste “M” ou “F” comme token isolé)
        if lw.strip().upper() in ("M", "F"):
            data["sexe"] = lw.strip().upper()

    # Affectation des dates clés
    if dates:
        data["date_naissance"] = dates[0]
    if len(dates) >= 3:
        data["date_expiration"] = dates[2]
    elif len(dates) == 2:
        data["date_expiration"] = dates[1]

    return data


def parse_cni_verso_text(extracted_text: list[str], gender: Optional[str] = None) -> dict[str, Optional[str]]:
    """
    Extrait le NIN (Numéro d'Identité Nationale) du verso de la CNI sénégalaise.
    Si on passe `gender="M"` ou `"F"`, on ajoute le préfixe 1 (M) ou 2 (F) si absent.
    """
    data: dict[str, Optional[str]] = {"nin": None}

    for i, token in enumerate(extracted_text):
        if fuzzy_match(token, "nin", 70) and i + 1 < len(extracted_text):
            raw = sub(r"\s+", "", extracted_text[i + 1])
            # digits = "".join(filter(str.isdigit, raw))
            digits = "".join([c for c in raw if c.isdigit()])

            # ajoute le préfixe genre si nécessaire
            if gender in ("M", "F"):
                prefix = "1" if gender == "M" else "2"
                if not digits.startswith(prefix):
                    digits = prefix + digits

            # formate en blocs : 1 052 1998 00612
            if len(digits) >= 12:
                b1 = digits[0]
                b2 = digits[1:4]
                b3 = digits[4:8]
                b4 = digits[8:13]
                data["nin"] = f"{b1} {b2} {b3} {b4}"
            else:
                data["nin"] = digits
            break

    return data


def correct_immatriculation(candidate: str, threshold: int = 80) -> str | None:
    """
    Corrige une chaîne candidate d'immatriculation issue d'OCR, en appliquant des corrections
    seulement dans les positions attendues :
      - Les 2 premiers caractères (lettres) et les 2 derniers (lettres) ne seront
        corrigés que s'ils ne sont pas des lettres, en utilisant AMBIGUOUS_MAP.
      - Les 3 caractères du milieu (chiffres) seront corrigés uniquement s'ils ne sont pas des chiffres.

    Le pattern attendu est : 2 lettres, 3 chiffres, 2 lettres,
    éventuellement avec des séparateurs (espace ou tiret).

    Si la candidate est trop différente ou non plausible, retourne None.
    Sinon, si une correction pertinente est trouvée et que le score fuzzy (comparaison sans séparateurs)
    dépasse le seuil, renvoie le numéro corrigé, formaté en "LL-DDD-LL".
    """
    pattern = compile(NEW_IMMATRICULATION_PATTERN)

    # D'abord, si la candidate correspond déjà au pattern strict, on la retourne directement.
    if pattern.match(candidate):
        return candidate

    # Supprimer séparateurs pour analyser la structure (nous attendons 7 caractères : LLDDDLL)
    clean = sub(r"[-\s]", "", candidate)
    if len(clean) != 7:
        return None  # La chaîne n'a pas la longueur attendue pour une plaque valide.

    corrected = list(clean)
    # Positions attendues :
    #   positions 0 et 1 : lettres,
    #   positions 2, 3 et 4 : chiffres,
    #   positions 5 et 6 : lettres.
    letter_positions = [0, 1, 5, 6]
    digit_positions = [2, 3, 4]

    for i in letter_positions:
        ch = corrected[i]
        if not ch.isalpha() and ch in AMBIGUOUS_MAP and AMBIGUOUS_MAP[ch].isalpha():
            corrected[i] = AMBIGUOUS_MAP[ch]

    for i in digit_positions:
        ch = corrected[i]
        if not ch.isdigit() and ch in AMBIGUOUS_MAP and AMBIGUOUS_MAP[ch].isdigit():
            corrected[i] = AMBIGUOUS_MAP[ch]

    # Reconstituer le candidat sans séparateurs
    candidate_cleaned = "".join(corrected)
    # Format strict: insérer des tirets pour obtenir "LL-DDD-LL"
    formatted = f"{candidate_cleaned[0:2]}-{candidate_cleaned[2:5]}-{candidate_cleaned[5:7]}"

    # On calcule un score fuzzy en comparant en retirant les séparateurs
    score = ratio(sub(r"[-\s]", "", candidate), candidate_cleaned)
    if score >= threshold and pattern.match(formatted):
        return formatted

    return candidate


if __name__ == '__main__':
    ocr_result = "A4-717-NS"  # OCR renvoie "A4-717-NS" au lieu de "AA-717-NS"
    corrected = correct_immatriculation(ocr_result)
    print(f"Original: {ocr_result} -> Corrigé: {corrected}")
    print(correct_immatriculation("A4-717-NS"))  # → AA-717-NS
    print(correct_immatriculation("AA-7I7-NS"))  # → AA-717-NS
    print(correct_immatriculation("AA-OOO-NS"))  # → AA-000-NS
    print(correct_immatriculation("AA-717-NB"))  # → AA-717-NB
