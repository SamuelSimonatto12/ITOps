import random
import time
import psutil


def coletar_metricas_antena(id_antena="ANTENA_01"):

    
    io = psutil.net_io_counters()

    bytes_sent = io.bytes_sent
    bytes_recv = io.bytes_recv

    # 2. Simulação de dispositivos/conexões ativas
    active_conn = random.randint(10, 100)

    # 3. Uso de CPU e RAM (%)
    cpu_usage = psutil.cpu_percent(
        interval=1
    ) 
    cpu_usage_att = min(100, cpu_usage + 1 * active_conn)

    ram_usage = psutil.virtual_memory().percent
    ram_usage_att = min(100, ram_usage + 0.25 * ram_usage)

    return {
        "ID_antena": id_antena,
        "Bytes_Sent": bytes_sent,
        "Bytes_Recv": bytes_recv,
        "Active_conn": active_conn,
        "CPU_Usage_pct": cpu_usage_att,
        "RAM_Usage_pct": ram_usage_att,
    }


# Loop de monitoramento a cada 5 segundos
if __name__ == "__main__":
    ID_ANTENA = "ANT-SUL-01"

    try:
        while True:
            metricas = coletar_metricas_antena(
                id_antena=ID_ANTENA,
            )
            print(metricas)
            time.sleep(4)  # Espera 4s (mais 1s do cpu_percent = 5s total)
    except KeyboardInterrupt:
        print("\nMonitoramento encerrado.")