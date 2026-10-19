"""Geometria: peças do GeoJSON, distâncias, Web Mercator e planejamento dos prints."""

import json
import math
from pathlib import Path

import numpy as np


def carregar_pecas(caminho_geojson):
    """Lê um GeoJSON de peças e devolve lista de dicts com coordenadas (lon, lat)."""
    dados = json.loads(Path(caminho_geojson).read_text(encoding="utf-8"))
    pecas = []
    for f in dados["features"]:
        props = f["properties"]
        pecas.append({
            "peca": props.get("peca"),
            "name": props.get("name"),
            "comprimento_m": props.get("comprimento_m"),
            "segue_para": props.get("segue_para", []),
            "coordenadas": [tuple(c) for c in f["geometry"]["coordinates"]],
        })
    return pecas


def distancia_m(lon1, lat1, lon2, lat2):
    """Equirretangular — suficiente para segmentos curtos dentro de BH."""
    lat_media = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(lat_media) * 6371008.8
    dy = math.radians(lat2 - lat1) * 6371008.8
    return math.hypot(dx, dy)


def densificar(coordenadas, passo_m=5.0):
    """Pontos a cada `passo_m` ao longo da linha: [(lon, lat, distancia_acumulada_m)]."""
    pontos = [(coordenadas[0][0], coordenadas[0][1], 0.0)]
    acumulado = 0.0
    proximo = passo_m
    for (lon1, lat1), (lon2, lat2) in zip(coordenadas, coordenadas[1:]):
        d = distancia_m(lon1, lat1, lon2, lat2)
        if d == 0:
            continue
        while proximo <= acumulado + d:
            t = (proximo - acumulado) / d
            pontos.append((lon1 + t * (lon2 - lon1), lat1 + t * (lat2 - lat1), proximo))
            proximo += passo_m
        acumulado += d
    if acumulado - pontos[-1][2] > 1e-6:
        pontos.append((coordenadas[-1][0], coordenadas[-1][1], acumulado))
    return pontos


def pixel_mundo(lon, lat, zoom):
    """Web Mercator: pixel (CSS) no mundo de 256 * 2^zoom, igual à Maps JS API."""
    escala = 256 * 2 ** zoom
    seno = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    x = (lon + 180) / 360 * escala
    y = (0.5 - math.log((1 + seno) / (1 - seno)) / (4 * math.pi)) * escala
    return x, y


def _lonlat_do_pixel_mundo(x, y, zoom):
    escala = 256 * 2 ** zoom
    lon = x / escala * 360 - 180
    n = math.pi - 2 * math.pi * y / escala
    lat = math.degrees(math.atan(math.sinh(n)))
    return lon, lat


def metros_por_pixel(lat, zoom, escala_tela=1):
    return 156543.03392 * math.cos(math.radians(lat)) / 2 ** zoom / escala_tela


def planejar_quadros(pontos_lonlat, zoom, largura, altura, margem_px=60):
    """
    Cobre os pontos com uma grade de quadros (prints). Devolve só os quadros que
    têm algum ponto, cada um com o centro (lon, lat) e o índice dos pontos dentro
    da área útil (descontada a margem, onde ficam logo e termos do Google).
    """
    xy = np.array([pixel_mundo(lon, lat, zoom) for lon, lat in pontos_lonlat])
    util_x, util_y = largura - 2 * margem_px, altura - 2 * margem_px
    x0, y0 = xy[:, 0].min(), xy[:, 1].min()
    col = ((xy[:, 0] - x0) // util_x).astype(int)
    lin = ((xy[:, 1] - y0) // util_y).astype(int)

    quadros = []
    for c, l in sorted(set(zip(col.tolist(), lin.tolist())), key=lambda t: (t[1], t[0])):
        cx = x0 + c * util_x + util_x / 2
        cy = y0 + l * util_y + util_y / 2
        # float do Python: no numpy 2, repr(np.float64) vira "np.float64(...)" e quebra o JS do mapa
        lon, lat = _lonlat_do_pixel_mundo(float(cx), float(cy), zoom)
        indices = np.nonzero((col == c) & (lin == l))[0]
        quadros.append({"centro": (lon, lat), "centro_px_mundo": (cx, cy), "indices": indices})
    return quadros


def dimensionar_quadro(pontos_lonlat, zoom, margem_px=60, escala_tela=2,
                       lado_max_px=5120, megapixels_max=25):
    """
    Viewport (px CSS) para cobrir as avenidas com o mínimo de prints — de
    preferência um só, do tamanho da área dos pontos mais a margem, que poupa a
    espera de tiles de cada quadro. Se o print passar de `megapixels_max` (ou um
    lado de `lado_max_px`), divide a área em colunas/linhas iguais até caber: com
    ~100 MP o Chromium deixa blocos do mapa em branco; ~25 MP sai completo.
    """
    xy = np.array([pixel_mundo(lon, lat, zoom) for lon, lat in pontos_lonlat])
    extensao = np.ptp(xy, axis=0)
    area_max = megapixels_max * 1e6 / escala_tela ** 2
    colunas = linhas = 1
    while True:
        # +2: o ponto mais distante precisa cair dentro da área útil, não na divisa do quadro
        largura = int(math.ceil(extensao[0] / colunas)) + 2 * margem_px + 2
        altura = int(math.ceil(extensao[1] / linhas)) + 2 * margem_px + 2
        if largura * altura <= area_max and max(largura, altura) <= lado_max_px:
            return largura, altura
        if largura >= altura:
            colunas += 1
        else:
            linhas += 1
