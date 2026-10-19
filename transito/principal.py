"""Função principal: captura as avenidas e devolve o trânsito de cada uma ou só a pior retenção."""

from datetime import datetime

from .analise import analisar_avenida, gravidade
from .captura import capturar_quadros
from .geometria import carregar_pecas, densificar, dimensionar_quadro, planejar_quadros
from .leitura import ler_pecas
from .local import localizar_retencao
from .parametros import EXTENSAO_MIN_M


def capturar_transito(arquivos_geojson, chave_api, pasta_prints=None, zoom=16,
                      largura=None, altura=None, escala_tela=2, passo_m=5.0,
                      raio_busca_m=6.0, margem_px=60, tolerancia_m=30.0,
                      ligar_pontas_m=2.0, lado_max_px=5120, navegador=None,
                      raio_direita_m=15.0, extensao_min_m=EXTENSAO_MIN_M):
    """
    Varre as avenidas inteiras (uma por GeoJSON de peças) e correlaciona o
    trânsito ao longo delas.

    zoom 16 com escala_tela 2 dá ~1,1 m por pixel em BH — folga para separar as
    pistas de sentidos opostos. `raio_busca_m` é o quanto a linha de trânsito
    pode estar deslocada do eixo OSM da peça; não passe da meia distância entre
    as pistas, senão começa a ler a do outro sentido. `raio_direita_m` é o mesmo,
    mas só à direita de quem anda (lado em que o Google desenha cada sentido),
    para os pontos que ficaram sem cor. `tolerancia_m` é o vão
    máximo (NORMAL/SEM_DADO) que ainda junta duas filas numa retenção só.
    `extensao_min_m` é o tamanho mínimo para uma retenção ser a maior da avenida
    (mais curta é fila de semáforo).
    `ligar_pontas_m` liga peças cujo fim coincide com o início de outra mesmo sem
    `segue_para` (0 para usar só o `segue_para` do corte).

    Sem `largura`/`altura`, o viewport fica do tamanho da área das avenidas
    (`dimensionar_quadro`), o que normalmente cobre tudo com um print só.
    `navegador`: Chromium já aberto, ver `capturar_quadros`.
    """
    avenidas = [carregar_pecas(caminho) for caminho in arquivos_geojson]
    pontos = [[densificar(p["coordenadas"], passo_m) for p in pecas] for pecas in avenidas]

    # Todas as avenidas no mesmo jogo de prints (um único carregamento de mapa)
    todas_pecas = [p for pecas in avenidas for p in pecas]
    todos_pontos = [pts for lista in pontos for pts in lista]
    lonlat = [(lon, lat) for pts in todos_pontos for lon, lat, _ in pts]
    auto_largura, auto_altura = dimensionar_quadro(lonlat, zoom, margem_px, escala_tela, lado_max_px)
    largura, altura = largura or auto_largura, altura or auto_altura
    quadros = planejar_quadros(lonlat, zoom, largura, altura, margem_px)
    imagens, carimbo = capturar_quadros(quadros, chave_api, zoom, largura, altura,
                                        escala_tela, pasta_prints, navegador=navegador)
    leituras = ler_pecas(todas_pecas, quadros, imagens, todos_pontos, zoom,
                         largura, altura, escala_tela, raio_busca_m, raio_direita_m)

    resultado = {}
    inicio = 0
    for caminho, pecas, pts in zip(arquivos_geojson, avenidas, pontos):
        nome = pecas[0]["name"]
        resultado[nome] = analisar_avenida(pecas, pts, leituras[inicio:inicio + len(pecas)],
                                           tolerancia_m, ligar_pontas_m, extensao_min_m)
        resultado[nome]["arquivo"] = str(caminho)
        inicio += len(pecas)

    return {
        "coletado_em": datetime.strptime(carimbo, "%Y%m%d%H%M%S").isoformat(),
        "fonte": "google_traffic_layer_imagem",
        "zoom": zoom,
        "quadros": len(quadros),
        "avenidas": resultado,
    }


def pior_transito(arquivos_geojson, chave_api, **opcoes):
    """
    Captura o trânsito (mesmas opções de `capturar_transito`) e devolve só a pior
    retenção entre todas as avenidas, com o local do início e do fim:
    {lat, lon, rua, rua_distancia_m, bairro} (ver `localizar_retencao`), os
    bairros que ela atravessa e o `sentido` (bairro para onde o trânsito vai).
    Coordenadas em [lat, lon], a ordem do Google Maps. Sem nenhuma retenção de
    pelo menos `extensao_min_m` (só filas de semáforo ou trânsito livre), `nivel`
    vem None e o resto vazio (o `coletado_em` continua dizendo de quando é a leitura).
    """
    dados = capturar_transito(arquivos_geojson, chave_api, **opcoes)
    candidatas = [(nome, av["maior_retencao"]) for nome, av in dados["avenidas"].items()
                  if av["maior_retencao"]]
    if not candidatas:
        return {"coletado_em": dados["coletado_em"], "avenida": None, "nivel": None,
                "extensao_m": 0.0, "metros_slow": 0.0, "metros_traffic_jam": 0.0,
                "metros_stopped": 0.0, "gravidade": 0.0, "pecas": [], "inicio": None,
                "fim": None, "bairros_percorridos": [], "sentido": None, "coordenadas": []}
    nome, r = max(candidatas, key=lambda c: gravidade(c[1]))
    local = localizar_retencao(dados["avenidas"][nome]["arquivo"], nome, r)
    return {
        "coletado_em": dados["coletado_em"],
        "avenida": nome,
        "nivel": r["nivel"],
        "extensao_m": r["extensao_m"],
        "metros_slow": r["metros_slow"],
        "metros_traffic_jam": r["metros_traffic_jam"],
        "metros_stopped": r["metros_stopped"],
        "gravidade": r["gravidade"],
        "pecas": r["pecas"],
        "inicio": {"lat": r["inicio"][1], "lon": r["inicio"][0], **local["inicio"]},
        "fim": {"lat": r["fim"][1], "lon": r["fim"][0], **local["fim"]},
        "bairros_percorridos": local["bairros_percorridos"],
        "sentido": local["sentido"],
        "coordenadas": [[lat, lon] for lon, lat in r["coordenadas"]],
    }

