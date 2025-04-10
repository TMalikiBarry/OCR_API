from flask import request, jsonify

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


########################################################
# Fonctions Utilitaires & auth
########################################################

def check_auth():
    """
    Vérifie la présence du paramètre 'secret-key' dans le corps (JSON ou form-data)
    ou en query string.
    Détermine le rôle : 'mytouchpoint' ou 'public'.
    Retourne (role, None) si OK, ou (None, (json, code)) si erreur.
    """
    secret_key = None
    if request.is_json:
        data = request.get_json(silent=True)
        if data:
            secret_key = data.get('secret-key')

    if not secret_key:
        secret_key = request.form.get('secret-key')

    if not secret_key:
        secret_key = request.args.get('secret-key')

    if not secret_key:
        return None, (jsonify({"error": "Paramètre 'secret-key' manquant"}), 403)

    if secret_key in MYTOUCHPOINT_KEYS:
        return "mytouchpoint", None
    elif secret_key in PUBLIC_KEYS:
        return "public", None
    else:
        return None, (jsonify({"error": "Clé secrète invalide ou non autorisée"}), 403)
