# Utiliser une image Python légère
#FROM python:3.11-slim

# Définir le répertoire de travail
#WORKDIR /app

# Copier uniquement les fichiers nécessaires
#COPY requirements.txt ./
#RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste des fichiers
#COPY . .

# Exposer le port Flask (par défaut 5000)
#EXPOSE 5000

# Lancer l'application Flask
#CMD ["python", "app.py"]


# ############## PROD

# Utiliser une image Python légère
FROM python:3.9-slim

# Désactiver l'écriture des fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copier seulement requirements.txt en premier pour profiter du cache Docker
COPY requirements.txt .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Exposer le port
EXPOSE 8080

# Lancer via Gunicorn (production)
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]