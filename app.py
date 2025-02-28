import easyocr
import numpy as np
import cv2
import re
from flask import Flask, request, jsonify
from rapidfuzz import fuzz

app = Flask(__name__)

# Charger EasyOCR une seule fois
print("🔄 Initialisation d'EasyOCR...")
reader = easyocr.Reader(['fr'], gpu=False)  
print("✅ EasyOCR chargé !")

# Définition des regex
IMMATRICULATION_PATTERN = r"[A-Z]{2}-\d{3}-[A-Z]{2}"  # Format AA-171-TX
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"  # Format 13/09/2024
NUMERO_TITULAIRE_PATTERN = r"\b\d{9,12}\b"
FULLNAME_TITULAIRE_PATTERN = r"^(?:M\.[A-Z]*\s?[A-Z]+(?:\s[A-Z]+)+|[A-Z]+(?:\s[A-Z]+)+)$"
CYLINDREE_PATTERN = r"^\d{2,7}\s*?cm3$"
ENERGIES = ["essence", "diesel", "électrique", "electrique", "hybride", "hydrogène"]



@app.route('/extract-cgr_verso', methods=['POST'])
def extract_cgr_verso():
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    image = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)

    results = reader.readtext(image)
    # extracted_text = [res[1] for res in results if res[2] > 0.35]
    extracted_text = [res[1] for res in results]

    data = {
        "energie": None,
        "puissance": None,
        "vin": None,
        "marque": None,
        "cylindree": None
    }

    for i, word in enumerate(extracted_text):
        wlower = word.lower()

        # Energie (fuzzy sur la liste)
        for eng in ENERGIES:
            if fuzzy_match(wlower, eng, 70):
                data["energie"] = word

        # Puissance ex: "8 CV"
        if re.match(r"^(\d+)\s?CV$", word):
            data["puissance"] = word

        # VIN : 17 caractères alphanumériques
        if re.match(r"^[A-Z0-9]{17}$", word.upper()):
            data["vin"] = word

        # Marque (après "marque" fuzzy)
        if fuzzy_match(wlower, "marque"):
            if i + 1 < len(extracted_text):
                data["marque"] = extracted_text[i + 1]

        # Cylindrée ex: "1462 cm3"
        if re.match(CYLINDREE_PATTERN, wlower):
            data["cylindree"] = word
        elif fuzzy_match(wlower, "cylindrée", 80) and i + 1 < len(extracted_text):
              # Vérifier qu'il y a un mot après
            data["cylindree"] = extracted_text[i + 1]

    return jsonify(data)




@app.route('/extract-cgr_recto', methods=['POST'])
def extract_key_info_cgr_recto():
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    image = cv2.imdecode(np.frombuffer(file.read(), np.uint8), cv2.IMREAD_COLOR)

    # Extraction OCR
    results = reader.readtext(image)
    extracted_text = [res[1] for res in results]

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

        # Date mise en circulation (après "immat" fuzzy)
        if fuzzy_match(word, "Date Immatriculation"):
            if i + 2 < len(extracted_text):
                if re.match(DATE_PATTERN, extracted_text[i + 2]):
                    data["date_mise_en_circulation"] = extracted_text[i + 2]


        if fuzzy_match(word, "Date Immatriculation", 89):
            for offset in [1, 2, 3, 4]:
                idx = i + offset
                if idx < len(extracted_text) and re.match(DATE_PATTERN, extracted_text[idx]):
                    data["date_mise_en_circulation"] = extracted_text[idx]
                    break

        # Titulaire (Full name en majuscules)
        if re.fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6, 16):
            data["titulaire"] = word
            # Séparer nom et prénom
            data["nom"], data["prenom"] = parse_titulaire(word)

        # Numéro titulaire
        if re.fullmatch(NUMERO_TITULAIRE_PATTERN, word):
            data["numero_titulaire"] = word

        # Adresse commune (après "adresse" fuzzy)
        if (fuzzy_match(word, "adresse commune", 70) or fuzzy_match(word, "adresse", 65)) and i + 2 < len(extracted_text):
            next_word = extracted_text[i + 1]
            
            # Si le mot suivant fait au moins 7 caractères, on le prend
            if len(next_word) >= 7:
                data["adresse_commune"] = next_word
            else:
                data["adresse_commune"] = extracted_text[i + 2]

    return jsonify(data)







@app.route('/extract-text', methods=['POST'])
def extract_text():

    print("🟢 Requête reçue ")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)

    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    image = np.frombuffer(file.read(), np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    tolerance = request.args.get('tolerance', default=0.35, type=float)

    # image = preprocess_image(file)

    # Extraction du texte avec EasyOCR
    results = reader.readtext(image)

    # Seulement garder les textes avec une probabilité > 45%
    extracted_text = [res[1] for res in results if res[2] > tolerance]

    return jsonify({"text": extracted_text})






def fuzzy_match(word, target, threshold=78):
    score = fuzz.ratio(word.lower(), target.lower())

    # if score >= threshold:        
    print(f"Comparaison fuzzy : '{word}' vs '{target}' → Score = {score}")

    return score >= threshold



def parse_titulaire(full_name: str):

    """
    Extrait le nom et le prénom d'une chaîne de type :
      - "M. DIAGNE SERIGNE BAMBA"
      - "M. DIAGNE"
      - "M.I DIAGNE SERIGNE BAMBA"
      - "M.IDIAGNE SERIGNE BAMBA"
      - "DIAGNE SERIGNE BAMBA"
    SANS capturer "M.I."
    Retourne (nom, prenom).
    """

    # Nouveau pattern
    # prefix_pattern = r"^M\.(?:I(?:\s+|$)|\s+|$)\s*"
    prefix_pattern = r"^M\.I?(?!\.)\s*"
    
    # 1. On supprime le préfixe s'il existe
    name_part = re.sub(prefix_pattern, "", full_name.strip(), flags=re.IGNORECASE)
    
    # 2. Séparer en mots
    splitted = name_part.strip().split()

    # 3. Gérer les cas
    if len(splitted) == 0:
        return "", ""
    elif len(splitted) == 1:
        return splitted[0], ""
    else:
        last_name = splitted[0]
        first_name = " ".join(splitted[1:])
        return last_name, first_name




@app.route('/extract-text-lines', methods=['POST'])
def extract_text_lines():
    """
    Endpoint pour extraire le texte ligne par ligne, avec un paramètre 'threshold' ajustable.
    threshold : Tolérance en pixels pour considérer que des mots sont sur la même ligne.
    """
    print("🟢 Requête reçue pour extraction ligne par ligne")

    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    image = np.frombuffer(file.read(), np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    # Récupérer le paramètre threshold depuis la requête (avec valeur par défaut 10)
    threshold = request.args.get('threshold', default=10, type=int)

    # Récupérer le paramètre tolerance avec une valeur par défaut de .35
    tolerance = request.args.get('tolerance', default=0.35, type=float)


    # Extraction brute avec EasyOCR
    results = reader.readtext(image)

    # Filtrer les mots avec une probabilité > 45%
    filtered_results = [res for res in results if res[2] > tolerance]

    # Regrouper en lignes avec le threshold spécifié
    extracted_lines = group_text_by_lines(filtered_results, threshold)

    return jsonify({"text": extracted_lines})


def group_text_by_lines(results, threshold=10):
    """
    Regroupe les mots détectés en lignes en fonction de leur proximité verticale.
    
    threshold : Tolérance en pixels pour considérer que des mots sont sur la même ligne.
    """
    results.sort(key=lambda r: r[0][0][1])  # Trier les résultats par la coordonnée Y (haut du mot)
    lines = []
    current_line = []
    last_y = None

    for res in results:
        (top_left, _, bottom_right, _) = res[0]  # Coordonnées du mot
        word = res[1]  # Texte détecté
        y_center = (top_left[1] + bottom_right[1]) / 2  # Centre en Y du mot

        if last_y is None or abs(y_center - last_y) < threshold:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]

        last_y = y_center

    if current_line:
        lines.append(" ".join(current_line))

    return lines



@app.route('/extract-cgr_recto-key_info', methods=['POST'])
def extract_key_info_old():
    print("🟢 Requête reçue")
    print("Headers: ", request.headers)
    print("Form Data: ", request.form)
    print("Files: ", request.files)


    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    image = np.frombuffer(file.read(), np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    # image = preprocess_image(file)

    # Extraction du texte
    results = reader.readtext(image)
    extracted_text = [res[1] for res in results]

    # Initialisation des valeurs
    data = {
        "date_mise_en_circulation": None,
        "numero_immatriculation": None,
        "titulaire": None,
        "nom": None,
        "prenom": None,
        "numero_titulaire": None,
        "adresse_commune": None
    }

    # Recherche des valeurs avec les règles définies
    for i, word in enumerate(extracted_text):
        # Trouver numéro d'immatriculation
        if re.match(IMMATRICULATION_PATTERN, word):
            data["numero_immatriculation"] = word
        
        # Trouver date de mise en circulation (juste après "N° Immatriculation")
        if "immat" in word.lower():
            if i + 1 < len(extracted_text) and re.match(DATE_PATTERN, extracted_text[i + 1]):
                data["date_mise_en_circulation"] = extracted_text[i + 1]

        # Trouver le titulaire
        if re.fullmatch(FULLNAME_TITULAIRE_PATTERN, word) and i in range(6, 16):
            data["titulaire"] = word


        # if "titulaire" in word.lower() and len(word) > len("titulaire"):
        #     if i + 2 < len(extracted_text):  
        #         data["titulaire"] = extracted_text[i + 2]

        # Trouver numéro titulaire (le DEUXIÈME champ après "N° Titulaire")
        if re.fullmatch(NUMERO_TITULAIRE_PATTERN, word):
                data["numero_titulaire"] = word

        # Trouver adresse commune (le PROCHAIN champ après "Adresse")
        if "adresse" in word.lower() or "ommune" in word.lower():
            if i + 1 < len(extracted_text):  
                data["adresse_commune"] = extracted_text[i + 1]

    return jsonify(data)




def preprocess_image(file):
    image = np.frombuffer(file.read(), np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)

    # Convertir en niveaux de gris
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Appliquer un seuillage adaptatif
    processed_image = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    return processed_image



@app.route('/verify', methods=['POST'])
def verify_image():
    print("🟢 Requête reçue !")
    print("Headers:", request.headers)
    print("Form Data:", request.form)
    print("Files:", request.files)

    if 'image' not in request.files or request.files['image'].filename == '':
        print("❌ Aucune image reçue")
        return jsonify({"error": "Aucune image reçue"}), 400
    
    print("✅ Image détectée !")
    return jsonify({"message": "Image bien reçue"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)
