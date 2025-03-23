import io
import re

import easyocr
import rapidfuzz
import torch
from PIL import Image
from flask import Flask, request, jsonify

########################################################
# Configuration Flask & EasyOCR
########################################################
app = Flask(__name__)

########################################################
# Clés d'authentification
########################################################
MYTOUCHPOINT_KEYS = {
    "5D13989CABA5EDF241031D8006E29949BAECD065768C29F557B74681FAE31A6DECC31698FC313985A1D9D8CAF27D362676ABCD843022CCF709F918C1B58A4CF8",
    "6E8283286DFC864454F4FCD9738FBE644982FAAB3B2F98B79D11BDDF4129AC0172FC103D8B0C6E0AB023BF85803C6BE00BE80DB27F7DE9BD36E7125CCA637119"
}

PUBLIC_KEYS = {
    "C3835FDAC10F61B49E27619F7618BDC7A12BEA581A717240FE775FA93B3A928D456374ACB73044F0ED6B79F220DA0D79EA23082D39477D1923BB5B360E8DD56A"
}

print("🔄 Initialisation d'EasyOCR...")
reader = easyocr.Reader(['fr'], gpu=torch.cuda.is_available())
print("✅ EasyOCR chargé !")

########################################################
# Listes & Regex
########################################################
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]
IMMATRICULATION_PATTERN = r"^[A-Z]{2}[-.\s]?\d{2,4}[-.\s]?[A-Z]{1,3}$"  # AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"  # 13/09/2024
NUM_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|[A-Z]+(?:\s[A-Z]+)+)$"
CYLINDREE_PATTERN = r"^\d{2,7}\s*cm3$"


########################################################
# Fonctions Utilitaires & auth
########################################################

def fuzzy_match(word: str, target: str, threshold=70):
    """
    Compare deux chaînes en minuscule via rapidfuzz et renvoie True si score >= threshold.
    """
    score = rapidfuzz.fuzz.ratio(word.lower(), target.lower())
    return score >= threshold


def downscale_image_if_needed(pil_image: Image.Image, max_size=1080):
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


def extract_text_with_ocr(file_storage, tolerance=0.2):
    """
    Lit le fichier image (FileStorage), le convertit en PIL, downscale si besoin,
    puis utilise EasyOCR pour extraire le texte (avec un seuil 'tolerance').
    Retourne la liste des mots extraits.
    """
    pil_image = Image.open(file_storage)
    pil_image = downscale_image_if_needed(pil_image, max_size=1080)

    # Convertir PIL -> bytes
    img_bytes = io.BytesIO()
    pil_image.save(img_bytes, format='PNG')
    content = img_bytes.getvalue()

    # Extraire le texte via EasyOCR
    results = reader.readtext(content)  # detail=1 => [ ([x1,y1],[x2,y2]...), 'texte', conf ]
    extracted_text = [res[1] for res in results if res[2] > tolerance]
    return extracted_text


def check_auth():
    """
    Vérifie la présence du paramètre 'secret-key' en query string.
    Détermine le rôle : 'mytouchpoint' ou 'public'.
    Retourne (role, None) si OK, ou (None, (json, code)) si erreur.
    """
    secret_key = request.args.get('secret-key')
    if not secret_key:
        return None, (jsonify({"error": "Paramètre 'secret-key' manquant"}), 403)

    # Déterminer le rôle
    if secret_key in MYTOUCHPOINT_KEYS:
        return "mytouchpoint", None
    elif secret_key in PUBLIC_KEYS:
        return "public", None
    else:
        return None, (jsonify({"error": "Clé secrète invalide ou non autorisée"}), 403)


########################################################
# Détection du type de document (recto/verso)
########################################################
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

        # Score recto
        if any(fuzzy_match(wlower, kw, 65) for kw in recto_keywords):
            recto_score += 1
        # Immatriculation pattern
        if re.match(IMMATRICULATION_PATTERN, word):
            recto_score += 1
        # Score verso
        if any(fuzzy_match(wlower, kw, 65) for kw in verso_keywords):
            verso_score += 1
        # VIN
        if re.match(r"^[A-Z0-9]{17}$", word.upper()):
            verso_score += 1

    if recto_score > verso_score:
        return "recto"
    elif verso_score > recto_score:
        return "verso"
    else:
        return None


########################################################
# Fonctions de parsing recto / verso
########################################################
def parse_cgr_recto_text(extracted_text):
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

        # Date (fuzzy 'Date Immatriculation')
        if fuzzy_match(word, "Date Immatriculation", 70):
            for offset in [1, 2, 3, 4]:
                idx = i + offset
                if idx < len(extracted_text) and re.match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    break

        # Titulaire (full name)
        if re.fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6, 16):
            data["titulaire"] = word
            # Séparer nom/prénom
            splitted = word.split()
            if len(splitted) > 1:
                data["nom"] = splitted[0]
                data["prenom"] = " ".join(splitted[1:])

        # Numéro titulaire
        if re.fullmatch(NUM_TITULAIRE_PATTERN, word):
            data["numero_titulaire"] = word

        # Adresse commune
        if (fuzzy_match(word, "adresse commune", 70) or fuzzy_match(word, "adresse", 65)
            or fuzzy_match(word, "commune", 60)) and i + 2 < len(extracted_text):

            # next_word = extracted_text[i + 1]
            if len(extracted_text[i + 1]) >= 7:
                data["adresse_commune"] = extracted_text[i + 1]
            elif len(extracted_text[i + 2]) >= 7:
                data["adresse_commune"] = extracted_text[i + 2]
            else:
                data["adresse_commune"] = extracted_text[i + 3]

    return data


def parse_cgr_verso_text(extracted_text):
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

        # Puissance ex: '8 CV'
        if re.match(r"^(\d+)\s?CV$", word):
            data["puissance"] = word

        # VIN
        if re.match(r"^[A-Z0-9]{17}$", word.upper()):
            data["vin"] = word

        # Marque
        if fuzzy_match(wlower, "marque", 65) and i + 1 < len(extracted_text):
            data["marque"] = extracted_text[i + 1]

        # Cylindrée
        if re.match(CYLINDREE_PATTERN, wlower):
            data["cylindree"] = word
        elif fuzzy_match(wlower, "cylindrée", 80) and i + 1 < len(extracted_text):
            data["cylindree"] = extracted_text[i + 1]

    return data


########################################################
# 1) /extract-text : renvoie texte brut
########################################################
@app.route('/extract-text', methods=['POST'])
def endpoint_extract_text():
    """
    Accessible aux deux rôles (mytouchpoint, public).
    """

    role, auth_error = check_auth()

    if auth_error:
        return auth_error  # (json, code)

    """
    Retourne la liste de mots extraits de l'image (texte brut).
    Paramètre 'tolerance' (float) en query string (ex: ?tolerance=0.4).
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Full Text!")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)
    return jsonify({"text": extracted_text})


########################################################
# 2) /extract-recto : parse champs recto
########################################################
@app.route('/extract-recto', methods=['POST'])
def endpoint_extract_recto():
    """
    Accessible uniquement à mytouchpoint.
    """

    role, auth_error = check_auth()

    if auth_error:
        return auth_error

    if role != "mytouchpoint":
        return jsonify({"error": "Accès refusé. Endpoint réservé à MyTouchpoint."}), 403

    """
    Extrait les infos du recto (date, immatriculation, titulaire, etc.).
    Si l'image semble être un verso, on met un 'warning' dans la réponse.
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Recto!")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)

    # Détecter le type
    doc_type = detect_document_type(extracted_text)
    if doc_type is None:
        return jsonify({"error": "Le type de document fourni n'est pas reconnu."}), 400

    warning = None
    if doc_type == "verso":
        warning = "Attention : le document semble être un verso, alors que l'endpoint attend un recto."

    recto_data = parse_cgr_recto_text(extracted_text)

    # Inclure le warning dans la réponse si nécessaire
    if warning:
        recto_data["warning"] = warning

    return jsonify(recto_data)


########################################################
# 3) /extract-verso : parse champs verso
########################################################
@app.route('/extract-verso', methods=['POST'])
def endpoint_extract_verso():
    """
    Accessible uniquement à mytouchpoint.
    """

    role, auth_error = check_auth()

    if auth_error:
        return auth_error

    if role != "mytouchpoint":
        return jsonify({"error": "Accès refusé. Endpoint réservé à MyTouchpoint."}), 403

    """
    Extrait les infos du verso (energie, puissance, vin, marque, cylindree).
    Si l'image semble être un recto, on met un 'warning' dans la réponse.
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Verso!")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], tolerance)

    doc_type = detect_document_type(extracted_text)
    if doc_type is None:
        return jsonify({"error": "Le type de document fourni n'est pas reconnu."}), 400

    warning = None
    if doc_type == "recto":
        warning = "Attention : le document semble être un recto, alors que l'endpoint attend un verso."

    verso_data = parse_cgr_verso_text(extracted_text)

    if warning:
        verso_data["warning"] = warning

    return jsonify(verso_data)


########################################################
# 4) /extract-cgr : reçoit deux images recto/verso
########################################################
@app.route('/extract-cgr', methods=['POST'])
def endpoint_extract_cgr():
    """
    Reçoit deux images : image_recto, image_verso
    Retourne un JSON unifié avec les champs recto + verso.
    Accessible uniquement à mytouchpoint.
    """

    role, auth_error = check_auth()

    if auth_error:
        return auth_error

    if role != "mytouchpoint":
        return jsonify({"error": "Accès refusé. Endpoint réservé à MyTouchpoint."}), 403

    if 'image_recto' not in request.files or 'image_verso' not in request.files:
        return jsonify({"error": "Deux images (recto, verso) doivent être fournies"}), 400

    print("🟢 Requête reçue Extraction Verso!")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)

    # Recto
    recto_text = extract_text_with_ocr(request.files['image_recto'], tolerance)
    recto_data = parse_cgr_recto_text(recto_text)

    # Verso
    verso_text = extract_text_with_ocr(request.files['image_verso'], tolerance)
    verso_data = parse_cgr_verso_text(verso_text)

    # Fusion
    merged_data = {**recto_data, **verso_data}
    return jsonify(merged_data)


########################################################
# Main
########################################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)
