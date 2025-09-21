import network
import uasyncio as asyncio
import ujson
from machine import Pin, time_pulse_us
from time import sleep
from webSocket import websocket_handshake, Websocket  

# ======== CONFIGURAÇÕES ========
SSID = "WIFI_IOT_CFP601"
PASSWORD = "iot@senai601"

TRIG_PIN = 33  # saída do sensor
ECHO_PIN = 32  # entrada do sensor
DISTANCIA_LIMITE = 10  # cm
SOM_VELOCIDADE_CM_POR_US = 0.0343

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


# ======== Servidor WebSocket ========
# async def: define uma corrotina que pode ser pausada e retomada.
async def atender_cliente(conexao_entrada, conexao_saida):
    # ===== Handshake WebSocket =====
    # Realiza o handshake assíncrono com o cliente WebSocket.
    # 'await' permite que o ESP32 execute outras tarefas enquanto espera a resposta.
    sucesso_handshake = await websocket_handshake(conexao_entrada, conexao_saida)
    if not sucesso_handshake:
        print("Falha no handshake com cliente WebSocket")
        return  # Sai da função se não conseguir conectar

    # Cria objeto de conexão WebSocket para comunicação
    conexao_ws = Websocket(conexao_entrada, conexao_saida)
    print("Cliente WebSocket conectado!")

    # Configura pinos de trigger (saída) e echo (entrada)
    pino_trigger = Pin(TRIG_PIN, Pin.OUT)
    pino_echo = Pin(ECHO_PIN, Pin.IN)

    # Inicializa contadores e estado anterior do sensor
    contador1 = 0
    contador2 = 1
    contador3 = 2
    estado_anterior = False  # usado para detectar borda de entrada da peça

    try:
        while True:  # loop principal da corrotina
            # Mede a distância usando o sensor ultrassônico
            distancia_cm = medir_distancia(pino_trigger, pino_echo)
            if distancia_cm > 0:
                print(f"Distancia: {distancia_cm:.2f} cm")

                # Detecta se a peça entrou na zona de limite e evita contagem repetida
                if distancia_cm <= DISTANCIA_LIMITE and not estado_anterior:
                    # Atualiza contadores
                    contador1 = contador1 + 1
                    contador2 = contador2 + 2
                    contador3 = contador3 + 3
                    estado_anterior = True  # marca que já contou a peça

                    # Prepara vetor de contadores e envia ao cliente WebSocket
                    vetor_contadores = [contador1, contador2, contador3]
                    print("Peca detectada, vetor:", vetor_contadores)
                    # 'await' faz a função pausar enquanto envia os dados,
                    # permitindo que outras corrotinas rodem simultaneamente
                    await conexao_ws.send(ujson.dumps(vetor_contadores))

                elif distancia_cm > DISTANCIA_LIMITE:
                    # Quando peça sai da zona, reseta o estado para próxima detecção
                    estado_anterior = False

            # Pausa assíncrona para liberar o loop de eventos e permitir multitarefa
            await asyncio.sleep(0.2)

    except Exception as erro:
        # Captura qualquer erro durante a execução do loop
        print("Erro no WebSocket:", erro)
    finally:
        # Garantir que a conexão WebSocket seja fechada quando a corrotina terminar
        conexao_ws.close()
        print("Conexao WebSocket encerrada")

        


# ======== Função principal ========
async def main():
    ip_esp = conectar_wifi(SSID, PASSWORD)
    print("Servidor rodando... IP:", ip_esp)
    server = await asyncio.start_server(atender_cliente, "0.0.0.0", 8080)
    print("Aguardando clientes WebSocket...")

    # Mantém o loop do servidor rodando
    while True:
        await asyncio.sleep(1)


# ======== Execução ========
asyncio.run(main())

