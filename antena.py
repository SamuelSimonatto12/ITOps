import random
import time
import psutil


def coletar_metricas_antena(id_antena="ap01"):
    # 1. Tráfego de Rede acumulado
    io = psutil.net_io_counters()
    bytes_sent = io.bytes_sent
    bytes_recv = io.bytes_recv

    # 2. Simulação de dispositivos/conexões ativas
    active_conn = random.randint(10, 100)

    # 3. Uso de CPU e RAM (%) com simulação de impacto das conexões
    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_usage_att = min(100.0, cpu_usage + 1 * active_conn)

    ram_usage = psutil.virtual_memory().percent
    ram_usage_att = min(100.0, ram_usage + 0.25 * active_conn)

    return {
        "id_dispositivo": id_antena, 
        "tipo": "antena",
        "bytes_sent": bytes_sent,
        "bytes_recv": bytes_recv,
        "active_conn": active_conn,
        "cpu_usage_pct": round(cpu_usage_att, 2),
        "ram_usage_pct": round(ram_usage_att, 2),
    }


if __name__ == "__main__":
    ID_ANTENA = "ap01"

    try:
        while True:
            metricas = coletar_metricas_antena(id_antena=ID_ANTENA)
            print(metricas)
            time.sleep(4) 
    except KeyboardInterrupt:
        print("\nMonitoramento encerrado.")