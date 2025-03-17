import io
import re
import cv2
import math
import easyocr
import numpy as np
from PIL import Image
from flask import Flask, request, jsonify
from rapidfuzz import fuzz
import torch

app = Flask(__name__)

print("🔄 Initialisation d'EasyOCR...")
# Détection auto du GPU si dispo
reader = easyocr.Reader(['fr'], gpu=torch.cuda.is_available())
print("✅ EasyOCR chargé !")

# -------------------- REGEX & Listes --------------------
IMMATRICULATION_PATTERN = r"[A-Z]{2}-\d{3}-[A-Z]{2}"  # Format AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"                  # Format 13/09/2024
NUM_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|[A-Z]+(?:\s[A-Z]+)+)$"
CYLINDREE_PATTERN = r"^\d{2,7}\s*cm3$"
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]

# -------------------- Fonctions Utilitaires --------------------
def fuzzy_match(word, target, threshold=78):
    score = fuzz.ratio(word.lower(), target.lower())
    # Debug si besoin:
    # print(f"Fuzzy match: '{word}' vs '{target}' => {score}")
    return score >= threshold

def parse_titulaire(full_name: str):
    """
    Retire le préfixe M. ou M.I s'il existe, puis sépare en (nom, prénom).
    """
    prefix_pattern = r"^M\.I?(?!\.)\s*"
    import re
    name_part = re.sub(prefix_pattern, "", full_name.strip(), flags=re.IGNORECASE)
    splitted = name_part.strip().split()
    if len(splitted) == 0:
        return "", ""
    elif len(splitted) == 1:
        return splitted[0], ""
    else:
        return splitted[0], " ".join(splitted[1:])

def downscale_image_if_needed(pil_image, max_size=1080):
    """
    Réduit la taille de l'image (PIL) si la dimension la plus grande > max_size.
    """
    w, h = pil_image.size
    if max(w, h) > max_size:
        ratio = max_size / float(max(w, h))
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
    return pil_image

def extract_text_with_ocr(image_file, tolerance=0.35):
    """
    Lit le fichier image (FileStorage), le convertit en PIL, downscale si besoin,
    puis utilise EasyOCR pour extraire le texte (avec un seuil 'tolerance').
    Retourne la liste des mots.
    """
    pil_image = Image.open(image_file)
    pil_image = downscale_image_if_needed(pil_image, max_size=1080)

    # Convertir PIL -> bytes pour EasyOCR
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format='PNG')
    content = img_bytes.getvalue()

    # Extraire le texte
    results = reader.readtext(content)  # detail=1 => [ [ [x1,y1],[x2,y2],[x3,y3],[x4,y4] ], text, conf ]
    # Filtrer par conf > tolerance
    extracted_text = [res[1] for res in results if res[2] > tolerance]
    return extracted_text

# -------------------- Logiques Recto / Verso --------------------
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

        # Date (fuzzy "Date Immatriculation")
        if fuzzy_match(word, "Date Immatriculation"):
            for offset in [1,2,3,4]:
                idx = i + offset
                if idx < len(extracted_text) and re.match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    break

        # Titulaire
        if re.fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6,16):
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

        # Energie
        for eng in ENERGIES:
            if fuzzy_match(wlower, eng, 70):
                data["energie"] = word

        # Puissance ex: "8 CV"
        if re.match(r"^(\d+)\s?CV$", word):
            data["puissance"] = word

        # VIN : 17 caractères
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

# -------------------- Endpoints --------------------

@app.route('/extract-text', methods=['POST'])
def endpoint_extract_text():
    """
    Retourne la liste de mots extraits de l'image (une seule image).
    Paramètre 'tolerance' en query string (ex: ?tolerance=0.4).
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    tolerance = request.args.get('tolerance', default=0.35, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)
    return jsonify({"text": extracted_text})

@app.route('/extract-recto', methods=['POST'])
def endpoint_extract_recto():
    """
    Extrait les infos du recto (date, immatriculation, titulaire, etc.) depuis une seule image.
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    tolerance = request.args.get('tolerance', default=0.35, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)
    recto_data = parse_cgr_recto_text(extracted_text)
    return jsonify(recto_data)

@app.route('/extract-verso', methods=['POST'])
def endpoint_extract_verso():
    """
    Extrait les infos du verso (energie, puissance, vin, marque, cylindree) depuis une seule image.
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    tolerance = request.args.get('tolerance', default=0.35, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)
    verso_data = parse_cgr_verso_text(extracted_text)
    return jsonify(verso_data)

@app.route('/extract-cgr', methods=['POST'])
def endpoint_extract_cgr():
    """
    Reçoit deux images : image_recto, image_verso
    Retourne un JSON unifié avec les champs recto + verso.
    """
    if 'image_recto' not in request.files or 'image_verso' not in request.files:
        return jsonify({"error": "Deux images (recto, verso) doivent être fournies"}), 400

    tolerance = request.args.get('tolerance', default=0.35, type=float)

    # Recto
    recto_text = extract_text_with_ocr(request.files['image_recto'], tolerance)
    recto_data = parse_cgr_recto_text(recto_text)

    # Verso
    verso_text = extract_text_with_ocr(request.files['image_verso'], tolerance)
    verso_data = parse_cgr_verso_text(verso_text)

    # Fusion
    merged_data = {**recto_data, **verso_data}
    return jsonify(merged_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)