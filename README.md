# **OCR_API** – *API d’Extraction de Texte et Données Structurées*

**EasyOCR_API** est une API développée avec *Flask* et utilisant **EasyOCR** pour extraire du texte et des données
spécifiques à partir d'images de documents.  
Elle est conçue pour reconnaître et analyser différents types de documents, notamment:

- **Carte grise**
- **Carte d'identité nationale**
- **Documents d'assurance**

L’authentification se fait via un paramètre `secret-key` passé en query string.

---

## ⚙️ **Authentification**

Pour accéder aux endpoints, ajoutez le paramètre `secret-key` dans l'URL.

**Exemple d’appel :**

```
?secret-key=VOTRE_CLE_SECRETE
```

## 🔑 **Rôles et Accès**

| Rôle         | Accès                                      |
|--------------|--------------------------------------------|
| mytouchpoint | Accès complet à tous les endpoints privés. |
| public       | Accès limité à /extract-text uniquement.   |

## 📌 **Endpoints et Exemples cURL**

## 1️⃣ */extract-text*

**Description** : Extrait l'ensemble du texte brut de l'image.

**Description :**  
Extrait l'ensemble du **texte brut** de l'image.

- **Méthode :** `POST`

- **Paramètres :**
  - *Query* : `tolerance` (optionnel, par défaut `0.2`)
  - *Form*  : `secret-key` (clé d’authentification), `image` (fichier image)

#### Exemple cURL :

```bash
curl -X POST "http://localhost:9000/extract-text?tolerance=0.2" \
  -F "secret-key=VOTRE_CLE_SECRETE" \
  -F "image=@/chemin/vers/image.png"
```
## 2️⃣ */extract-recto* (🔒 MyTouchpoint uniquement )

**Description** : Extrait les informations du recto du document (ex : date de mise en circulation, numéro
d'immatriculation, titulaire, nom, prénom, numéro titulaire, adresse commune).

> 💡 Si l’image fournie correspond au verso, un avertissement sera inclus dans la réponse.

- Méthode : ```POST```

- Paramètres :

  - *Query* : ```tolerance``` (optionnel, par défaut ```0.2```)

  - *Form* : `secret-key` (clé d’authentification), ```image``` (fichier image)

#### Exemple cURL :

```
 curl -X POST "http://localhost:9000/extract-recto?tolerance=0.2" \
   -F "secret-key=VOTRE_CLE_SECRETE" \
  -F "image=@/chemin/vers/recto.png"
```
## 3️⃣ */extract-verso* (🔒 MyTouchpoint uniquement)

**Description** : Extrait les informations du verso du document (ex : énergie, puissance, VIN, marque, cylindrée).

> 💡 Si l’image fournie correspond au recto, un avertissement sera inclus dans la réponse.

- Méthode : ```POST```

- Paramètres :

  - *Query* : ```tolerance``` (optionnel, par défaut ```0.2```)

  - *Form* : `secret-key` (clé d’authentification),  ```image``` (fichier image)

#### Exemple cURL :

``` bash
 curl -X POST "http://localhost:9000/extract-verso?tolerance=0.2" \
  -F "secret-key=VOTRE_CLE_SECRETE" \
  -F "image=@/chemin/vers/verso.png"
```

## 4️⃣ */extract-cgr* (🔒 MyTouchpoint uniquement)

**Description** : Reçoit deux images (recto et verso) et renvoie un JSON unifié regroupant les informations extraites de
chacune.

- Méthode : ```POST```

- Paramètres :

  - *Query* : ```tolerance``` (optionnel, par défaut ```0.2```)

  - *Form* : `secret-key` (clé d’authentification), ```image_recto``` et ```image_verso``` (fichiers images)

#### Exemple cURL :

```
 curl -X POST "http://localhost:9000/extract-cgr?tolerance=0.2" \
  -F "secret-key=VOTRE_CLE_SECRETE" \
  -F "image_recto=@/chemin/vers/recto.png" \
  -F "image_verso=@/chemin/vers/verso.png"
```

## 🔧 Remarques Techniques

> - 📌 EasyOCR est utilisé pour extraire le texte depuis l’image.

> - 📌 RapidFuzz est utilisé pour des comparaisons de chaînes (fuzzy matching).

> - 📌 Les expressions régulières (regex) permettent d’identifier des formats spécifiques comme l’immatriculation, la
    date, etc.

## 🚀 Tester avec Postman

- **Option 1** : Importer directement les requêtes cURL (Postman > Import > Raw Text).
- **Option 2** : Créer manuellement une requête ```POST```, ajouter ```secret-key``` en *query string*, puis un champ
  ```image``` de type *file*.

## 🛠 Intégration

Vous pouvez facilement intégrer OCR_API dans vos projets en appelant les endpoints via Python, JavaScript, Java, ou tout
autre langage supportant HTTP.

## 🛠 Déploiement et Configuration

1. **Installation des dépendances** :

```
pip install -r requirements.txt
```

2. **Lancement local** :

```
python app.py
```

3. **Utilisation de Docker** :

```
docker build -t easy-ocr-api .
docker run -p 9000:9000 easy-ocr-api
```