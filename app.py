import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import uuid

st.set_page_config(page_title="Gestão de Tarefas", layout="wide")

# Conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Função para garantir que os dados sejam tratados como DataFrame
def load_data(worksheet):
    df = conn.read(worksheet=worksheet)
    if df.empty:
        if worksheet == "Tarefas":
            return pd.DataFrame(columns=["id_tarefa", "titulo", "urgencia", "status_global", "contexto", "criado_em"])
        else:
            return pd.DataFrame(columns=["id_instancia", "id_tarefa", "responsavel", "data_entrada", "data_saida", "observacoes"])
    return df

df_tarefas = load_data("Tarefas")
df_instancias = load_data("Instancias")

st.sidebar.header("Ambientes")
contexto_escolhido = st.sidebar.radio("Selecione o painel atual:", ["Pessoal", "InnovaTerra", "Egas"])
st.title(f"Gestão de Tarefas - {contexto_escolhido}")

aba_gestao, aba_cadastro = st.tabs(["📋 Gestão e Fluxo", "➕ Nova Tarefa"])

with aba_cadastro:
    st.subheader("Adicionar Tarefa")
    with st.form("form_nova_tarefa", clear_on_submit=True):
        titulo = st.text_input("Título")
        urgencia = st.selectbox("Urgência", ["Baixa", "Média", "Alta", "Urgente"])
        if st.form_submit_button("Salvar"):
            if titulo.strip():
                nova_tarefa = pd.DataFrame([{
                    "id_tarefa": str(uuid.uuid4())[:8],
                    "titulo": titulo,
                    "urgencia": urgencia,
                    "status_global": "Pendente",
                    "contexto": contexto_escolhido,
                    "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }])
                df_tarefas = pd.concat([df_tarefas, nova_tarefa], ignore_index=True)
                conn.update(worksheet="Tarefas", data=df_tarefas)
                st.success("Tarefa cadastrada!")
                st.rerun()

with aba_gestao:
    # Filtra as tarefas do contexto
    tarefas_filtro = df_tarefas[df_tarefas["contexto"] == contexto_escolhido]
    
    if tarefas_filtro.empty:
        st.info("Nenhuma tarefa ativa neste momento para este contexto.")
    
    for _, tarefa in tarefas_filtro.iterrows():
        id_t = tarefa["id_tarefa"]
        tit = tarefa["titulo"]
        urg = tarefa["urgencia"]
        stat = tarefa["status_global"]
        
        with st.expander(f"[{urg}] {tit} - (Status atual: {stat})"):
            col_status, col_instancia = st.columns(2)
            
            with col_status:
                st.markdown("**Atualizar Status Global**")
                lista_status = ["Pendente", "Em andamento", "Aguardando Setor/Pessoa", "Em revisão", "Concluída"]
                idx_atual = lista_status.index(stat) if stat in lista_status else 0
                novo_status = st.selectbox("Mudar para:", lista_status, index=idx_atual, key=f"status_{id_t}")
                
                if st.button("Salvar Status", key=f"btn_status_{id_t}"):
                    df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "status_global"] = novo_status
                    conn.update(worksheet="Tarefas", data=df_tarefas)
                    st.rerun()

            with col_instancia:
                st.markdown("**Encaminhar (Nova Instância)**")
                with st.form(f"form_inst_{id_t}", clear_on_submit=True):
                    responsavel = st.text_input("Responsável / Setor")
                    obs = st.text_area("Observações")
                    
                    if st.form_submit_button("Registrar Encaminhamento"):
                        if responsavel.strip():
                            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            # Fecha instâncias anteriores abertas desta tarefa
                            mask = (df_instancias["id_tarefa"] == id_t) & (df_instancias["data_saida"].isna() | (df_instancias["data_saida"] == ""))
                            df_instancias.loc[mask, "data_saida"] = agora
                            
                            nova_instancia = pd.DataFrame([{
                                "id_instancia": str(uuid.uuid4())[:8],
                                "id_tarefa": id_t,
                                "responsavel": responsavel,
                                "data_entrada": agora,
                                "data_saida": "",
                                "observacoes": obs
                            }])
                            df_instancias = pd.concat([df_instancias, nova_instancia], ignore_index=True)
                            conn.update(worksheet="Instancias", data=df_instancias)
                            st.rerun()

            st.markdown("---")
            st.markdown("**Histórico e Tempo de Resolução**")
            
            instancias_tarefa = df_instancias[df_instancias["id_tarefa"] == id_t]
            if not instancias_tarefa.empty:
                st.dataframe(instancias_tarefa[["responsavel", "data_entrada", "data_saida", "observacoes"]], hide_index=True, use_container_width=True)
                
                ultima_linha = instancias_tarefa.iloc[-1]
                if pd.isna(ultima_linha["data_saida"]) or ultima_linha["data_saida"] == "":
                    if st.button("Concluir Etapa Atual", key=f"concluir_etapa_{id_t}"):
                        id_inst = ultima_linha["id_instancia"]
                        df_instancias.loc[df_instancias["id_instancia"] == id_inst, "data_saida"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        conn.update(worksheet="Instancias", data=df_instancias)
                        st.rerun()
            else:
                st.write("Sem histórico de tramitação.")
