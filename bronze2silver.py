from datetime import datetime
import json
import os
import time
import boto3
import pandas as pd

# Carregar variáveis de ambiente
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:

    def carregar_env(caminho_env=".env"):
        if os.path.exists(caminho_env):
            with open(caminho_env, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha and not linha.startswith("#") and "=" in linha:
                        chave, valor = linha.split("=", 1)
                        os.environ[chave.strip()] = (
                            valor.strip().strip('"').strip("'")
                        )

    carregar_env()

BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "itops-s3-sptech-samuel")
PREFIX_BRONZE = os.getenv("PREFIX_BRONZE", "bronze")
PREFIX_SILVER = os.getenv("PREFIX_SILVER", "silver")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client("s3", region_name=AWS_REGION)


def extrair_e_formatar_timestamp(nome_arquivo):
    """Extrai 'YYYY-MM-DD_HH-MM' do arquivo e formata para 'YYYY-MM-DD HH:MM:00'"""
    try:
        partes = nome_arquivo.split("_")
        data_str, hora_str = partes[0], partes[1]
        dt = datetime.strptime(f"{data_str}_{hora_str}", "%Y-%m-%d_%H-%M")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def ler_jsons_bronze_local():
    """Lê todos os JSONs locais da camada Bronze e cria DataFrames"""
    lista_antenas = []
    lista_firewall = []

    # 1. Antenas
    pasta_antenas = os.path.join(PREFIX_BRONZE, "antenas")
    if os.path.exists(pasta_antenas):
        for arq in os.listdir(pasta_antenas):
            if arq.endswith(".json"):
                timestamp = extrair_e_formatar_timestamp(arq)
                caminho = os.path.join(pasta_antenas, arq)
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        dados["timestamp"] = timestamp
                        lista_antenas.append(dados)
                except Exception as e:
                    print(f"Erro ao ler arquivo {caminho}: {e}")

    # 2. Firewall
    pasta_firewall = os.path.join(PREFIX_BRONZE, "firewall")
    if os.path.exists(pasta_firewall):
        for arq in os.listdir(pasta_firewall):
            if arq.endswith(".json"):
                timestamp = extrair_e_formatar_timestamp(arq)
                caminho = os.path.join(pasta_firewall, arq)
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        dados["timestamp"] = timestamp
                        lista_firewall.append(dados)
                except Exception as e:
                    print(f"Erro ao ler arquivo {caminho}: {e}")

    return pd.DataFrame(lista_antenas), pd.DataFrame(lista_firewall)


def avaliar_status_carga(row):
    status = []

    # 1. Gargalo de Processamento
    cpu_antena = row.get("antena_cpu_pct", 0)
    cpu_fw = row.get("firewall_cpu_pct", 0)
    if cpu_antena > 80 or cpu_fw > 80:
        status.append("gargalo de processamento")

    # 2. OOM (Out Of Memory)
    ram_antena = row.get("antena_ram_pct", 0)
    ram_fw = row.get("firewall_ram_pct", 0)
    if ram_antena > 75 or ram_fw > 75:
        status.append("OOM (Out Of Memory)")

    # 3. Alta Densidade na Antena
    if row.get("Active_conn", 0) > 40:
        status.append("alta densidade")

    return " | ".join(status) if status else "Normal"


def processar_camada_silver():
    print("\n--- Processando Camada Silver (Tratamento & Join) ---")

    df_antenas, df_firewall = ler_jsons_bronze_local()

    if df_antenas.empty or df_firewall.empty:
        print("Dados insuficientes na Bronze para realizar o cruzamento.")
        return

    # ---------------------------------------------------------------------
    # PADRONIZAÇÃO DE COLUNAS
    # ---------------------------------------------------------------------
    df_antenas.columns = df_antenas.columns.str.lower()
    df_firewall.columns = df_firewall.columns.str.lower()

    df_antenas = df_antenas.rename(
        columns={
            "id_antena": "ID_antena",
            "bytes_sent": "antena_bytes_sent",
            "bytes_recv": "antena_bytes_recv",
            "cpu_usage_pct": "antena_cpu_pct",
            "ram_usage_pct": "antena_ram_pct",
            "active_conn": "Active_conn",
        }
    )

    df_firewall = df_firewall.rename(
        columns={
            "id_firewall": "ID_firewall",
            "bytes_sent": "firewall_bytes_sent",
            "bytes_recv": "firewall_bytes_recv",
            "cpu_usage_pct": "firewall_cpu_pct",
            "ram_usage_pct": "firewall_ram_pct",
            "active_sessions": "Active_sessions",
            "dropped_packets": "Dropped_packets",
        }
    )

    for col in ["antena_bytes_sent", "antena_bytes_recv"]:
        if col not in df_antenas.columns:
            df_antenas[col] = 0

    for col in ["firewall_bytes_sent", "firewall_bytes_recv"]:
        if col not in df_firewall.columns:
            df_firewall[col] = 0

    # ---------------------------------------------------------------------
    # 1. JOIN (CRUZAMENTO) PELA TIMESTAMP
    # ---------------------------------------------------------------------
    df_silver = pd.merge(df_antenas, df_firewall, on="timestamp", how="inner")
    df_silver = df_silver.sort_values(by="timestamp").reset_index(drop=True)

    # ---------------------------------------------------------------------
    # 2. CÁLCULO DE VAZÃO INSTANTÂNEA (Mbps)
    # ---------------------------------------------------------------------
    df_silver["antena_vazao_sent_mbps"] = (
        (df_silver["antena_bytes_sent"].diff() * 8) / (60 * 1_000_000)
    ).fillna(0.0).round(4)

    df_silver["firewall_vazao_sent_mbps"] = (
        (df_silver["firewall_bytes_sent"].diff() * 8) / (60 * 1_000_000)
    ).fillna(0.0).round(4)

    # ---------------------------------------------------------------------
    # 3. CONSISTÊNCIA DE TRÁFEGO
    # ---------------------------------------------------------------------
    df_silver["diferenca_bytes_sent"] = (
        df_silver["firewall_bytes_sent"] - df_silver["antena_bytes_sent"]
    )
    df_silver["status_consistencia_trafego"] = df_silver[
        "diferenca_bytes_sent"
    ].apply(
        lambda diff: "OK (Consistente)"
        if abs(diff) < 500_000
        else "Discrepância Detectada"
    )

    # ---------------------------------------------------------------------
    # 4. COLUNA DE CARGA / ALERTA (status_carga)
    # ---------------------------------------------------------------------
    df_silver["status_carga"] = df_silver.apply(avaliar_status_carga, axis=1)

    colunas_finais = [
        "timestamp",
        "ID_antena",
        "ID_firewall",
        "Active_conn",
        "Active_sessions",
        "antena_vazao_sent_mbps",
        "firewall_vazao_sent_mbps",
        "antena_bytes_sent",
        "firewall_bytes_sent",
        "diferenca_bytes_sent",
        "status_consistencia_trafego",
        "status_carga",
        "top_blocked_ip",
        "Dropped_packets",
        "antena_cpu_pct",
        "firewall_cpu_pct",
        "antena_ram_pct",
        "firewall_ram_pct",
    ]

    cols = [c for c in colunas_finais if c in df_silver.columns]
    df_silver = df_silver[cols]

    # ---------------------------------------------------------------------
    # 5. SALVAR LOCALMENTE E SUBIR PARA S3
    # ---------------------------------------------------------------------
    os.makedirs(PREFIX_SILVER, exist_ok=True)
    caminho_csv_local = os.path.join(PREFIX_SILVER, "dados_consolidados.csv")

    df_silver.to_csv(caminho_csv_local, index=False, encoding="utf-8")
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] CSV Silver salvo em: {caminho_csv_local}"
    )

    s3_key = f"{PREFIX_SILVER}/dados_consolidados.csv"
    try:
        s3_client.upload_file(caminho_csv_local, BUCKET_NAME, s3_key)
        print(f" -> Enviado para S3: s3://{BUCKET_NAME}/{s3_key}")
    except Exception as e:
        print(f" -> Erro ao subir para o S3: {e}")


# Executa o pipeline ao rodar o script diretamente
if __name__ == "__main__":
    processar_camada_silver()