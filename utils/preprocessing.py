from io import BytesIO
from time import time

from PIL.Image import Image, open, Resampling


def downscale_image_if_needed(pil_image: Image, max_size=1080):
    """
    Réduit la taille de l'image (PIL) si la dimension la plus grande > max_size.
    """
    w, h = pil_image.size
    if max(w, h) > max_size:
        ratio = max_size / float(max(w, h))
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        pil_image = pil_image.resize((new_w, new_h), resample=Resampling.LANCZOS)
    return pil_image


def extract_text_with_ocr(file_storage, reader, tolerance=0.2):
    """
    Lit le fichier image (FileStorage), le convertit en PIL, effectue un downscale si besoin,
    puis utilise EasyOCR (via l'instance reader) pour extraire le texte.
    Affiche le temps d'exécution de chaque étape.

    Retourne la liste des mots extraits dont la confiance est supérieure à 'tolerance'.
    """
    start_time = time()
    print("=== Début OCR ===")

    # Ouverture de l'image
    t0 = time()
    pil_image = open(file_storage)
    print(f"Ouverture image: {time() - t0:.2f} sec")

    # Downscale si besoin
    t1 = time()
    pil_image = downscale_image_if_needed(pil_image, max_size=1080)
    print(f"Downscale image: {time() - t1:.2f} sec")

    # Convertir PIL -> bytes
    t2 = time()
    img_bytes = BytesIO()
    pil_image.save(img_bytes, format='PNG')
    content = img_bytes.getvalue()
    print(f"Conversion en bytes: {time() - t2:.2f} sec")

    # OCR
    t3 = time()
    results = reader.readtext(content)  # detail=1 => [ ([x1,y1],[x2,y2]...), 'texte', conf ]
    print(f"Lecture EasyOCR: {time() - t3:.2f} sec")

    # Extraction filtrée
    extracted_text = [res[1] for res in results if res[2] > tolerance]
    print(f"=== Fin OCR (total: {time() - start_time:.2f} sec) ===")
    return extracted_text
