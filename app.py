import os
import re
import cv2
import numpy as np
import easyocr
from flask import Flask, request, jsonify
from rapidfuzz import fuzz

app = Flask(__name__)

print("🔄 Initialisation d'EasyOCR...")
reader = easyocr.Reader(['fr'], gpu=False)  # Charger le modèle une seule fois
print("✅ EasyOCR chargé !")

# REGEX
IMMATRICULATION_PATTERN = r"[A-Z]{2}-\d{3}-[A-Z]{2}"  # Format AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"                  # Format 13/09/2024
NUM_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|[A-Z]+(?:\s[A-Z]+)+)$"
CYLINDREE_PATTERN = r"^\d{2,7}\s*cm3$"
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]

# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def fuzzy_match(word, target, threshold=78):
    score = fuzz.ratio(word.lower(), target.lower())
    # print(f"Fuzzy match: '{word}' vs '{target}' => {score}")
    return score >= threshold

def parse_titulaire(full_name: str):
    """
    Retire le préfixe M. ou M.I s'il existe, puis sépare en (nom, prénom).
    """
    prefix_pattern = r"^M\.I?(?!\.)\s*"
    name_part = re.sub(prefix_pattern, "", full_name.strip(), flags=re.IGNORECASE)
    splitted = name_part.strip().split()
    if len(splitted) == 0:
        return "", ""
    elif len(splitted) == 1:
        return splitted[0], ""
    else:
        return splitted[0], " ".join(splitted[1:])

def read_image_from_request(key: str):
    """
    Lit l'image depuis request.files[key] et la convertit en objet OpenCV (BGR).
    Retourne None si l'image n'est pas décodable.
    """
    if key not in request.files:
        return None
    file = request.files[key]
    if not file or file.filename == '':
        return None

    image = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)
    return image

def extract_text_with_ocr(image, tolerance=0.35):
    """
    Utilise EasyOCR pour extraire le texte (et la confiance).
    Retourne une liste de mots filtrés par 'tolerance'.
    """
    results = reader.readtext(image)
    extracted_text = [res[1] for res in results if res[2] > tolerance]
    return extracted_text

# ---------------------------------------------------------------------------
# Recto / Verso Logic
# ---------------------------------------------------------------------------

def parse_cgr_recto_text(extracted_text):
    """
    Analyse la liste de mots (recto) et renvoie un dict
    { date_mise_en_circulation, numero_immatriculation, titulaire, nom, prenom, numero_titulaire, adresse_commune }
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

    for i, word in enumerate(extracted_text):
        # Immatriculation
        if re.match(IMMATRICULATION_PATTERN, word):
            data["numero_immatriculation"] = word

        # Date
        if fuzzy_match(word, "Date Immatriculation"):
            for offset in [1, 2, 3, 4]:
                idx = i + offset
                if idx < len(extracted_text) and re.match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    break

        # Titulaire
        if re.fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6, 16):
            data["titulaire"] = word
            data["nom"], data["prenom"] = parse_titulaire(word)

        # Numéro titulaire
        if re.fullmatch(NUM_TITULAIRE_PATTERN, word):
            data["numero_titulaire"] = word

        # Adresse commune
        if (fuzzy_match(word, "adresse commune", 70) or fuzzy_match(word, "adresse", 65)) and i+2 < len(extracted_text):
            next_word = extracted_text[i+1]
            if len(next_word) >= 7:
                data["adresse_commune"] = next_word
            else:
                data["adresse_commune"] = extracted_text[i+2]

    return data

def parse_cgr_verso_text(extracted_text):
    """
    Analyse la liste de mots (verso) et renvoie un dict
    { energie, puissance, vin, marque, cylindree }
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

        # Energie (fuzzy)
        for eng in ENERGIES:
            if fuzzy_match(wlower, eng, 70):
                data["energie"] = word

        # Puissance ex: "8 CV"
        if re.match(r"^(\d+)\s?CV$", word):
            data["puissance"] = word

        # VIN
        if re.match(r"^[A-Z0-9]{17}$", word.upper()):
            data["vin"] = word

        # Marque
        if fuzzy_match(wlower, "marque"):
            if i+1 < len(extracted_text):
                data["marque"] = extracted_text[i+1]

        # Cylindrée
        if re.match(CYLINDREE_PATTERN, wlower):
            data["cylindree"] = word
        elif fuzzy_match(wlower, "cylindrée", 80) and i+1 < len(extracted_text):
            data["cylindree"] = extracted_text[i+1]

    return data

# ---------------------------------------------------------------------------
# Nouveau endpoint unifié
# ---------------------------------------------------------------------------

@app.route('/extract-cgr', methods=['POST'])
def extract_cgr():
    """
    Reçoit deux images : image_recto, image_verso
    Retourne un JSON unifié avec les champs recto + verso.
    Si deux images ne sont pas fournies, renvoie une erreur JSON.
    """
    # Vérifier la présence des deux fichiers
    img_recto = read_image_from_request('image_recto')
    img_verso = read_image_from_request('image_verso')

    if not img_recto or not img_verso:
        return jsonify({"error": "Deux images (recto, verso) doivent être fournies"}), 400

    # Paramètre de tolérance (optionnel)
    tolerance = request.args.get('tolerance', default=0.35, type=float)

    # Extraire le texte
    recto_text = extract_text_with_ocr(img_recto, tolerance)
    verso_text = extract_text_with_ocr(img_verso, tolerance)

    # Analyser recto/verso
    recto_data = parse_cgr_recto_text(recto_text)
    verso_data = parse_cgr_verso_text(verso_text)

    # Fusionner les données dans un seul JSON
    # S'il n'y a pas de collision de clés, c'est facile
    merged_data = {**recto_data, **verso_data}

    return jsonify(merged_data)


# Endpoint de test ou endpoints existants...
# /extract-text, /extract-text-lines, etc.


if __name__ == '__main__':
    # Pour la production: utiliser gunicorn ou un autre WSGI server
    app.run(host='0.0.0.0', port=9000, debug=True)