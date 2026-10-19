"""Avenida inteira: suaviza a leitura, monta trechos e percursos e consolida as retenções."""

import numpy as np

from .geometria import distancia_m
from .leitura import NOMES_CLASSE
from .parametros import CLASSE_PARA_SPEED, EXTENSAO_MIN_M, PESO_NIVEL


def _suavizar(classes, lacuna_max=3, trecho_min=5):
    """
    Preenche buracos curtos (-1) cercados pela mesma classe e absorve no vizinho
    mais longo os trechos de menos de `trecho_min` pontos (5 = 25 m com passo de
    5 m): o toco de cor de uma rua que cruza ou de uma alça não vira trânsito da
    avenida, nem muda o nível de uma fila.
    """
    c = classes.copy()
    n = len(c)
    i = 0
    while i < n:
        if c[i] != -1:
            i += 1
            continue
        j = i
        while j < n and c[j] == -1:
            j += 1
        if j - i <= lacuna_max and i > 0 and j < n and c[i - 1] == c[j]:
            c[i:j] = c[j]
        i = j
    while True:  # sempre o trecho mais curto primeiro, até nenhum ficar abaixo do mínimo
        inicios = np.flatnonzero(np.r_[True, c[1:] != c[:-1]])
        fins = np.r_[inicios[1:], n]
        tamanhos = fins - inicios
        if len(inicios) < 2 or tamanhos.min() >= trecho_min:
            return c
        k = int(tamanhos.argmin())
        vizinho = max((v for v in (k - 1, k + 1) if 0 <= v < len(inicios)), key=lambda v: tamanhos[v])
        c[inicios[k]:fins[k]] = c[inicios[vizinho]]


def montar_trechos(pontos, classes):
    """Agrupa pontos consecutivos de mesmo `speed` em trechos com início/fim em metros."""
    trechos = []
    for (lon, lat, dist), cls in zip(pontos, classes):
        speed = CLASSE_PARA_SPEED[NOMES_CLASSE[cls]] if cls >= 0 else "SEM_DADO"
        if trechos and trechos[-1]["speed"] == speed:
            trechos[-1]["fim_m"] = round(dist, 1)
            trechos[-1]["coordenadas"].append([lon, lat])
        else:
            inicio = trechos[-1]["fim_m"] if trechos else 0.0
            if trechos:
                trechos[-1]["coordenadas"].append([lon, lat])  # trechos encostados
            trechos.append({"speed": speed, "inicio_m": inicio, "fim_m": round(dist, 1),
                            "coordenadas": [[lon, lat]]})
    return trechos


def montar_percursos(pecas, ligar_pontas_m=2.0):
    """
    Encadeia as peças pelo `segue_para` em percursos contínuos, de cada peça sem
    antecessora até uma peça sem continuação. Bifurcações (principal/marginal,
    alças) geram um percurso por ramo. Ligações para peças fora do GeoJSON são
    ignoradas e ciclos são cortados.

    Com `ligar_pontas_m` > 0, também liga A → B quando o fim de A coincide com o
    início de B (corrige `segue_para` incompleto no corte). 0 desliga.
    """
    ids = [p["peca"] for p in pecas]
    seguintes = {p["peca"]: [s for s in p["segue_para"] if s in ids] for p in pecas}
    if ligar_pontas_m > 0:
        for a in pecas:
            fim = a["coordenadas"][-1]
            for b in pecas:
                ini = b["coordenadas"][0]
                if (b["peca"] != a["peca"] and b["peca"] not in seguintes[a["peca"]]
                        and distancia_m(fim[0], fim[1], ini[0], ini[1]) <= ligar_pontas_m):
                    seguintes[a["peca"]].append(b["peca"])
    com_antecessor = {s for lista in seguintes.values() for s in lista}

    percursos = []

    def andar(caminho):
        proximas = [s for s in seguintes[caminho[-1]] if s not in caminho]
        if not proximas:
            percursos.append(caminho)
            return
        for s in proximas:
            andar(caminho + [s])

    for pid in ids:
        if pid not in com_antecessor:
            andar([pid])
    # peças que só existem dentro de um ciclo (anel fechado sem ponta)
    while True:
        cobertas = {pid for caminho in percursos for pid in caminho}
        faltando = [pid for pid in ids if pid not in cobertas]
        if not faltando:
            break
        andar([faltando[0]])
    return percursos


def _juntar_percurso(ids_percurso, pontos_por_id, classes_por_id):
    """Concatena pontos e classes das peças do percurso, com distância acumulada."""
    pontos, classes, limites = [], [], []
    deslocamento = 0.0
    for k, pid in enumerate(ids_percurso):
        pts, cls = pontos_por_id[pid], classes_por_id[pid]
        pular = 1 if k > 0 else 0  # 1º ponto da peça = último da anterior
        for (lon, lat, d), c in zip(pts[pular:], cls[pular:]):
            pontos.append((lon, lat, deslocamento + d))
            classes.append(c)
        limites.append((pid, deslocamento, deslocamento + pts[-1][2]))
        deslocamento += pts[-1][2]
    return pontos, np.array(classes), limites


def consolidar_retencoes(trechos, limites, tolerancia_m=30.0):
    """
    Junta trechos congestionados (SLOW/TRAFFIC_JAM/STOPPED) do percurso separados
    por até `tolerancia_m` (de NORMAL ou SEM_DADO) numa retenção só — inclusive
    quando a fila passa de uma peça para a seguinte. O vão é curto de propósito: filas separadas por
    trânsito livre de verdade são retenções diferentes.

    `gravidade` = metros congestionados ponderados por `PESO_NIVEL`; o vão entre
    as filas não conta.
    """
    congestionados = [i for i, t in enumerate(trechos) if t["speed"] in PESO_NIVEL]
    retencoes = []
    for i in congestionados:
        if retencoes and trechos[i]["inicio_m"] - trechos[retencoes[-1][1]]["fim_m"] <= tolerancia_m:
            retencoes[-1][1] = i
        else:
            retencoes.append([i, i])
    retencoes = [trechos[a:b + 1] for a, b in retencoes]

    resultado = []
    for grupo in retencoes:
        inicio, fim = grupo[0]["inicio_m"], grupo[-1]["fim_m"]
        metros = dict.fromkeys(PESO_NIVEL, 0.0)
        coordenadas = []
        for t in grupo:
            if t["speed"] in metros:
                metros[t["speed"]] += t["fim_m"] - t["inicio_m"]
            coords = t["coordenadas"]
            coordenadas.extend(coords if not coordenadas else coords[1:])
        resultado.append({
            "inicio_m": inicio,
            "fim_m": fim,
            "extensao_m": round(fim - inicio, 1),
            # o nível mais grave que aparece na retenção
            "nivel": max((t["speed"] for t in grupo if t["speed"] in PESO_NIVEL), key=PESO_NIVEL.get),
            "metros_slow": round(metros["SLOW"], 1),
            "metros_traffic_jam": round(metros["TRAFFIC_JAM"], 1),
            "metros_stopped": round(metros["STOPPED"], 1),
            "gravidade": round(sum(metros[nivel] * peso for nivel, peso in PESO_NIVEL.items()), 1),
            "inicio": coordenadas[0],
            "fim": coordenadas[-1],
            "pecas": [pid for pid, a, b in limites if a < fim and b > inicio],
            "coordenadas": coordenadas,
        })
    return resultado


def gravidade(retencao):
    """Critério de pior retenção: a de maior `gravidade`; no empate, a mais longa."""
    return retencao["gravidade"], retencao["extensao_m"]


def analisar_avenida(pecas, pontos_por_peca, leituras, tolerancia_m=30.0, ligar_pontas_m=2.0,
                     extensao_min_m=EXTENSAO_MIN_M):
    """
    Trânsito por peça, por percurso e a maior retenção da avenida inteira. Os
    percursos trazem todas as retenções; a maior sai só das que têm pelo menos
    `extensao_min_m` (as mais curtas são fila de semáforo, ver `EXTENSAO_MIN_M`).
    """
    pontos_por_id = {p["peca"]: pts for p, pts in zip(pecas, pontos_por_peca)}
    classes_por_id = {p["peca"]: cls for p, cls in zip(pecas, leituras)}

    saida_pecas = []
    for p, pts, cls in zip(pecas, pontos_por_peca, leituras):
        suave = _suavizar(cls)
        saida_pecas.append({
            "peca": p["peca"], "comprimento_m": p["comprimento_m"],
            "segue_para": p["segue_para"],
            "cobertura": round(float((suave >= 0).mean()), 3),
            "trechos": montar_trechos(pts, suave),
        })

    saida_percursos = []
    for ids in montar_percursos(pecas, ligar_pontas_m):
        pontos, classes, limites = _juntar_percurso(ids, pontos_por_id, classes_por_id)
        suave = _suavizar(classes)  # suaviza já emendado: buraco na junção não quebra a fila
        trechos = montar_trechos(pontos, suave)
        saida_percursos.append({
            "pecas": ids,
            "comprimento_m": round(pontos[-1][2], 1),
            "cobertura": round(float((suave >= 0).mean()), 3),
            "trechos": trechos,
            "retencoes": consolidar_retencoes(trechos, limites, tolerancia_m),
        })

    candidatas = [dict(r, percurso=perc["pecas"])
                  for perc in saida_percursos for r in perc["retencoes"]
                  if r["extensao_m"] >= extensao_min_m]
    maior = max(candidatas, key=gravidade, default=None)
    return {"pecas": saida_pecas, "percursos": saida_percursos, "maior_retencao": maior}
