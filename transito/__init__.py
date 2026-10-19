"""
Captura do trânsito por imagem — adaptação do stuttgart-traffic para BH.

Em vez de tirar print do google.de/maps (UI por cima, centro/zoom imprecisos e
avenidas desenhadas em amarelo, que se confunde com o laranja do trânsito),
abre uma página local com a Maps JavaScript API, mapa base todo apagado e só a
TrafficLayer ligada. Como centro, zoom e escala são controlados, cada pixel do
print é georreferenciado por Web Mercator e a cor é lida em cima de cada peça.

Uso:
    from transito import capturar_transito
    dados = capturar_transito(
        ["peças de exemplo/pecas_avenida_do_contorno.geojson"],
        chave_api="...",
        pasta_prints="prints",
    )

O maps_image_collect.py, na raiz do projeto, coleta a pior retenção a cada 10 minutos e
sobrescreve pior_transito.json (ver `coletar_periodicamente`).

Saída por peça no mesmo vocabulário do Routes API (NORMAL / SLOW / TRAFFIC_JAM),
para reaproveitar o tratamento que já existe (consolidar_congestionamentos etc.),
mais STOPPED para o vermelho-escuro, que o Routes API não separa do vermelho.

Módulos, na ordem em que os dados passam por eles:
    parametros   paleta da TrafficLayer, níveis de trânsito e pesos
    geometria    peças do GeoJSON, distâncias, Web Mercator e quadros (prints)
    captura      página do mapa no Chromium (Playwright) e prints
    leitura      cor de trânsito em cada ponto das peças
    analise      trechos, percursos e retenções de cada avenida
    ruas         rua mais próxima de um ponto, do lado do motorista
    bairros      bairros ao longo das peças (base Bairro Popular do BHMap)
    local        rua e bairro do início e do fim de uma retenção
    principal    capturar_transito e pior_transito
    coletor      coleta periódica e gravação do JSON
    conferencia  marca os pontos lidos sobre o print, para conferir

Os dados de ruas e bairros ficam na pasta `bairros e ruas`, ao lado do pacote.
"""

from .coletor import coletar_periodicamente
from .principal import capturar_transito, pior_transito

__all__ = ["capturar_transito", "pior_transito", "coletar_periodicamente"]
