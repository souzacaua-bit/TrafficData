"""Captura (Playwright): abre a Maps JavaScript API só com a TrafficLayer e tira os prints."""

import json
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image


# Mapa base apagado: fundo branco, sem ruas, sem rótulos. Só sobra o trânsito.
ESTILO_MAPA = [
    {"elementType": "labels", "stylers": [{"visibility": "off"}]},
    {"featureType": "all", "elementType": "geometry", "stylers": [{"visibility": "off"}]},
    {"featureType": "landscape", "elementType": "geometry",
     "stylers": [{"visibility": "on"}, {"color": "#ffffff"}]},
]

HTML_MAPA = """<!doctype html>
<html><head><meta charset="utf-8">
<style>html,body,#mapa{margin:0;padding:0;width:100%;height:100%;background:#fff}</style>
</head><body><div id="mapa"></div>
<script>
let mapa;
window.mapaPronto = false;
function iniciar() {
  mapa = new google.maps.Map(document.getElementById('mapa'), {
    center: {lat: __LAT__, lng: __LON__}, zoom: __ZOOM__,
    disableDefaultUI: true, keyboardShortcuts: false, gestureHandling: 'none',
    clickableIcons: false, backgroundColor: '#ffffff', styles: __ESTILO__,
  });
  new google.maps.TrafficLayer().setMap(mapa);
  google.maps.event.addListenerOnce(mapa, 'idle', () => { window.mapaPronto = true; });
}
window.irPara = (lat, lon) => new Promise(resolve => {
  google.maps.event.addListenerOnce(mapa, 'idle', () => {
    const c = mapa.getCenter();
    resolve([c.lat(), c.lng(), mapa.getZoom()]);
  });
  mapa.setCenter({lat: lat, lng: lon});
  google.maps.event.trigger(mapa, 'resize');
});
</script>
<script async src="https://maps.googleapis.com/maps/api/js?key=__CHAVE__&callback=iniciar"></script>
</body></html>"""

URL_PAGINA = "http://transito.local/mapa.html"


def _esperar_tiles(page, contador, quieto_ms=150, limite_ms=20000):
    """
    Espera os tiles de trânsito: nenhuma requisição pendente ou nova e todas as
    imagens do mapa carregadas por `quieto_ms`, e então dois quadros de pintura
    para estarem na tela. Medido em BH: o print sai igual ao tirado 1,5 s depois.
    """
    inicio = time.monotonic()
    pronto_desde = None
    ultimo_total = contador["total"]
    while (time.monotonic() - inicio) * 1000 < limite_ms:
        carregado = (contador["pendentes"] == 0 and contador["total"] == ultimo_total
                     and page.evaluate("() => [...document.querySelectorAll('#mapa img')]"
                                       ".every(i => i.complete)"))
        ultimo_total = contador["total"]
        if not carregado:
            pronto_desde = None
        elif pronto_desde is None:
            pronto_desde = time.monotonic()
        elif (time.monotonic() - pronto_desde) * 1000 >= quieto_ms:
            break
        page.wait_for_timeout(30)
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def capturar_quadros(quadros, chave_api, zoom=16, largura=1920, altura=1080,
                     escala_tela=2, pasta_prints=None, rotulo="bh", navegador=None):
    """
    Abre o mapa uma vez (um único carregamento cobrado da Maps JS API) e vai
    reposicionando o centro para cada quadro. Devolve as imagens como arrays RGB.

    `navegador` é um Chromium do Playwright já aberto, para reaproveitar entre
    coletas; sem ele, abre um só para esta captura. O mapa é carregado sempre num
    contexto novo: num mapa já aberto, religar a TrafficLayer só redesenha os
    tiles da memória, sem buscar o trânsito atualizado.
    """
    if navegador is None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            try:
                return capturar_quadros(quadros, chave_api, zoom, largura, altura,
                                        escala_tela, pasta_prints, rotulo, navegador)
            finally:
                navegador.close()

    lon0, lat0 = quadros[0]["centro"]
    html = (HTML_MAPA.replace("__LAT__", repr(lat0)).replace("__LON__", repr(lon0))
            .replace("__ZOOM__", str(zoom)).replace("__ESTILO__", json.dumps(ESTILO_MAPA))
            .replace("__CHAVE__", chave_api))
    carimbo = datetime.now().strftime("%Y%m%d%H%M%S")
    if pasta_prints:
        Path(pasta_prints).mkdir(parents=True, exist_ok=True)

    imagens = []
    contexto = navegador.new_context(viewport={"width": largura, "height": altura},
                                     device_scale_factor=escala_tela)
    try:
        page = contexto.new_page()
        page.route(URL_PAGINA, lambda rota: rota.fulfill(body=html, content_type="text/html"))

        contador = {"pendentes": 0, "total": 0}

        def _saiu(_):
            contador["pendentes"] = max(0, contador["pendentes"] - 1)

        def _entrou(_):
            contador["pendentes"] += 1
            contador["total"] += 1

        page.on("request", _entrou)
        page.on("requestfinished", _saiu)
        page.on("requestfailed", _saiu)

        page.goto(URL_PAGINA)
        page.wait_for_function("window.mapaPronto === true", timeout=30000)

        for i, quadro in enumerate(quadros):
            lon, lat = quadro["centro"]
            lat_r, lon_r, zoom_r = page.evaluate("([lat, lon]) => window.irPara(lat, lon)", [lat, lon])
            if zoom_r != zoom or abs(lat_r - lat) > 1e-6 or abs(lon_r - lon) > 1e-6:
                raise RuntimeError(f"Mapa não ficou no centro/zoom pedido: {lat_r}, {lon_r}, z{zoom_r}")
            _esperar_tiles(page, contador)
            png = page.screenshot(type="png")
            if pasta_prints:
                Path(pasta_prints, f"{rotulo}-{carimbo}-q{i:02d}.png").write_bytes(png)
            imagens.append(np.asarray(Image.open(BytesIO(png)).convert("RGB")))
    finally:
        contexto.close()
    return imagens, carimbo
