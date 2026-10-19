"""
Ruas: a rua mais próxima do início e do fim de um congestionamento, do lado do
motorista (adaptado de `bairros e ruas/ruas_av.py`).

Os GeoJSON de ruas de cada avenida ficam em `bairros e ruas/ruas/<avenida>/`,
um por lado (`*_lado_direito`, `*_lado_esquerdo`, `*_lado_travessia`). Cada rua
traz em `lados_por_peca` o lado em que fica em relação a cada peça, no sentido
do tráfego dela; valem as do lado direito, o do meio-fio da pista, e as que
atravessam a peça. (O ruas_av.py decidia o lado pelo centro de todas as peças,
o que só acerta em anel como o Contorno: na Amazonas trocava o lado das pistas
principais, e não achava a pista quando a fila passava de uma peça para outra.)
"""

import functools
import json
import math
import re
import unicodedata
from pathlib import Path

PASTA_RUAS = Path(__file__).resolve().parent.parent / "bairros e ruas" / "ruas"


# ---------- geometria ----------

def _xy(lon, lat, lat0):
    return (lon * 111320.0 * math.cos(math.radians(lat0)), lat * 110540.0)


def _dist_ponto_segmento(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def _mais_proximo_na_linha(lon, lat, coords):
    """Distância (m) do ponto até a LineString, índice do segmento e direção do segmento."""
    lat0 = lat
    p = _xy(lon, lat, lat0)
    melhor = (float("inf"), 0, (0.0, 0.0))
    for i in range(len(coords) - 1):
        a = _xy(coords[i][0], coords[i][1], lat0)
        b = _xy(coords[i + 1][0], coords[i + 1][1], lat0)
        d, _ = _dist_ponto_segmento(p, a, b)
        if d < melhor[0]:
            melhor = (d, i, (b[0] - a[0], b[1] - a[1]))
    return melhor


# ---------- carga ----------

def carregar_ruas(caminho_geojson):
    with open(caminho_geojson, encoding="utf-8") as fh:
        return json.load(fh)["features"]


def pasta_da_avenida(nome):
    """Pasta das ruas pelo nome da avenida: "Avenida dos Andradas" -> ruas/andradas."""
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^avenida\s+", "", s)
    s = re.sub(r"^(do|dos|da|das|de)\s+", "", s)
    return PASTA_RUAS / s.replace(" ", "_")


@functools.lru_cache(maxsize=None)
def ruas_da_avenida(nome):
    """Ruas dos três lados da avenida, lidas uma vez só; vazio se ela não tem pasta de ruas."""
    pasta = pasta_da_avenida(nome)
    return [f for arquivo in sorted(pasta.glob("*_lado_*.geojson")) for f in carregar_ruas(arquivo)]


# ---------- lógica ----------

def ruas_do_motorista(ruas, peca):
    """
    Ruas que quem anda na `peca` encontra: as do lado direito dela e as travessias
    que cortam a peça (no `lados_por_peca` elas aparecem do lado esquerdo, porque
    se ligam pelo canteiro). Se nenhuma dessas tem nome, todas as da avenida.
    """
    def encontra(f):
        lados = f["properties"].get("lados_por_peca") or {}
        return peca in lados and (lados[peca].get("lado") == "direito"
                                  or f["properties"].get("lado") == "travessia")

    escolhidas = [f for f in ruas if encontra(f)]
    return escolhidas if any(f["properties"].get("name") for f in escolhidas) else ruas


def rua_mais_proxima(lat, lon, ruas, ignorar_sem_nome=True):
    """{rua, distancia_m, u, v} da rua mais próxima do ponto, ou None se não há nenhuma."""
    melhor = None
    for f in ruas:
        nome = f["properties"].get("name")
        if ignorar_sem_nome and not nome:
            continue
        d, _, _ = _mais_proximo_na_linha(lon, lat, f["geometry"]["coordinates"])
        if melhor is None or d < melhor[0]:
            melhor = (d, nome, f["properties"])
    if melhor is None:
        return None
    d, nome, props = melhor
    if isinstance(nome, list):  # o OSM junta numa via só trechos com nomes diferentes
        nome = " / ".join(nome)
    return {"rua": nome, "distancia_m": round(d, 1), "u": props.get("u"), "v": props.get("v")}
