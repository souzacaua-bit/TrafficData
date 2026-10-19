"""
Bairros: lê um congestionamento em termos de bairro: onde começa, onde termina,
quais bairros atravessa e para que bairro o trânsito está indo (sentido).

Trabalha sobre os GeoJSON de peças (cada peça orientada no sentido do
tráfego, com `peca` e `segue_para`) e a base Bairro Popular do BHMap
(BAIRRO_POPULAR.json, na pasta `bairros e ruas`: 493 bairros de Belo Horizonte,
nome na coluna NOME, em EPSG:31983). Outra camada de polígonos pode ser
passada em `fonte_bairros`.

O Bairro Popular cobre só BH: trecho de avenida a mais de `fora_m` de
qualquer bairro (ex.: Teresa Cristina em Contagem) sai como "Fora de BH".

Uso:
    from transito.bairros import preparar_pecas, bairros_do_congestionamento

    pecas = preparar_pecas("google_cortes/pecas_Avenida_Brasil.geojson")
    info = bairros_do_congestionamento(pecas,
                                       inicio=(-19.9323, -43.9359),
                                       fim=(-19.9289, -43.9300))
    # {'bairro_inicio': 'Savassi', 'bairro_fim': 'Funcionários',
    #  'bairros_percorridos': ['Savassi', 'Boa Viagem', 'Savassi', 'Funcionários'],
    #  'sentido': 'Santa Efigênia', 'distancia_sentido_m': 192.8}

Pontos em tupla são (lat, lon). GeoJSON e TomTom entregam [lon, lat]:
inverta antes ou passe {"lat": ..., "lon": ...}.

O bairro de cada ponto é o do lado direito da pista (onde está o motorista),
para não cair na divisa quando a avenida separa dois bairros.
"""
import copy
import functools
import heapq
import json
import math
import os

import geopandas as gpd
import numpy as np
import shapely
from pandas.api.types import is_string_dtype
from pyproj import Transformer
from shapely.geometry import LineString, Point

CRS_METRICO = "EPSG:31983"
_para_metrico = Transformer.from_crs("EPSG:4326", CRS_METRICO, always_xy=True)

BAIRRO_POPULAR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "bairros e ruas", "BAIRRO_POPULAR.json")
COLUNA_BAIRRO_POPULAR = "NOME"
FORA_DA_BASE = "Fora de BH"


# ---------------------------------------------------------------- bairros

def carregar_bairros(fonte=None, coluna_nome=None):
    """GeoDataFrame em EPSG:31983 com colunas `bairro` e `geometry`.
    `fonte`: caminho de arquivo ou GeoDataFrame; None usa o Bairro Popular,
    lido do disco uma vez só e reaproveitado."""
    if fonte is None:
        return _bairro_popular().copy()
    gdf = fonte if isinstance(fonte, gpd.GeoDataFrame) else gpd.read_file(fonte)
    if gdf.crs is None:
        # sem CRS declarado: em graus é WGS84; em metros, o SIRGAS 2000 / UTM 23S do BHMap
        x0, y0, x1, y1 = gdf.total_bounds
        em_graus = -180 <= x0 <= x1 <= 180 and -90 <= y0 <= y1 <= 90
        gdf = gdf.set_crs("EPSG:4326" if em_graus else CRS_METRICO)
    gdf = gdf.to_crs(CRS_METRICO)
    geom = gdf.geometry.name

    if coluna_nome is None:
        conhecidas = ("bairro", "nome_bairro", "nomebairro", "nome")
        por_nome = {str(c).lower(): c for c in gdf.columns if c != geom}
        candidatas = [por_nome[n] for n in conhecidas if n in por_nome]
        if not candidatas:
            # pandas 3 guarda texto como dtype "str", não object
            candidatas = [c for c in gdf.columns if c != geom and is_string_dtype(gdf[c])]
        if not candidatas:
            raise ValueError("Não encontrei a coluna com o nome do bairro; informe coluna_nome.")
        coluna_nome = candidatas[0]

    saida = gdf[[coluna_nome, geom]].rename(columns={coluna_nome: "bairro"})
    if geom != "geometry":
        saida = saida.rename_geometry("geometry")
    saida["bairro"] = saida["bairro"].astype(str).str.strip()
    return saida


@functools.lru_cache(maxsize=1)
def _bairro_popular():
    return carregar_bairros(BAIRRO_POPULAR, COLUNA_BAIRRO_POPULAR)


def _amostrar(linha, passo_m, offset_m):
    """Distâncias a cada ~`passo_m` ao longo da linha e os pontos a
    `offset_m` metros à direita delas (lado do motorista), de uma vez só."""
    L = linha.length
    n = max(int(L // passo_m), 1)
    d = L * np.arange(n + 1) / n
    p, a, b = (shapely.get_coordinates(shapely.line_interpolate_point(linha, x))
               for x in (d, np.maximum(d - 2.0, 0.0), np.minimum(d + 2.0, L)))
    dx, dy = (b - a).T
    norma = np.hypot(dx, dy)
    norma[norma == 0] = 1.0
    return d.tolist(), shapely.points(p[:, 0] + dy / norma * offset_m, p[:, 1] - dx / norma * offset_m)


def _rotular(pontos, bairros, fora_m):
    """Bairro de cada ponto: o polígono que o contém; senão o mais próximo
    até `fora_m` (divisa, fresta entre polígonos); senão FORA_DA_BASE."""
    nomes = bairros["bairro"].to_numpy(dtype=object)
    rotulos = np.full(len(pontos), FORA_DA_BASE, dtype=object)
    i_pt, i_b = bairros.sindex.query(pontos, predicate="within")
    i_pt, primeiro = np.unique(i_pt, return_index=True)  # polígonos sobrepostos: vale o primeiro
    rotulos[i_pt] = nomes[i_b[primeiro]]
    faltando = np.setdiff1d(np.arange(len(pontos)), i_pt)
    if len(faltando):
        i_pt, i_b = bairros.sindex.nearest(pontos[faltando], max_distance=fora_m, return_all=False)
        rotulos[faltando[i_pt]] = nomes[i_b]
    return rotulos.tolist()


def _limpar(itens, minimo_m):
    """Absorve trechos curtos (quina de bairro, ruído de borda) no vizinho."""
    while len(itens) > 1:
        k = min(range(len(itens)), key=lambda k: itens[k]["fim_m"] - itens[k]["inicio_m"])
        if itens[k]["fim_m"] - itens[k]["inicio_m"] >= minimo_m:
            break
        if k == 0:
            itens[1]["inicio_m"] = itens[0]["inicio_m"]
        elif k == len(itens) - 1:
            itens[k - 1]["fim_m"] = itens[k]["fim_m"]
        elif itens[k - 1]["bairro"] == itens[k + 1]["bairro"]:
            itens[k - 1]["fim_m"] = itens.pop(k + 1)["fim_m"]
        else:
            # entre dois bairros diferentes a divisa fica no meio do trecho curto
            itens[k - 1]["fim_m"] = itens[k + 1]["inicio_m"] = (itens[k]["inicio_m"] + itens[k]["fim_m"]) / 2
        del itens[k]

    for it in itens:
        it["inicio_m"] = round(it["inicio_m"], 1)
        it["fim_m"] = round(it["fim_m"], 1)
    return itens


def bairros_ao_longo(linha, bairros, passo_m=25.0, offset_m=20.0, minimo_m=60.0, fora_m=50.0):
    """Intervalos contíguos [{bairro, inicio_m, fim_m}] cobrindo a linha
    (EPSG:31983, orientada no sentido do tráfego) de 0 ao comprimento."""
    dists, pontos = _amostrar(linha, passo_m, offset_m)
    rotulos = _rotular(pontos, bairros, fora_m)
    # a divisa fica no meio das duas amostras em que o bairro muda
    trocas = [i for i in range(1, len(rotulos)) if rotulos[i] != rotulos[i - 1]]
    cortes = [0.0] + [(dists[i - 1] + dists[i]) / 2 for i in trocas] + [linha.length]
    nomes = [rotulos[0]] + [rotulos[i] for i in trocas]
    return _limpar([{"bairro": b, "inicio_m": a, "fim_m": f}
                    for b, a, f in zip(nomes, cortes, cortes[1:])], minimo_m)


def bairro_em(intervalos, dist_m):
    for it in intervalos:
        if it["inicio_m"] <= dist_m <= it["fim_m"] + 1e-6:
            return it["bairro"]
    return intervalos[-1]["bairro"] if intervalos else None


# ---------------------------------------------------------------- peças

def _ler_fc(fonte):
    if isinstance(fonte, dict):
        return fonte
    with open(fonte, encoding="utf-8") as f:
        return json.load(f)


def _rumo(linha, d):
    """Azimute (0 = norte) da linha em `d`, numa janela de 20 m como em google_cortes._virada."""
    a = linha.interpolate(max(d - 20.0, 0.0))
    b = linha.interpolate(min(d + 20.0, linha.length))
    return math.degrees(math.atan2(b.x - a.x, b.y - a.y)) % 360


def _dif_ang(a, b):
    return abs((a - b + 180) % 360 - 180)


def _emendas_geometricas(pecas, ident, emenda_m):
    """Peças que começam onde esta termina, no mesmo rumo. Cobre os casos
    em que `segue_para` ficou vazio ou aponta para peça fora do arquivo."""
    pc = pecas[ident]
    fim = pc["linha"].coords[-1]
    return [outro for outro, o in pecas.items()
            if outro != ident and math.dist(fim, o["linha"].coords[0]) <= emenda_m
            and _dif_ang(pc["rumo_fim"], o["rumo_inicio"]) < 60]


def preparar_pecas(fonte_pecas, fonte_bairros=None, coluna_nome=None,
                   passo_m=25.0, offset_m=20.0, minimo_m=60.0, emenda_m=10.0,
                   virada_max=135.0, fora_m=50.0):
    """dict peca -> {id, linha (31983), comprimento_m, rumo_inicio, rumo_fim,
    segue_para, seguintes, bairros}.
    Rodar uma vez por avenida e reaproveitar a cada consulta. Sem
    `fonte_bairros`, usa o Bairro Popular.

    Ligações de `segue_para` que viram mais de `virada_max` graus (meia-volta
    onde as duas pistas se encontram num nó só) ficam de fora de `seguintes`,
    como em google_cortes.cortar_retornos."""
    fc = _ler_fc(fonte_pecas)
    bairros = carregar_bairros(fonte_bairros, coluna_nome)

    pecas = {}
    for f in fc["features"]:
        prop = f["properties"]
        lonlat = np.asarray(f["geometry"]["coordinates"], dtype=float)
        linha = LineString(np.column_stack(_para_metrico.transform(lonlat[:, 0], lonlat[:, 1])))
        pecas[prop["peca"]] = {
            "id": prop["peca"],
            "linha": linha,
            "comprimento_m": linha.length,
            "rumo_inicio": _rumo(linha, 0.0),
            "rumo_fim": _rumo(linha, linha.length),
            "segue_para": list(prop.get("segue_para") or []),
            "bairros": bairros_ao_longo(linha, bairros, passo_m, offset_m, minimo_m, fora_m),
        }

    for ident, pc in pecas.items():
        ligadas = [s for s in pc["segue_para"] if s in pecas and s != ident
                   and _dif_ang(pc["rumo_fim"], pecas[s]["rumo_inicio"]) <= virada_max]
        pc["seguintes"] = ligadas or _emendas_geometricas(pecas, ident, emenda_m)
    return pecas


def anotar_geojson(fonte_pecas, pecas, destino=None):
    """Copia o GeoJSON de peças com a propriedade `bairros` em cada feature."""
    fc = copy.deepcopy(_ler_fc(fonte_pecas))
    for f in fc["features"]:
        pc = pecas.get(f["properties"]["peca"])
        if pc:
            f["properties"]["bairros"] = pc["bairros"]
    if destino:
        with open(destino, "w", encoding="utf-8") as arq:
            json.dump(fc, arq, ensure_ascii=False, indent=2)
    return fc


# ---------------------------------------------------------------- congestionamento

def _ponto(p):
    """(lat, lon) ou dict com lat/lon -> Point em EPSG:31983."""
    if isinstance(p, dict):
        lat = p.get("lat", p.get("latitude"))
        lon = p.get("lon", p.get("lng", p.get("longitude")))
        if lat is None or lon is None:
            raise ValueError(f"Ponto sem lat/lon: {p!r}")
    else:
        lat, lon = p
    return Point(*_para_metrico.transform(lon, lat))


def _candidatas(pecas, ponto, tolerancia_m, peca=None, distancia_max_m=None):
    """[(peca, distancia_ao_eixo, posicao_na_peca)]."""
    if peca is not None:
        if peca not in pecas:
            raise KeyError(f"Peça {peca!r} não está no arquivo de peças.")
        linha = pecas[peca]["linha"]
        return [(peca, linha.distance(ponto), linha.project(ponto))]
    dists = [(pc["linha"].distance(ponto), ident) for ident, pc in pecas.items()]
    mais_perto = min(dists)
    if distancia_max_m is not None and mais_perto[0] > distancia_max_m:
        raise ValueError(
            f"Ponto a {mais_perto[0]:.0f} m da peça mais próxima ({mais_perto[1]}): fora da "
            "avenida ou com lat/lon trocados (tupla é (lat, lon); GeoJSON/TomTom usam [lon, lat]).")
    perto = [x for x in dists if x[0] <= tolerancia_m] or [mais_perto]
    return [(ident, d, pecas[ident]["linha"].project(ponto)) for d, ident in perto]


def _caminho(pecas, a, pos_a, b, pos_b, limite_m=30000.0):
    """Menor percurso de (a, pos_a) até (b, pos_b) seguindo o tráfego.
    Retorna (distancia_m, [peças]) ou None."""
    if a == b and pos_b >= pos_a:
        return pos_b - pos_a, [a]
    resto = pecas[a]["comprimento_m"] - pos_a
    fila = [(resto, s, (a, s)) for s in pecas[a]["seguintes"]]
    heapq.heapify(fila)
    visto = set()
    while fila:
        custo, atual, rota = heapq.heappop(fila)
        if custo > limite_m:
            break
        if atual == b:
            return custo + pos_b, list(rota)
        if atual in visto:
            continue
        visto.add(atual)
        prox = custo + pecas[atual]["comprimento_m"]
        for s in pecas[atual]["seguintes"]:
            if s not in visto:
                heapq.heappush(fila, (prox, s, rota + (s,)))
    return None


def _bairros_percorridos(pecas, rota, pos_a, pos_b):
    sequencia = []
    for k, ident in enumerate(rota):
        de = pos_a if k == 0 else 0.0
        ate = pos_b if k == len(rota) - 1 else pecas[ident]["comprimento_m"]
        nomes = [it["bairro"] for it in pecas[ident]["bairros"]
                 if it["fim_m"] > de and it["inicio_m"] < ate] or [bairro_em(pecas[ident]["bairros"], de)]
        for nome in nomes:
            if not sequencia or sequencia[-1] != nome:
                sequencia.append(nome)
    return sequencia


def _pontes(pecas, ident, ponte_m=200.0, virada_max=135.0, frente_max=75.0):
    """[(peca, salto_m)] que continuam esta por cima de um buraco no corte (praça,
    rotatória: na Raul Soares a Amazonas para e recomeça ~135 m depois). Valem
    as peças que começam até `ponte_m` do fim desta, à frente dela (até
    `frente_max` graus do rumo) e sem ser a pista de volta (virada até
    `virada_max`)."""
    pc = pecas[ident]
    x0, y0 = pc["linha"].coords[-1]
    saida = []
    for outro, o in pecas.items():
        x1, y1 = o["linha"].coords[0]
        salto = math.dist((x0, y0), (x1, y1))
        if outro == ident or salto > ponte_m or _dif_ang(pc["rumo_fim"], o["rumo_inicio"]) > virada_max:
            continue
        rumo_ate = math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360
        if salto <= 5.0 or _dif_ang(pc["rumo_fim"], rumo_ate) <= frente_max:
            saida.append((outro, salto))
    return saida


def _proximo_bairro(pecas, ident, pos, atual, alcance_m, virada_max=135.0, curta_m=50.0):
    """Primeiro bairro diferente de `atual` à frente de (ident, pos),
    seguindo o tráfego até `alcance_m`. Retorna (bairro, distancia_m) ou None.

    Não entra em retorno para a pista oposta, nem quando a meia-volta é
    feita em duas viradas por uma peça curta (< `curta_m`): o rumo de
    referência só é atualizado ao sair de uma peça longa. Peça sem
    `seguintes` continua pelas `_pontes`, se houver."""
    fila = [(0.0, ident, pos, None)]
    visto = set()
    melhor = None
    while fila:
        base, pc_id, de, rumo_ref = heapq.heappop(fila)
        if base > alcance_m or (melhor and base >= melhor[1]):
            break
        if pc_id in visto:
            continue
        visto.add(pc_id)
        pc = pecas[pc_id]
        for it in pc["bairros"]:
            if it["fim_m"] <= de or it["bairro"] == atual:
                continue
            d = base + max(it["inicio_m"] - de, 0.0)
            if d <= alcance_m and (melhor is None or d < melhor[1]):
                melhor = (it["bairro"], d)
            break
        if rumo_ref is None or pc["comprimento_m"] - de >= curta_m:
            rumo_ref = pc["rumo_fim"]
        prox = base + pc["comprimento_m"] - de
        for s, salto in [(s, 0.0) for s in pc["seguintes"]] or _pontes(pecas, pc_id):
            if s not in visto and _dif_ang(rumo_ref, pecas[s]["rumo_inicio"]) <= virada_max:
                heapq.heappush(fila, (prox + salto, s, 0.0, rumo_ref))
    return (melhor[0], round(melhor[1], 1)) if melhor else None


def bairros_do_congestionamento(pecas, inicio, fim, peca_inicio=None, peca_fim=None,
                                tolerancia_m=35.0, alcance_sentido_m=3000.0,
                                distancia_max_m=200.0):
    """Bairros de um congestionamento.

    `inicio` é a cauda da fila e `fim` é a cabeça, no sentido do tráfego,
    como (lat, lon) ou dict com lat/lon. Se as peças forem conhecidas, passe
    `peca_inicio`/`peca_fim`; senão são escolhidas pelo par de peças mais
    próximas que tenha percurso válido de `inicio` até `fim` (isso descarta
    a pista do sentido oposto).

    `sentido` é o primeiro bairro diferente do bairro da cabeça da fila,
    procurado à frente até `alcance_sentido_m`, sem entrar em retorno para
    a pista oposta. Se a avenida não muda de bairro nesse alcance, ou se o
    arquivo de peças acaba antes, o trânsito está indo para o bairro em que
    a cabeça já está (ex.: fila no Centro numa avenida que termina no
    Centro): `sentido` é esse bairro, com `distancia_sentido_m` 0.

    Levanta ValueError se um ponto estiver a mais de `distancia_max_m` da
    peça mais próxima (outra rua ou lat/lon trocados); None desliga.
    """
    p_ini, p_fim = _ponto(inicio), _ponto(fim)
    cand_a = _candidatas(pecas, p_ini, tolerancia_m, peca_inicio, distancia_max_m)
    cand_b = _candidatas(pecas, p_fim, tolerancia_m, peca_fim, distancia_max_m)

    escolha = None
    for a, da, pa in cand_a:
        for b, db, pb in cand_b:
            r = _caminho(pecas, a, pa, b, pb)
            if r is None:
                continue
            nota = r[0] + da + db
            if escolha is None or nota < escolha[0]:
                escolha = (nota, a, pa, b, pb, r[1])

    if escolha:
        _, a, pa, b, pb, rota = escolha
    else:
        a, _, pa = min(cand_a, key=lambda c: c[1])
        b, _, pb = min(cand_b, key=lambda c: c[1])
        rota = None

    bairro_inicio = bairro_em(pecas[a]["bairros"], pa)
    bairro_fim = bairro_em(pecas[b]["bairros"], pb)
    if rota:
        percorridos = _bairros_percorridos(pecas, rota, pa, pb)
    else:
        percorridos = [bairro_inicio] if bairro_inicio == bairro_fim else [bairro_inicio, bairro_fim]

    sentido = _proximo_bairro(pecas, b, pb, bairro_fim, alcance_sentido_m) or (bairro_fim, 0.0)

    return {
        "bairro_inicio": bairro_inicio,
        "bairro_fim": bairro_fim,
        "bairros_percorridos": percorridos,
        "sentido": sentido[0],
        "distancia_sentido_m": sentido[1],
    }
