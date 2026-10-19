"""
Coletor do pior trânsito: a cada 10 minutos captura as avenidas abaixo e
sobrescreve pior_transito.json. O código fica no pacote `transito`.

A chave da Maps JavaScript API vem de GOOGLE_MAPS_API_KEY, no ambiente ou no
.env ao lado do script (modelo em .env.example).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from transito import coletar_periodicamente

if __name__ == "__main__":
    PASTA = Path(__file__).resolve().parent  # arquivos ao lado do script, de onde quer que ele rode
    PECAS = PASTA / 'peças de exemplo'
    load_dotenv(PASTA / '.env')
    chave = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not chave:
        raise SystemExit('Defina GOOGLE_MAPS_API_KEY no .env (modelo em .env.example)')
    try:
        coletar_periodicamente([PECAS / 'pecas_avenida_crtistiano_machado.geojson'],
                               chave, saida=PASTA / 'pior_transito.json')
    except KeyboardInterrupt:
        pass
