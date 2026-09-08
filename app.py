import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, date
import uuid
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Tarefas", layout="wide")

# Conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(worksheet):
    df = conn.read(worksheet=worksheet)
    if df.empty:
        if worksheet == "Tarefas":
            return pd.DataFrame(columns=["id_tarefa", "titulo", "urgencia", "importancia", "status_global", "contexto", "criado_em", "concluido_em"])
        else:
            return pd.DataFrame(columns=["id_instancia", "id_tarefa", "responsavel", "data_entrada", "data_saida", "observacoes"])
    return df

df_tarefas = load_data("Tarefas")
df_instancias = load_data("Instancias")

# Tratamento de segurança para colunas e valores nulos
colunas_tarefas_padrao = {
    "id_tarefa": "",
    "titulo": "",
    "urgencia": "Não Urgente",
    "importancia": "Não Importante",
    "status_global": "Pendente",
    "contexto": "Pessoal",
    "criado_em": "",
    "concluido_em": ""
}

for col, val_padrao in colunas_tarefas_padrao.items():
    if col not in df_tarefas.columns:
        df_tarefas[col] = val_padrao
    else:
        df_tarefas[col] = df_tarefas[col].fillna(val_padrao)

# Função utilitária para cálculo de tempo formatado
def calcular_tempo_decorrido(inicio_str, fim_str=None):
    try:
        dt_inicio = datetime.strptime(str(inicio_str).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Tempo Indefinido"
    
    if fim_str and str(fim_str).strip() != "":
        try:
            dt_fim = datetime.strptime(str(fim_str).strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_fim = datetime.now()
    else:
        dt_fim = datetime.now()
    
    delta = dt_fim - dt_inicio
    dias = delta.days
    horas = delta.seconds // 3600
    
    if dias > 0:
        return f"{dias}d {horas}h"
    return f"{horas}h"

# Menu Lateral para os Ambientes
st.sidebar.header("Ambientes")
contexto_escolhido = st.sidebar.radio("Selecione o painel atual:", ["Pessoal", "InnovaTerra", "Egas"])

st.title("Gestão de Tarefas")

# Abas da Aplicação
aba_dashboard, aba_gestao, aba_cadastro, aba_relatorios = st.tabs(["📊 Dashboard", "📋 Gestão e Fluxo", "➕ Nova Tarefa", "📄 Relatórios"])

# ================= ABA DASHBOARD =================
with aba_dashboard:
    st.subheader("📌 Quadro de Avisos (Pendências Prioritárias)")
    
    df_pendentes_geral = df_tarefas[df_tarefas["status_global"] != "Concluída"]
    
    col1, col2, col3 = st.columns(3)
    ambientes = [("Pessoal", col1), ("InnovaTerra", col2), ("Egas", col3)]
    
    for amb, col in ambientes:
        df_amb = df_pendentes_geral[df_pendentes_geral["contexto"] == amb]
        q1_fazer_agora = len(df_amb[(df_amb["importancia"] == "Importante") & (df_amb["urgencia"] == "Urgente")])
        q2_programe_se = len(df_amb[(df_amb["importancia"] == "Importante") & (df_amb["urgencia"] == "Não Urgente")])
        
        with col:
            st.info(f"**{amb}**\n\n🚨 Fazer Agora (1º): **{q1_fazer_agora}** tarefas\n\n📅 Programe-se (2º): **{q2_programe_se}** tarefas")

# ================= ABA GESTÃO E FLUXO =================
with aba_gestao:
    tarefas_filtro = df_tarefas[df_tarefas["contexto"] == contexto_escolhido]
    
    if tarefas_filtro.empty:
        st.info("Nenhuma tarefa ativa neste momento para este contexto.")
    
    for _, tarefa in tarefas_filtro.iterrows():
        id_t = tarefa["id_tarefa"]
        tit = tarefa["titulo"]
        urg = tarefa["urgencia"]
        imp = tarefa["importancia"]
        stat = tarefa["status_global"]
        
        with st.expander(f"[{urg} / {imp}] {tit} - (Status: {stat})"):
            col_status, col_instancia = st.columns(2)
            
            with col_status:
                st.markdown("**Atualizar Status Global**")
                lista_status = ["Pendente", "Em andamento", "Aguardando Setor/Pessoa", "Em revisão", "Concluída"]
                idx_atual = lista_status.index(stat) if stat in lista_status else 0
                novo_status = st.selectbox("Mudar para:", lista_status, index=idx_atual, key=f"status_{id_t}")
                
                if st.button("Salvar Status", key=f"btn_status_{id_t}"):
                    df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "status_global"] = novo_status
                    
                    if novo_status == "Concluída":
                        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "concluido_em"] = agora
                        # Encerra qualquer instância em aberto
                        mask = (df_instancias["id_tarefa"] == id_t) & (df_instancias["data_saida"].isna() | (df_instancias["data_saida"] == ""))
                        df_instancias.loc[mask, "data_saida"] = agora
                        conn.update(worksheet="Instancias", data=df_instancias)
                    else:
                        df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "concluido_em"] = ""
                        
                    conn.update(worksheet="Tarefas", data=df_tarefas)
                    st.cache_data.clear()
                    st.rerun()

            with col_instancia:
                st.markdown("**Encaminhar (Nova Instância)**")
                with st.form(f"form_inst_{id_t}", clear_on_submit=True):
                    responsavel = st.text_input("Responsável / Setor")
                    obs = st.text_area("Observações")
                    
                    if st.form_submit_button("Registrar Encaminhamento"):
                        if responsavel.strip():
                            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
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
                            st.cache_data.clear()
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
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.write("Sem histórico de tramitação.")

# ================= ABA NOVA TAREFA =================
with aba_cadastro:
    st.subheader("Adicionar Tarefa")
    with st.form("form_nova_tarefa", clear_on_submit=True):
        titulo = st.text_input("Título")
        urgencia = st.selectbox("Urgência", ["Urgente", "Não Urgente"])
        importancia = st.selectbox("Importância", ["Importante", "Não Importante"])
        
        if st.form_submit_button("Salvar"):
            if titulo.strip():
                nova_tarefa = pd.DataFrame([{
                    "id_tarefa": str(uuid.uuid4())[:8],
                    "titulo": titulo,
                    "urgencia": urgencia,
                    "importancia": importancia,
                    "status_global": "Pendente",
                    "contexto": contexto_escolhido,
                    "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "concluido_em": ""
                }])
                df_tarefas = pd.concat([df_tarefas, nova_tarefa], ignore_index=True)
                conn.update(worksheet="Tarefas", data=df_tarefas)
                st.cache_data.clear()
                st.success("Tarefa cadastrada!")
                st.rerun()

# ================= ABA RELATÓRIOS (PDF) =================
with aba_relatorios:
    st.subheader("Gerador de Relatórios (Matriz de Eisenhower)")
    
    def gerar_pdf_eisenhower(df_relatorio, titulo_pdf, is_concluida=False):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        pdf.set_font("helvetica", style="B", size=16)
        pdf.cell(w=0, h=10, text=titulo_pdf, new_x="LMARGIN", new_y="NEXT", align="C")
        
        # Subtítulo com timestamp da emissão
        pdf.set_font("helvetica", size=9)
        pdf.cell(w=0, h=6, text=f"Emitido em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)
        
        categorias = [
            ("1o) IMPORTANTE e URGENTE: FAZER AGORA!", "Importante", "Urgente"),
            ("2o) IMPORTANTE e NAO URGENTE: PROGRAME-SE!", "Importante", "Não Urgente"),
            ("3o) URGENTE e NAO IMPORTANTE: DELEGUE!", "Não Importante", "Urgente"),
            ("4o) NAO URGENTE e NAO IMPORTANTE: ELIMINE!", "Não Importante", "Não Urgente")
        ]
        
        largura_util = pdf.epw
        
        for nome_cat, imp, urg in categorias:
            pdf.set_font("helvetica", style="B", size=11)
            pdf.cell(w=largura_util, h=8, text=nome_cat, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("helvetica", size=10)
            filtro = df_relatorio[(df_relatorio["importancia"] == imp) & (df_relatorio["urgencia"] == urg)]
            
            if filtro.empty:
                pdf.cell(w=largura_util, h=6, text="  Nenhuma tarefa nesta categoria.", new_x="LMARGIN", new_y="NEXT")
            else:
                for _, row in filtro.iterrows():
                    fim = row["concluido_em"] if is_concluida else None
                    tempo_txt = calcular_tempo_decorrido(row["criado_em"], fim)
                    
                    rotulo_tempo = "Tempo de resolucao" if is_concluida else "Em andamento ha"
                    texto_tarefa = f"- {row['titulo']} [Contexto: {row['contexto']} | Status: {row['status_global']} | {rotulo_tempo}: {tempo_txt}]"
                    
                    texto_sanitizado = texto_tarefa.encode("latin-1", "replace").decode("latin-1")
                    
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(w=largura_util, h=6, text=texto_sanitizado, new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(4)
            
        return bytes(pdf.output())

    df_pendentes = df_tarefas[df_tarefas["status_global"] != "Concluída"]
    df_concluidas_base = df_tarefas[df_tarefas["status_global"] == "Concluída"].copy()

    col_pdf1, col_pdf2 = st.columns(2)
    
    with col_pdf1:
        st.markdown("### Tarefas Pendentes")
        st.caption("Calcula a duração desde o cadastro até o momento da emissão.")
        pdf_pendentes_bytes = gerar_pdf_eisenhower(df_pendentes, "Relatorio de Tarefas Pendentes", is_concluida=False)
        st.download_button(
            label="📥 Baixar PDF (Pendentes)",
            data=pdf_pendentes_bytes,
            file_name="tarefas_pendentes.pdf",
            mime="application/pdf",
            key="btn_dl_pendentes"
        )

    with col_pdf2:
        st.markdown("### Tarefas Concluídas")
        st.caption("Filtre o período de conclusão desejado:")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            data_ini = st.date_input("De:", value=date.today().replace(day=1), key="dt_ini")
        with col_d2:
            data_fim = st.date_input("Até:", value=date.today(), key="dt_fim")
            
        # Aplicação do filtro de data de conclusão
        df_concluidas_filtradas = pd.DataFrame()
        if not df_concluidas_base.empty:
            df_concluidas_base["dt_comp"] = pd.to_datetime(df_concluidas_base["concluido_em"], errors="coerce").dt.date
            df_concluidas_filtradas = df_concluidas_base[
                (df_concluidas_base["dt_comp"] >= data_ini) & (df_concluidas_base["dt_comp"] <= data_fim)
            ]
            
        pdf_concluidas_bytes = gerar_pdf_eisenhower(
            df_concluidas_filtradas, 
            f"Relatorio de Tarefas Concluidas ({data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')})", 
            is_concluida=True
        )
        st.download_button(
            label="📥 Baixar PDF (Concluídas)",
            data=pdf_concluidas_bytes,
            file_name=f"tarefas_concluidas_{data_ini}_{data_fim}.pdf",
            mime="application/pdf",
            key="btn_dl_concluidas"
        )
