import streamlit as st
import requests
import time
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go

# Configurações iniciais
auth_url = "https://integra.ons.org.br/api/autenticar"
renovar_url = "https://integra.ons.org.br/api/renovar"
geracao_url = "https://integra.ons.org.br/api/programacao/usina/ListarGeracaoProposta"

# Configura a visualização da página como wide
st.set_page_config(layout="wide")

# Função para obter o token de autenticação
def get_token(login, senha):
    auth_payload = {
        "usuario": login,
        "senha": senha
    }
    response = requests.post(auth_url, json=auth_payload)
    if response.status_code == 200:
        auth_data = response.json()
        return auth_data['access_token'], auth_data['refresh_token']
    else:
        st.error(f"Erro na autenticação: {response.status_code}")
        return None, None

# Função para renovar o token de autenticação
def renovar_token(refresh_token):
    response = requests.post(renovar_url, json={"refresh_token": refresh_token})
    if response.status_code == 200:
        auth_data = response.json()
        return auth_data['access_token'], auth_data['refresh_token']
    else:
        st.error(f"Erro ao renovar o token: {response.status_code}")
        return None, None

# Função para dividir a lista de usinas em grupos de no máximo 10
def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# Função para fazer a requisição e obter os dados de geração por usina
def get_usina_generation_forecast(access_token, date, usinas, refresh_token):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    all_data = []

    for chunk in chunk_list(usinas, 10):
        payload = {
            "Ano": date.year,
            "Mes": date.month,
            "Dia": date.day,
            "CodigosUsinas": chunk
        }

        response = requests.post(geracao_url, json=payload, headers=headers)

        if response.status_code == 200:
            all_data.extend(response.json().get("Usinas", []))
        elif response.status_code == 401:  # Unauthorized, token might have expired
            st.warning("Token expirado. Tentando renovar o token...")
            new_token, new_refresh_token = renovar_token(refresh_token)
            if new_token:
                st.session_state.access_token = new_token
                st.session_state.refresh_token = new_refresh_token
                headers["Authorization"] = f"Bearer {new_token}"
                response = requests.post(geracao_url, json=payload, headers=headers)
                if response.status_code == 200:
                    all_data.extend(response.json().get("Usinas", []))
                else:
                    st.error(f"Erro na requisição após renovar o token: {response.status_code}")
                    return None
            else:
                st.error("Não foi possível renovar o token. Faça login novamente.")
                return None
        elif response.status_code == 429:  # Too Many Requests
            st.warning("Limite de requisições atingido. Aguardando para tentar novamente...")
            time.sleep(60)  # Aguardar 60 segundos antes de tentar novamente
            return get_usina_generation_forecast(access_token, date, usinas, refresh_token)
        else:
            st.error(f"Erro na requisição: {response.status_code}")
            return None

    return {"Usinas": all_data}

# Função para exibir os dados no Streamlit como gráfico e tabela
def display_forecast(today_data, tomorrow_data, selected_usinas):
    if today_data or tomorrow_data:
        st.write(f"Previsão de Geração para Hoje e Amanhã")
        intervals = ["00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30", "04:00", "04:30", "05:00",
                     "05:30", "06:00", "06:30", "07:00", "07:30", "08:00", "08:30", "09:00", "09:30", "10:00",
                     "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00",
                     "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00", "19:30", "20:00",
                     "20:30", "21:00", "21:30", "22:00", "22:30", "23:00", "23:30", "24:00:00"]

        # Construir DataFrames para hoje e amanhã
        df_combined = pd.DataFrame({"Intervalo": intervals})

        for usina in selected_usinas:
            if today_data:
                usina_data_today = next((item for item in today_data["Usinas"] if item["Codigo"] == usina), None)
                if usina_data_today:
                    valores_por_intervalo = {v["PatamarHora"]: v["PatamarValor_PRE"] for v in usina_data_today.get("DadoInsumoPatamar", [])}
                    df_combined[usina + " (Hoje)"] = df_combined["Intervalo"].map(valores_por_intervalo)

            if tomorrow_data:
                usina_data_tomorrow = next((item for item in tomorrow_data["Usinas"] if item["Codigo"] == usina), None)
                if usina_data_tomorrow:
                    valores_por_intervalo = {v["PatamarHora"]: v["PatamarValor_PRE"] for v in usina_data_tomorrow.get("DadoInsumoPatamar", [])}
                    df_combined[usina + " (Amanhã)"] = df_combined["Intervalo"].map(valores_por_intervalo)

        # Reorganizar a tabela para exibir Hoje e Amanhã lado a lado
        if today_data and tomorrow_data:
            cols = []
            for usina in selected_usinas:
                cols.extend([usina + " (Hoje)", usina + " (Amanhã)"])
            df_combined = df_combined[["Intervalo"] + cols]

        # Exibir a tabela com formatação
        st.subheader("Tabela de Previsão de Geração")
        df_styled = df_combined.style.format({col: "{:.2f} MW" for col in df_combined.columns if col != "Intervalo"})
        st.dataframe(df_styled)

        # Criar um gráfico combinado para hoje e amanhã
        fig = go.Figure()

        color_discrete_map = {usina: f"hsl({i * 40}, 70%, 50%)" for i, usina in enumerate(selected_usinas)}

        # Adicionar as linhas de hoje
        for usina in selected_usinas:
            if usina + " (Hoje)" in df_combined.columns:
                fig.add_trace(go.Scatter(
                    x=df_combined["Intervalo"], y=df_combined[usina + " (Hoje)"],
                    mode='lines',
                    name=f"{usina} (Hoje)",
                    line=dict(color=color_discrete_map[usina])
                ))

        # Adicionar as linhas pontilhadas para amanhã
        for usina in selected_usinas:
            if usina + " (Amanhã)" in df_combined.columns:
                fig.add_trace(go.Scatter(
                    x=df_combined["Intervalo"], y=df_combined[usina + " (Amanhã)"],
                    mode='lines',
                    name=f"{usina} (Amanhã)",
                    line=dict(color=color_discrete_map[usina], dash='dot')
                ))

        fig.update_layout(
            title="Previsão de Geração para Hoje e Amanhã",
            xaxis_title="Intervalo",
            yaxis_title="Geração (MW)",
            xaxis_tickangle=-45
        )

        st.plotly_chart(fig)

    else:
        st.write("Nenhum dado disponível.")

# Interface principal
st.title("Previsão de Geração por Usina")

# Verificar se já temos os tokens na sessão
if "access_token" not in st.session_state or "refresh_token" not in st.session_state:
    # Interface de login
    st.sidebar.header("Login")
    login = st.sidebar.text_input("Usuário")
    senha = st.sidebar.text_input("Senha", type="password")
    if st.sidebar.button("Entrar"):
        access_token, refresh_token = get_token(login, senha)
        if access_token and refresh_token:
            st.session_state.access_token = access_token
            st.session_state.refresh_token = refresh_token
            st.success("Login bem-sucedido!")
        else:
            st.error("Falha no login. Verifique suas credenciais.")

# Se já estivermos logados
if "access_token" in st.session_state and "refresh_token" in st.session_state:
    # Data de hoje e amanhã
    today = datetime.today()
    tomorrow = today + timedelta(days=1)

    # Lista completa de usinas
    usinas = ["VLAB2", "VLAMZ", "VLARN", "VLCAN","VLCARC", "VLCNB", "VLFIG", "VLMNV", "VLSDMA", "VLSDMC", "VLSM2A"]
    
    # Filtros no menu lateral
    st.sidebar.header("Filtros")
    
    # Filtro para selecionar usinas
    selected_usinas = st.sidebar.multiselect("Selecione as Usinas", usinas, default=usinas)

    # Filtro para selecionar a data a ser mostrada (hoje, amanhã, ou ambos)
    date_choice = st.sidebar.radio("Escolha a Data", ["Hoje", "Amanhã", "Ambos"])

    # Obter dados com base no filtro selecionado
    today_data = tomorrow_data = None
    if date_choice in ["Hoje", "Ambos"]:
        today_data = get_usina_generation_forecast(st.session_state.access_token, today, selected_usinas, st.session_state.refresh_token)
    if date_choice in ["Amanhã", "Ambos"]:
        tomorrow_data = get_usina_generation_forecast(st.session_state.access_token, tomorrow, selected_usinas, st.session_state.refresh_token)

    # Exibir os dados no Streamlit como gráficos
    display_forecast(today_data, tomorrow_data, selected_usinas)
