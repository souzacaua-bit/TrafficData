# Traffic World

Monitora o trânsito das principais avenidas de Belo Horizonte e aponta a **pior retenção** da cidade: em qual avenida ela está, o tamanho, a rua e o bairro onde a fila começa e termina, e para onde o trânsito está indo.

## Como funciona

1. Abre o Google Maps num navegador invisível, só com a camada de trânsito (as linhas verdes, laranjas e vermelhas).
2. Tira um print do mapa e lê a cor em cima de cada avenida, a cada 5 metros.
3. Junta os trechos lentos em filas e escolhe a pior delas.
4. Descobre a rua e o bairro de cada ponta da fila.
5. Grava o resultado em `pior_transito.json` e repete a cada 10 minutos.

Filas com menos de 300 m não contam: normalmente são só a espera de um semáforo.

## O que você precisa

- Python 3.10 ou mais novo
- Uma chave da **Maps JavaScript API** do Google ([como criar](https://developers.google.com/maps/documentation/javascript/get-api-key))

## Instalação

```bash
pip install numpy pillow playwright geopandas shapely pyproj pandas python-dotenv
python -m playwright install chromium
```

O segundo comando baixa o navegador que o programa usa para abrir o mapa.

## Configurar a chave

Copie o arquivo `.env.example` com o nome `.env`:

```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux / Mac
```

Abra o `.env` e coloque a sua chave:

```
GOOGLE_MAPS_API_KEY=sua-chave-aqui
```

O `.env` fica só no seu computador. Não envie esse arquivo para o GitHub.

## Rodar

```bash
python maps_image_collect.py
```

A cada coleta aparece uma linha no terminal com a pior retenção, por exemplo:

```
[20:27:26] STOPPED de 645 m na Avenida Cristiano Machado, de Rua dos Pinguins (Vila Clóris) até Rua Joaquim Clemente (Juliana) (15.0 s)
```

Para parar, aperte `Ctrl+C`.

## Escolher as avenidas

As avenidas ficam na lista dentro de `maps_image_collect.py`. Para monitorar mais de uma, coloque mais arquivos na lista:

```python
coletar_periodicamente([PECAS / 'pecas_avenida_crtistiano_machado.geojson',
                        PECAS / 'pecas_avenida_do_contorno.geojson'],
                       chave, saida=PASTA / 'pior_transito.json')
```

Avenidas disponíveis, na pasta `peças de exemplo/`:

| Arquivo | Avenida |
|---|---|
| `pecas_avenida_afonso_pena.geojson` | Avenida Afonso Pena |
| `pecas_avenida_amazonas.geojson` | Avenida Amazonas |
| `pecas_avenida_bias_fortes.geojson` | Avenida Bias Fortes |
| `pecas_avenida_crtistiano_machado.geojson` | Avenida Cristiano Machado |
| `pecas_avenida_do_contorno.geojson` | Avenida do Contorno |
| `pecas_Avenida_dos_Andradas.geojson` | Avenida dos Andradas |
| `pecas_anel_rodoviario.geojson` | Anel Rodoviário |

A rua de cada ponta só aparece nas avenidas que têm pasta em `bairros e ruas/ruas/`. Nas outras, o campo `rua` vem vazio e o bairro continua aparecendo.

Para coletar com outra frequência, passe `intervalo_s` em segundos (o padrão é 600, ou seja, 10 minutos):

```python
coletar_periodicamente([...], chave, saida=PASTA / 'pior_transito.json', intervalo_s=300)
```

## O resultado

O `pior_transito.json` é substituído a cada coleta. Os campos principais:

```json
{
  "coletado_em": "2026-10-18T20:27:26",
  "avenida": "Avenida Cristiano Machado",
  "nivel": "STOPPED",
  "extensao_m": 645.0,
  "metros_slow": 210.0,
  "metros_traffic_jam": 230.0,
  "metros_stopped": 205.0,
  "gravidade": 1925.0,
  "inicio": {"lat": -19.82498, "lon": -43.94383, "rua": "Rua dos Pinguins", "rua_distancia_m": 67.0, "bairro": "Vila Clóris"},
  "fim": {"lat": -19.81969, "lon": -43.94636, "rua": "Rua Joaquim Clemente", "rua_distancia_m": 28.9, "bairro": "Juliana"},
  "bairros_percorridos": ["Vila Clóris", "Juliana"],
  "sentido": "Satélite",
  "coordenadas": [[-19.82498, -43.94383], [-19.81969, -43.94636]]
}
```

| Campo | O que é |
|---|---|
| `nivel` | A pior cor da fila: `SLOW` (laranja), `TRAFFIC_JAM` (vermelho) ou `STOPPED` (vermelho-escuro). Vem `null` quando não há nenhuma fila de 300 m ou mais |
| `extensao_m` | Tamanho da fila, em metros |
| `metros_slow`, `metros_traffic_jam`, `metros_stopped` | Quantos metros da fila têm cada cor |
| `gravidade` | Nota usada para escolher a pior fila: cada metro laranja vale 1, vermelho vale 3 e vermelho-escuro vale 5 |
| `inicio`, `fim` | Ponto onde a fila começa e termina, com a rua mais próxima e o bairro |
| `bairros_percorridos` | Bairros por onde a fila passa |
| `sentido` | Bairro para onde o trânsito está indo |
| `coordenadas` | Todos os pontos da fila, em `[lat, lon]`, para desenhar num mapa |

## Usar no seu próprio código

Para fazer uma consulta só, sem repetir a cada 10 minutos:

```python
import os
from dotenv import load_dotenv
from transito import pior_transito

load_dotenv()
dados = pior_transito(["peças de exemplo/pecas_avenida_do_contorno.geojson"], os.environ["GOOGLE_MAPS_API_KEY"])
print(dados["avenida"], dados["extensao_m"], "m")
```

Rode a partir da pasta do projeto, para os caminhos dos arquivos funcionarem.

## Pastas

```
transito/              o código
peças de exemplo/      o traçado de cada avenida, dividido em pedaços
bairros e ruas/
  BAIRRO_POPULAR.json  os bairros de Belo Horizonte
  ruas/<avenida>/      as ruas que cruzam cada avenida, separadas por lado
maps_image_collect.py  o coletor
.env.example           modelo do arquivo da chave
```

## Custo da API

Cada coleta carrega o mapa uma vez. Coletando a cada 10 minutos, são cerca de 4.300 carregamentos por mês. Confira os [preços da Maps JavaScript API](https://developers.google.com/maps/billing-and-pricing/pricing) para saber se isso cabe na cota gratuita.

## Dados

- Traçado das avenidas e ruas: © colaboradores do [OpenStreetMap](https://www.openstreetmap.org/copyright)
- Bairros: base Bairro Popular do BHMap, da Prefeitura de Belo Horizonte
- Trânsito: camada de trânsito do Google Maps

## Licença

Veja o arquivo [LICENSE](LICENSE).
