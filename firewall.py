import random
import time
import psutil

# Lista de IPs suspeitos para simular tentativas de força bruta / DoS
IPS_SUSPEITOS = [
    "185.220.101.5",
    "45.154.255.120",
    "192.168.1.250",
    "10.0.0.99",
    "198.51.100.42",
]


def coletar_metricas_firewall(id_firewall="fw01"):
    # 1. Tráfego de Rede (Bytes Enviados e Recebidos)
    io = psutil.net_io_counters()
    bytes_sent = io.bytes_sent
    bytes_recv = io.bytes_recv

    # Pacotes descartados (dados reais do SO + simulação de descarte por regras de firewall)
    dropped_packets = (io.dropin + io.dropout) + random.randint(10, 150)

    # 2. Sessões TCP/UDP Ativas    
    # active_sessions = len(psutil.net_connections(kind="inet"))
    active_sessions = random.randint(400, 1200)

    # 3. IP do atacante simulado
    top_blocked_ip = random.choice(IPS_SUSPEITOS)

    # 4. Uso de CPU e RAM (%)
    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_usage_att = min(100.0, cpu_usage + (active_sessions / 50))

    ram_usage = psutil.virtual_memory().percent
    ram_usage_att = min(100.0, ram_usage + (active_sessions / 100))

    return {
        "id_dispositivo": id_firewall,
        "tipo": "firewall",
        "bytes_sent": bytes_sent,
        "bytes_recv": bytes_recv,
        "active_sessions": active_sessions,
        "dropped_packets": dropped_packets,
        "top_blocked_ip": top_blocked_ip,
        "cpu_usage_pct": round(cpu_usage_att, 2),
        "ram_usage_pct": round(ram_usage_att, 2),
    }


if __name__ == "__main__":
    ID_FIREWALL = "fw01"

    try:
        while True:
            metricas = coletar_metricas_firewall(id_firewall=ID_FIREWALL)
            print(metricas)
            time.sleep(4)  
    except KeyboardInterrupt:
        print("\nMonitoramento do firewall encerrado.")