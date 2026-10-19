"""Conferência: marca os pontos lidos sobre o print, para ver se a leitura bate com o mapa."""

from PIL import Image


def desenhar_conferencia(imagem, pixels_xy, classes, caminho):
    """Marca os pontos lidos sobre o print (preto = sem dado) para conferir o alinhamento."""
    from PIL import ImageDraw
    img = Image.fromarray(imagem).convert("RGB")
    d = ImageDraw.Draw(img)
    cores = {-1: (0, 0, 0), 0: (0, 120, 0), 1: (200, 100, 0), 2: (160, 0, 0), 3: (80, 0, 0)}
    for (x, y), c in zip(pixels_xy, classes):
        d.ellipse([x - 2, y - 2, x + 2, y + 2], outline=cores[int(c)])
    img.save(caminho)
