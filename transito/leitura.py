"""Leitura de cor: classifica os pixels do print e lê o trânsito em cada ponto das peças."""

import math

import numpy as np

from .geometria import metros_por_pixel, pixel_mundo
from .parametros import CORES_TRANSITO, TOLERANCIA_COR


NOMES_CLASSE = list(CORES_TRANSITO)
_REF_CORES = np.array([c for nome in NOMES_CLASSE for c in CORES_TRANSITO[nome]], dtype=np.float32)
_REF_CLASSE = np.array([i for i, nome in enumerate(NOMES_CLASSE) for _ in CORES_TRANSITO[nome]])


def _classificar_pixels(rgb):
    """rgb (..., 3) -> índice da classe em NOMES_CLASSE, ou -1 se não for cor de trânsito."""
    dist = np.linalg.norm(rgb[..., None, :].astype(np.float32) - _REF_CORES, axis=-1)
    melhor = dist.argmin(axis=-1)
    return np.where(dist.min(axis=-1) <= TOLERANCIA_COR, _REF_CLASSE[melhor], -1)


def _ler_disco(imagem, pixels_xy, raio_px, normais=None, lote=256, faixa_px=3):
    """
    Cor de trânsito da linha mais próxima de cada ponto (x, y) dentro do disco de
    raio `raio_px` — só na metade da direita, se vierem as `normais`. -1 onde não há.

    Vale a classe que mais aparece até `faixa_px` além do pixel colorido mais
    próximo, e não só a desse pixel: assim conta o miolo da linha, e não a borda,
    que no vermelho e no vermelho-escuro tem cores quase iguais.
    """
    altura, largura = imagem.shape[:2]
    r = int(math.ceil(raio_px))
    dy, dx = np.mgrid[-r:r + 1, -r:r + 1]
    dentro = dx ** 2 + dy ** 2 <= raio_px ** 2
    dx, dy = dx[dentro], dy[dentro]
    ordem = np.argsort(dx ** 2 + dy ** 2, kind="stable")
    dx, dy = dx[ordem], dy[ordem]
    dist = np.hypot(dx, dy)

    resultado = np.full(len(pixels_xy), -1)
    for ini in range(0, len(pixels_xy), lote):  # em lotes: com o disco grande, pesa na memória
        xy = pixels_xy[ini:ini + lote]
        px = np.rint(xy[:, 0]).astype(int)[:, None] + dx
        py = np.rint(xy[:, 1]).astype(int)[:, None] + dy
        valido = (px >= 0) & (px < largura) & (py >= 0) & (py < altura)
        if normais is not None:
            n = normais[ini:ini + lote]
            valido &= dx * n[:, :1] + dy * n[:, 1:] >= 0
        rgb = imagem[np.clip(py, 0, altura - 1), np.clip(px, 0, largura - 1), :3]
        classes = np.where(valido, _classificar_pixels(rgb), -1)

        tem_cor = classes >= 0
        linhas = np.arange(len(classes))
        primeiro = tem_cor.argmax(axis=1)  # vizinhos já estão ordenados por distância
        na_faixa = tem_cor & (dist <= dist[primeiro][:, None] + faixa_px)
        votos = np.stack([(na_faixa & (classes == k)).sum(axis=1)
                          for k in range(len(NOMES_CLASSE))], axis=1).astype(float)
        votos[linhas, classes[linhas, primeiro]] += 0.5  # empate: fica a do pixel mais próximo
        resultado[ini:ini + lote] = np.where(tem_cor.any(axis=1), votos.argmax(axis=1), -1)
    return resultado


def ler_classes(imagem, pixels_xy, raio_px, normais=None, raio_direita_px=0.0):
    """
    Para cada ponto (x, y) em pixels da imagem, procura no disco de raio `raio_px`
    a linha com cor de trânsito mais próxima do ponto (ver `_ler_disco`). Pegar a
    mais próxima (e não a maioria do disco) evita ler a pista do sentido oposto
    quando as duas estão perto.

    Com `normais` (vetor unitário para a direita de quem anda, em cada ponto), os
    pontos que ficaram sem cor são procurados de novo até `raio_direita_px`, só do
    lado direito: o Google desenha cada sentido deslocado para a direita do eixo
    (medido na Amazonas: 96–100% dos casos), e o sentido oposto fica à esquerda.
    """
    classes = _ler_disco(imagem, pixels_xy, raio_px)
    if normais is not None and raio_direita_px > raio_px:
        sem_cor = classes < 0
        classes[sem_cor] = _ler_disco(imagem, pixels_xy[sem_cor], raio_direita_px, normais[sem_cor])
    return classes


def ler_pecas(pecas, quadros, imagens, pontos_por_peca, zoom, largura, altura,
              escala_tela=2, raio_busca_m=6.0, raio_direita_m=15.0):
    """
    Classe de trânsito bruta (sem suavizar) de cada ponto de cada peça, a partir dos
    prints. Pontos sem cor a `raio_busca_m` são procurados até `raio_direita_m`, só
    à direita do sentido da peça (ver `ler_classes`).
    """
    todos = [pt for pontos in pontos_por_peca for pt in pontos]
    classes = np.full(len(todos), -1)
    lat_media = float(np.mean([pt[1] for pt in todos]))
    m_px = metros_por_pixel(lat_media, zoom, escala_tela)

    # posição no mundo e normal para a direita de quem anda (o y da tela cresce para baixo)
    xy_mundo, normais = [], []
    for pontos in pontos_por_peca:
        xy = np.array([pixel_mundo(lon, lat, zoom) for lon, lat, _ in pontos])
        if len(xy) < 2:
            normal = np.full((len(xy), 2), np.nan)
        else:
            tangente = np.gradient(xy, axis=0)
            tangente /= np.maximum(np.linalg.norm(tangente, axis=1, keepdims=True), 1e-9)
            normal = np.column_stack([-tangente[:, 1], tangente[:, 0]])
        xy_mundo.append(xy)
        normais.append(normal)
    xy_mundo, normais = np.vstack(xy_mundo), np.vstack(normais)

    for quadro, imagem in zip(quadros, imagens):
        idx = quadro["indices"]
        cx, cy = quadro["centro_px_mundo"]
        pix = np.column_stack([(xy_mundo[idx, 0] - cx + largura / 2) * escala_tela,
                               (xy_mundo[idx, 1] - cy + altura / 2) * escala_tela])
        classes[idx] = ler_classes(imagem, pix, raio_busca_m / m_px,
                                   normais[idx], raio_direita_m / m_px)

    leituras = []
    inicio = 0
    for pontos in pontos_por_peca:
        leituras.append(classes[inicio:inicio + len(pontos)])
        inicio += len(pontos)
    return leituras
