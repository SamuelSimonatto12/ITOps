from datetime import datetime
import os
import boto3
import pandas as pd

from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "itops-s3-sptech-samuel")
PREFIX_SILVER = os.getenv("PREFIX_SILVER", "silver")
PREFIX_GOLD = os.getenv("PREFIX_GOLD", "gold")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client("s3", region_name=AWS_REGION)


# extração

def ler_silver():

    caminho_silver = os.path.join(
        PREFIX_SILVER,
        "dados_consolidados.csv"
    )

    if not os.path.exists(caminho_silver):
        print("Arquivo da Silver não encontrado.")
        return pd.DataFrame()

    df = pd.read_csv(caminho_silver)

    print("Colunas da Silver:")
    print(df.columns.tolist())

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        "Dados da Silver carregados."
        )
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        "Dados da Silver carregados."
    )

    return df


# transformação

def gerar_relatorio_zona_morta(df):

    df = df[
        [
            "timestamp",
            "ID_antena",
            "Active_conn",
            "antena_vazao_sent_mbps"
        ]
    ]

    # convertendo dados para números
    df["Active_conn"] = pd.to_numeric(
        df["Active_conn"],
        errors="coerce"
    )

    df["antena_vazao_sent_mbps"] = pd.to_numeric(
        df["antena_vazao_sent_mbps"],
        errors="coerce"
    )

    # removendo linhas que não têm dados necessários
    df = df.dropna(
        subset=[
            "ID_antena",
            "Active_conn",
            "antena_vazao_sent_mbps"
        ]
    )

    # Agrupa os dados por antena
    df_gold = (
        df.groupby("ID_antena")
        .agg(
            media_conexoes=("Active_conn", "mean"),
            media_vazao_mbps=(
                "antena_vazao_sent_mbps",
                "mean"
            ),
            menor_conexoes=("Active_conn", "min"),
            maior_conexoes=("Active_conn", "max")
        )
        .reset_index()
    )

    df_gold["media_conexoes"] = df_gold[
        "media_conexoes"
    ].round(2)

    df_gold["media_vazao_mbps"] = df_gold[
        "media_vazao_mbps"
    ].round(4)

    # Classificação da utilização
    def classificar_antena(row):

        if (
            row["media_conexoes"] < 10
            and row["media_vazao_mbps"] < 1
        ):
            return "ZONA MORTA"

        elif (
            row["media_conexoes"] < 20
            and row["media_vazao_mbps"] < 2
        ):
            return "SUBUTILIZADA"

        else:
            return "NORMAL"

    df_gold["classificacao"] = df_gold.apply(
        classificar_antena,
        axis=1
    )

    # Ordena da menor utilização para a maior
    df_gold = df_gold.sort_values(
        by="media_conexoes"
    )

    return df_gold


def gerar_previsao_sobrecarga(df_silver):

    LIMITE_CONEXOES = 500

    colunas = [
        "timestamp",
        "ID_antena",
        "Active_conn"
    ]

    df = df_silver[colunas].copy()

    # Garantir que os dados estejam no formato correto
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["Active_conn"] = pd.to_numeric(
        df["Active_conn"],
        errors="coerce"
    )

    df = df.dropna()

    # Ordenar por antena e horário
    df = df.sort_values(
        ["ID_antena", "timestamp"]
    )

    resultados = []

    # Fazer a previsão para cada antena
    for antena, grupo in df.groupby("ID_antena"):

        grupo = grupo.sort_values("timestamp")

        # Pegar somente os dados das últimas 5 horas
        ultimo_horario = grupo["timestamp"].max()

        inicio_5_horas = ultimo_horario - pd.Timedelta(hours=5)

        ultimos_dados = grupo[
            grupo["timestamp"] >= inicio_5_horas
        ].copy()

        # Precisamos de pelo menos 2 registros
        if len(ultimos_dados) < 2:
            continue

        # Calcular quanto as conexões cresceram
        ultimos_dados["crescimento_conexoes"] = (
            ultimos_dados["Active_conn"].diff()
        )

        # Média do crescimento
        crescimento_medio = (
            ultimos_dados["crescimento_conexoes"]
            .dropna()
            .mean()
        )

        # Situação atual
        conexoes_atuais = (
            ultimos_dados["Active_conn"].iloc[-1]
        )

        horario_atual = (
            ultimos_dados["timestamp"].iloc[-1]
        )

        # Quanto falta para atingir o limite
        conexoes_restantes = (
            LIMITE_CONEXOES - conexoes_atuais
        )

        # Se já atingiu ou passou do limite
        if conexoes_atuais >= LIMITE_CONEXOES:

            previsao = "LIMITE JÁ ATINGIDO"
            horario_previsao = horario_atual

        # Se não está crescendo, não conseguimos prever
        elif crescimento_medio <= 0:

            previsao = "SEM PREVISÃO DE SOBRECARGA"
            horario_previsao = None

        else:

            # Quantas horas faltam
            horas_ate_limite = (
                conexoes_restantes / crescimento_medio
            )

            # Horário previsto
            horario_previsao = (
                horario_atual
                + pd.Timedelta(hours=horas_ate_limite)
            )

            previsao = "SOBRECARGA PREVISTA"

        resultados.append({
            "ID_antena": antena,
            "horario_atual": horario_atual,
            "conexoes_atuais": round(conexoes_atuais, 2),
            "limite_conexoes": LIMITE_CONEXOES,
            "crescimento_medio_conexoes_hora": round(
                crescimento_medio, 2
            ),
            "conexoes_restantes": round(
                max(conexoes_restantes, 0), 2
            ),
            "previsao": previsao,
            "horario_previsto_sobrecarga": horario_previsao
        })

    df_previsao = pd.DataFrame(resultados)

    return df_previsao



# load

def salvar_gold(df_gold, nome_arquivo):

    os.makedirs(
        PREFIX_GOLD,
        exist_ok=True
    )

    caminho_csv = os.path.join(
        PREFIX_GOLD,
        nome_arquivo
    )

    df_gold.to_csv(
        caminho_csv,
        index=False,
        encoding="utf-8"
    )

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        f"Gold salva em: {caminho_csv}"
    )

    s3_key = (
        f"{PREFIX_GOLD}/"
        f"{nome_arquivo}"
    )

    try:

        s3_client.upload_file(
            caminho_csv,
            BUCKET_NAME,
            s3_key
        )

        print(
            f" -> Enviado para S3: "
            f"s3://{BUCKET_NAME}/{s3_key}"
        )

    except Exception as e:

        print(
            f" -> Erro ao subir para o S3: {e}"
        )


def processar_gold():

    print(
        "\n--- Processando Camada Gold "
        "(Analytics) ---"
    )

    df_silver = ler_silver()

    if df_silver.empty:

        print(
            "Não existem dados suficientes "
            "na Silver."
        )

        return

    # --------------------------------
    # RELATÓRIO DE ZONAS MORTAS
    # --------------------------------

    df_zonas_mortas = gerar_relatorio_zona_morta(
        df_silver
    )

    print("\nRelatório de Zonas Mortas:")
    print(df_zonas_mortas)

    salvar_gold(
        df_zonas_mortas,
        "relatorio_zonas_mortas.csv"
    )

    # --------------------------------
    # PREVISÃO DE SOBRECARGA
    # --------------------------------

    df_previsao = gerar_previsao_sobrecarga(
        df_silver
    )

    print("\nRelatório de Predição de Sobrecarga:")
    print(df_previsao)

    salvar_gold(
        df_previsao,
        "previsao_sobrecarga.csv"
    )


if __name__ == "__main__":

    processar_gold()
