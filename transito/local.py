"""Local de uma retenção: rua e bairro do início e do fim, bairros atravessados e sentido."""

import functools
from pathlib import Path

from .bairros import bairros_do_congestionamento, preparar_pecas
from .ruas import rua_mais_proxima, ruas_da_avenida, ruas_do_motorista


@functools.lru_cache(maxsize=None)
def _pecas_com_bairros(arquivo):
    """Peças com os bairros ao longo delas: calculado uma vez por arquivo e reaproveitado."""
    return preparar_pecas(arquivo)


def localizar_retencao(arquivo_pecas, avenida, retencao):
    """
    Onde fica uma retenção de `consolidar_retencoes` (coordenadas em [lon, lat]).

    Devolve {"inicio": {rua, rua_distancia_m, bairro}, "fim": {...},
    "bairros_percorridos": [...], "sentido": bairro para onde o trânsito vai}.
    A rua é a mais próxima da ponta, do lado do motorista, na peça em que a ponta
    está; fica None se a avenida não tem pasta de ruas (ver `ruas.pasta_da_avenida`).
    """
    (lon_i, lat_i), (lon_f, lat_f) = retencao["inicio"], retencao["fim"]
    peca_i, peca_f = retencao["pecas"][0], retencao["pecas"][-1]
    bairros = bairros_do_congestionamento(_pecas_com_bairros(str(Path(arquivo_pecas).resolve())),
                                          inicio=(lat_i, lon_i), fim=(lat_f, lon_f),
                                          peca_inicio=peca_i, peca_fim=peca_f)
    ruas = ruas_da_avenida(avenida)

    def ponta(lat, lon, peca, bairro):
        rua = rua_mais_proxima(lat, lon, ruas_do_motorista(ruas, peca)) if ruas else None
        return {"rua": rua["rua"] if rua else None,
                "rua_distancia_m": rua["distancia_m"] if rua else None,
                "bairro": bairro}

    return {
        "inicio": ponta(lat_i, lon_i, peca_i, bairros["bairro_inicio"]),
        "fim": ponta(lat_f, lon_f, peca_f, bairros["bairro_fim"]),
        "bairros_percorridos": bairros["bairros_percorridos"],
        "sentido": bairros["sentido"],
    }
