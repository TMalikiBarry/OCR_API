# Utiliser une image Python légère
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier uniquement les fichiers nécessaires
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste des fichiers
COPY . .

# Exposer le port Flask (par défaut 5000)
EXPOSE 5000

# Lancer l'application Flask
CMD ["python", "app.py"]