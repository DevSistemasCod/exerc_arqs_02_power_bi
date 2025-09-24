import network
import uasyncio as asyncio
import ujson
from machine import Pin, time_pulse_us
from time import sleep
from webSocket import websocket_handshake, Websocket
from utime import localtime

# ======== CONFIGURAÇÕES ========
SSID = "WIFI_IOT_CFP601"
PASSWORD = "iot@senai601"

TRIG_PIN = 33  # saída do sensor
ECHO_PIN = 32  # entrada do sensor
DISTANCIA_LIMITE = 10  # cm
SOM_VELOCIDADE_CM_POR_US = 0.0343

TIPOS_PECA = ["Grande", "Media", "Pequena"]

# ======== Conectar ao Wi-Fi ========
def conectar_wifi(nome_rede, senha_rede):
    conexao_wifi = network.WLAN(network.STA_IF)
    conexao_wifi.active(True)

    if not conexao_wifi.isconnected():
        print("Conectando a rede Wi-Fi...")
        conexao_wifi.connect(nome_rede, senha_rede)
        while not conexao_wifi.isconnected():
            print(".", end="")
            sleep(0.5)

    print("\nConectado ao Wi-Fi!")
    ip_esp32 = conexao_wifi.ifconfig()[0]
    print("IP do ESP32:", ip_esp32)
    return ip_esp32


# ======== Função de medir distância ========
def medir_distancia(pino_trigger, pino_echo):
    pino_trigger.off()
    sleep(0.002)
    pino_trigger.on()
    sleep(0.00001)
    pino_trigger.off()
    duracao = time_pulse_us(pino_echo, 1, 30000)

    if duracao < 0:
        return -1
    return (duracao * SOM_VELOCIDADE_CM_POR_US) / 2


# ======== Cria objeto com data/hora ========
def criar_objetos(vetor_contadores):
    # Captura data e hora atuais do ESP32
    tempo = localtime()
    data_str = "{:02d}/{:02d}/{:04d}".format(tempo[2], tempo[1], tempo[0])
    hora_str = "{:02d}:{:02d}:{:02d}".format(tempo[3], tempo[4], tempo[5])

    lista_objetos = []
    # Para cada contador, cria um objeto com quantidade, tipo e timestamp
    for indice, quantidade in enumerate(vetor_contadores):
        lista_objetos.append({
            "quantidade": int(quantidade),
            "tipo": TIPOS_PECA[indice],
            "data": data_str,
            "hora": hora_str
        })
    return lista_objetos


# ======== Servidor WebSocket ========
async def atender_cliente(conexao_entrada, conexao_saida):
    # 'await' faz a função pausar enquanto aguarda resposta do cliente
    sucesso_handshake = await websocket_handshake(conexao_entrada, conexao_saida)
    if not sucesso_handshake:
        print("Falha no handshake com cliente WebSocket")
        return # Sai se não conseguir conectar

    # Cria objeto WebSocket para comunicação 
    conexao_ws = Websocket(conexao_entrada, conexao_saida)
    print("Cliente WebSocket conectado!")
    
    # ===== Configuração do sensor ultrassônico =====
    pino_trigger = Pin(TRIG_PIN, Pin.OUT)
    pino_echo = Pin(ECHO_PIN, Pin.IN)

    # Inicializa contadores e estado anterior (para evitar múltiplas contagens)
    vetor_contadores = [0, 0, 0]
    estado_anterior = False

    try:
        while True:  # loop principal da corrotina
            # Medir distância do sensor
            distancia_cm = medir_distancia(pino_trigger, pino_echo)
            if distancia_cm > 0:
                print(f"Distancia: {distancia_cm:.2f} cm")
                # Detecta borda de entrada da peça (evita contagem repetida)
                if distancia_cm <= DISTANCIA_LIMITE and not estado_anterior:
                    estado_anterior = True
                    # Atualiza contadores
                    vetor_contadores[0] = vetor_contadores[0] + 1
                    vetor_contadores[1] = vetor_contadores[1] + 2
                    vetor_contadores[2] = vetor_contadores[2] + 3

                    # Cria objetos com data/hora para envio
                    lista_objetos = criar_objetos(vetor_contadores)
                    
                    # Envia cada objeto ao cliente WebSocket
                    for objeto in lista_objetos:
                        print("Enviando:", objeto)
                         # 'await' pausa apenas esta corrotina, permitindo multitarefa
                        await conexao_ws.send(ujson.dumps(objeto))
                # Se peça saiu da zona de limite, permite nova detecção        
                elif distancia_cm > DISTANCIA_LIMITE:
                    estado_anterior = False

            # Pausa assíncrona, liberando o loop de eventos para outras corrotinas
            await asyncio.sleep(0.2)

    except Exception as erro:
        # Captura erros de comunicação WebSocket
        print("Erro no WebSocket:", erro)
    finally:
        # Fecha conexão de forma segura ao finalizar a corrotina
        conexao_ws.close()
        print("Conexao WebSocket encerrada")


# ======== Função principal ========
async def main():
    ip_esp = conectar_wifi(SSID, PASSWORD)
    print("Servidor rodando... IP:", ip_esp)
    server = await asyncio.start_server(atender_cliente, "0.0.0.0", 8080)
    print("Aguardando clientes WebSocket...")

    while True:
        await asyncio.sleep(1)

# ======== Execução ========
asyncio.run(main())

