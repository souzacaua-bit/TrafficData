"""Coleta periódica: roda `pior_transito` a cada intervalo e grava o resultado em JSON."""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from .parametros import EXTENSAO_MIN_M
from .principal import pior_transito


def _gravar_json(caminho, dados):
    """Grava num temporário e troca de uma vez: quem lê nunca pega o arquivo pela metade."""
    temporario = Path(caminho).with_name(Path(caminho).name + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)


def _onde(ponta):
    """'Rua X (Bairro)' para o log; só o bairro se a avenida não tem pasta de ruas."""
    return f"{ponta['rua']} ({ponta['bairro']})" if ponta["rua"] else ponta["bairro"]


def coletar_periodicamente(arquivos_geojson, chave_api, saida="pior_transito.json",
                           intervalo_s=600, **opcoes):
    """
    Roda `pior_transito` a cada `intervalo_s` (de início a início) e sobrescreve
    `saida` com a coleta mais recente. O Chromium fica aberto entre as coletas;
    se uma falhar, o erro é mostrado, o navegador é recriado e o loop segue.
    """
    from playwright.sync_api import sync_playwright

    print(f"Coletando a cada {intervalo_s / 60:g} min em {saida} (Ctrl+C para parar)", flush=True)
    with sync_playwright() as p:
        navegador = None
        while True:
            inicio = time.monotonic()
            try:
                if navegador is None:
                    navegador = p.chromium.launch()
                pior = pior_transito(arquivos_geojson, chave_api, navegador=navegador, **opcoes)
                _gravar_json(saida, pior)
                resumo = (f"{pior['nivel']} de {pior['extensao_m']:.0f} m na {pior['avenida']}, "
                          f"de {_onde(pior['inicio'])} até {_onde(pior['fim'])}"
                          if pior["nivel"] else "sem engarrafamento (nenhuma fila de "
                          f"{opcoes.get('extensao_min_m', EXTENSAO_MIN_M):.0f} m ou mais)")
                print(f"[{datetime.now():%H:%M:%S}] {resumo} "
                      f"({time.monotonic() - inicio:.1f} s)", flush=True)
            except Exception as erro:
                mensagem = str(erro).splitlines()[0] if str(erro) else ""
                print(f"[{datetime.now():%H:%M:%S}] falhou: {type(erro).__name__}: {mensagem}",
                      flush=True)
                if navegador is not None:
                    try:
                        navegador.close()
                    except Exception:
                        pass
                    navegador = None
            time.sleep(max(0.0, intervalo_s - (time.monotonic() - inicio)))
