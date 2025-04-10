# app.py
from easyocr import Reader
from flask import Flask, request, jsonify

from utils.auth import (check_auth)
from utils.ocr_parser import (
    parse_cgr_recto_text,
    parse_cgr_verso_text
)
# Importation des fonctions de nos modules utilitaires
from utils.preprocessing import extract_text_with_ocr

########################################################
# Configuration Flask & EasyOCR
########################################################
app = Flask(__name__)


print("🔄 Initialisation d'EasyOCR (CPU uniquement)...")
reader = Reader(['fr'], gpu=False)
print("✅ EasyOCR chargé !")



########################################################
# Endpoints
########################################################

# 0) /test : tester facilement le déploiement
@app.route('/test', methods=['GET'])
def isDeploiementOK():
    return jsonify({"message": "Votre API, EasyOcrAPI, a été déployé avec succès"})


########################################################
# 1) /extract-text : renvoie texte brut
########################################################
@app.route('/extract-text', methods=['POST'])
def endpoint_extract_text():
    """
    Accessible aux deux rôles (mytouchpoint, public).

    Retourne la liste de mots extraits de l'image (texte brut).
    Paramètre 'tolerance' (float) en query string (ex: ?tolerance=0.4).
    """
    role, auth_error = check_auth()
    if auth_error:
        return auth_error

    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Full Text!")
    print("Headers:", request.headers)
    print("Form Data:", request.form)
    print("Files:", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], reader, tolerance)
    return jsonify({"text": extracted_text})


########################################################
# 2) /extract-recto : parse champs recto
########################################################
@app.route('/extract-recto', methods=['POST'])
def endpoint_extract_recto():
    """
    Accessible uniquement à mytouchpoint.

    Extrait les infos du recto (date, immatriculation, titulaire, etc.).
    Si l'image semble être un verso, un 'warning' peut être inclus dans la réponse.
    """
    role, auth_error = check_auth()
    if auth_error:
        return auth_error
    if role != "mytouchpoint":
        return jsonify({"error": "Accès refusé. Endpoint réservé à MyTouchpoint."}), 403

    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Recto!")
    print("Headers:", request.headers)
    print("Form Data:", request.form)
    print("Files:", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], reader, tolerance)

    recto_data = parse_cgr_recto_text(extracted_text)
    return jsonify(recto_data)


########################################################
# 3) /extract-verso : parse champs verso
########################################################
@app.route('/extract-verso', methods=['POST'])
def endpoint_extract_verso():
    """
    Accessible uniquement à mytouchpoint.

    Extrait les infos du verso (energie, puissance, vin, marque, cylindree).
    Si l'image semble être un recto, un 'warning' peut être inclus dans la réponse.
    """
    role, auth_error = check_auth()
    if auth_error:
        return auth_error
    if role != "mytouchpoint":
        return jsonify({"error": "Accès refusé. Endpoint réservé à MyTouchpoint."}), 403

    if 'image' not in request.files:
        return jsonify({"error": "Aucune image fournie"}), 400

    print("🟢 Requête reçue Extraction Verso!")
    print("Headers:", request.headers)
    print("Form Data:", request.form)
    print("Files:", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)
    extracted_text = extract_text_with_ocr(request.files['image'], reader, tolerance)

    verso_data = parse_cgr_verso_text(extracted_text)
    return jsonify(verso_data)


########################################################
# 4) /extract-cgr : reçoit deux images recto/verso
########################################################
@app.route('/extract-cgr', methods=['POST'])
def endpoint_extract_cgr():
    """
    Reçoit deux images : image_recto, image_verso.
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

    print("🟢 Requête reçue Extraction CGR!")
    print("Headers:", request.headers)
    print("Form Data:", request.form)
    print("Files:", request.files)

    tolerance = request.args.get('tolerance', default=0.2, type=float)

    # Extraction pour le recto
    recto_text = extract_text_with_ocr(request.files['image_recto'], reader, tolerance)
    recto_data = parse_cgr_recto_text(recto_text)

    # Extraction pour le verso
    verso_text = extract_text_with_ocr(request.files['image_verso'], reader, tolerance)
    verso_data = parse_cgr_verso_text(verso_text)

    # Fusion des données
    merged_data = {**recto_data, **verso_data}
    return jsonify(merged_data)


########################################################
# Main
########################################################
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)