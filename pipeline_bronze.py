from datetime import datetime
import json
import os
import time
import boto3

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

from antena import coletar_metricas_antena
from firewall import coletar_metricas_firewall

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
PREFIX_BRONZE = os.getenv("PREFIX_BRONZE")
AWS_REGION = os.getenv("AWS_REGION")

s3_client = boto3.client("s3", region_name=AWS_REGION)


def gerar_nome_arquivo(id_dispositivo):
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"{timestamp_str}_{id_dispositivo}.json"


def salvar_e_enviar_bronze(dados, subpasta):
    # Identifica o ID independentemente de ser antena ou firewall
    id_dispositivo = (
        dados.get("ID_antena")
        or dados.get("ID_firewall")
        or dados.get("id_dispositivo")
        or "dispositivo"
    )

    nome_arquivo = gerar_nome_arquivo(id_dispositivo)

    pasta_local = os.path.join(PREFIX_BRONZE, subpasta)
    os.makedirs(pasta_local, exist_ok=True)

    caminho_local = os.path.join(pasta_local, nome_arquivo)
    with open(caminho_local, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] Local: salvo em {caminho_local}"
    )

    # 2. Envia para o S3
    s3_key = f"{PREFIX_BRONZE}/{subpasta}/{nome_arquivo}"
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(dados, indent=4, ensure_ascii=False),
            ContentType="application/json",
        )
        print(f" -> S3: enviado para s3://{BUCKET_NAME}/{s3_key}")
    except Exception as e:
        print(f" -> Erro S3: {e}")


def executar_pipeline():
    print("\n--- Iniciando Coleta Bronze ---")

    dados_antena = coletar_metricas_antena(id_antena="ap01")
    salvar_e_enviar_bronze(dados_antena, subpasta="antenas")

    dados_firewall = coletar_metricas_firewall(id_firewall="fw01")
    salvar_e_enviar_bronze(dados_firewall, subpasta="firewall")


if __name__ == "__main__":
    try:
        while True:
            executar_pipeline()
            print("Aguardando 1 minuto para a próxima execução...\n")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nPipeline encerrado.")