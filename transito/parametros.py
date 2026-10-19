"""Parâmetros da leitura: paleta da TrafficLayer, níveis de trânsito e pesos da gravidade."""

# Paleta da TrafficLayer: miolo e borda de cada linha (medidos nos prints; a borda
# é mais escura e é o que a busca encontra primeiro quando o eixo passa fora da
# linha), mais a paleta antiga, que ainda aparece em alguns tiles.
CORES_TRANSITO = {
    "verde": [(22, 224, 152), (4, 156, 100), (99, 214, 104), (132, 202, 80)],
    "laranja": [(255, 207, 67), (240, 190, 34), (255, 151, 77), (240, 125, 2)],
    "vermelho": [(242, 78, 66), (152, 62, 56), (242, 60, 50), (230, 0, 0)],
    "vermelho_escuro": [(169, 39, 39), (112, 32, 32), (129, 31, 31), (158, 19, 19)],
}
CLASSE_PARA_SPEED = {
    "verde": "NORMAL",
    "laranja": "SLOW",
    "vermelho": "TRAFFIC_JAM",
    "vermelho_escuro": "STOPPED",
}
TOLERANCIA_COR = 60  # distância RGB máxima até a cor de referência

# Peso de cada nível na gravidade de uma retenção, do mais leve ao mais grave:
# 1 m em vermelho conta como 3 m em amarelo; 1 m em vermelho-escuro, como 5.
PESO_NIVEL = {"SLOW": 1.0, "TRAFFIC_JAM": 3.0, "STOPPED": 5.0}

# Extensão mínima de uma retenção para concorrer a pior trânsito. Mais curta que
# isso é fila de semáforo, que o Google pinta nos 100-200 m antes do cruzamento:
# 88% das 190 retenções medidas no Contorno, Amazonas, Cristiano Machado e
# Andradas tinham menos de 200 m; os engarrafamentos conferidos nos prints, 345 m
# ou mais.
EXTENSAO_MIN_M = 300.0
