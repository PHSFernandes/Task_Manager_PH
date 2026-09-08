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

# Tratamento de integridade e tipos de colunas em Tarefas
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
        df_tarefas[col] = df_tarefas[col].fillna(val_padrao).astype(str)

# Tratamento de integridade e tipos de colunas em Instancias (evita conflitos de tipos em datas e IDs)
colunas_instancias_padrao = {
    "id_instancia": "",
    "id_tarefa": "",
    "responsavel": "",
    "data_entrada": "",
    "data_saida": "",
    "observacoes": ""
}

for col, val_padrao in colunas_instancias_padrao.items():
    if col not in df_instancias.columns:
        df_instancias[col] = val_padrao
    else:
        df_instancias[col] = df_instancias[col].fillna(val_padrao).astype(str)

# Função para cálculo exato de tempo decorrido individual (dias e horas)
def calcular_tempo_decorrido(inicio_str, fim_str=None):
    try:
        dt_inicio = datetime.strptime(str(inicio_str).strip(), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Tempo Indefinido"
    
    if fim_str and str(fim_str).strip() not in ["", "None", "nan"]:
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

# Menu Lateral de Ambientes
st.sidebar.header("Ambientes")
contexto_escolhido = st.sidebar.radio("Selecione o painel atual:", ["Pessoal", "InnovaTerra", "Egas"])

st.title("Gestão de Tarefas")

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
    tarefas_contexto = df_tarefas[df_tarefas["contexto"] == contexto_escolhido]
    
    subaba_ativas, subaba_concluidas = st.tabs(["⏳ Tarefas em Andamento", "✅ Tarefas Concluídas"])

    def renderizar_lista_tarefas(df_lista, is_historico_concluidas=False):
        global df_tarefas, df_instancias
        
        if df_lista.empty:
            st.info("Nenhuma tarefa encontrada nesta seção.")
            return

        for _, tarefa in df_lista.iterrows():
            id_t = str(tarefa["id_tarefa"])
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
                    novo_status = st.selectbox("Mudar para:", lista_status, index=idx_atual, key=f"status_{id_t}_{is_historico_concluidas}")
                    
                    if st.button("Salvar Status", key=f"btn_status_{id_t}_{is_historico_concluidas}"):
                        df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "status_global"] = novo_status
                        
                        if novo_status == "Concluída":
                            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "concluido_em"] = agora
                            
                            mask = (df_instancias["id_tarefa"] == id_t) & (df_instancias["data_saida"].isin(["", "None", "nan"]))
                            df_instancias.loc[mask, "data_saida"] = agora
                            conn.update(worksheet="Instancias", data=df_instancias)
                        else:
                            df_tarefas.loc[df_tarefas["id_tarefa"] == id_t, "concluido_em"] = ""
                            
                        conn.update(worksheet="Tarefas", data=df_tarefas)
                        st.cache_data.clear()
                        st.rerun()

                with col_instancia:
                    st.markdown("**Encaminhar (Nova Instância)**")
                    with st.form(f"form_inst_{id_t}_{is_historico_concluidas}", clear_on_submit=True):
                        responsavel = st.text_input("Responsável / Setor")
                        obs = st.text_area("Observações")
                        
                        if st.form_submit_button("Registrar Encaminhamento"):
                            if responsavel.strip():
                                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                
                                # Encerra qualquer instância anterior em aberto para esta tarefa
                                mask = (df_instancias["id_tarefa"] == id_t) & (df_instancias["data_saida"].isin(["", "None", "nan"]))
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
                    saida_val = str(ultima_linha["data_saida"]).strip()
                    if saida_val in ["", "None", "nan"]:
                        if st.button("Concluir Etapa Atual", key=f"concluir_etapa_{id_t}_{is_historico_concluidas}"):
                            id_inst = str(ultima_linha["id_instancia"])
                            df_instancias.loc[df_instancias["id_instancia"] == id_inst, "data_saida"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            conn.update(worksheet="Instancias", data=df_instancias)
                            st.cache_data.clear()
                            st.rerun()
                else:
                    st.write("Sem histórico de tramitação.")

    with subaba_ativas:
        df_ativas = tarefas_contexto[tarefas_contexto["status_global"] != "Concluída"]
        renderizar_lista_tarefas(df_ativas, is_historico_concluidas=False)

    with subaba_concluidas:
        df_concluidas_ctx = tarefas_contexto[tarefas_contexto["status_global"] == "Concluída"]
        renderizar_lista_tarefas(df_concluidas_ctx, is_historico_concluidas=True)

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
    
    categorias_eisenhower = [
        ("1o) IMPORTANTE e URGENTE: FAZER AGORA!", "Importante", "Urgente"),
        ("2o) IMPORTANTE e NAO URGENTE: PROGRAME-SE!", "Importante", "Não Urgente"),
        ("3o) URGENTE e NAO IMPORTANTE: DELEGUE!", "Não Importante", "Urgente"),
        ("4o) NAO URGENTE e NAO IMPORTANTE: ELIMINE!", "Não Importante", "Não Urgente")
    ]

    def gerar_pdf_pendentes_por_contexto(df_dados, contextos_selecionados):
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        largura_util = pdf.epw

        for ctx in contextos_selecionados:
            pdf.add_page()
            
            pdf.set_font("helvetica", style="B", size=15)
            titulo_secao = f"Relatorio de Tarefas Pendentes - {ctx}"
            pdf.cell(w=0, h=9, text=titulo_secao.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT", align="C")
            
            pdf.set_font("helvetica", size=9)
            pdf.cell(w=0, h=5, text=f"Data de Emissao: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(4)
            
            df_ctx = df_dados[df_dados["contexto"] == ctx]
            
            for nome_cat, imp, urg in categorias_eisenhower:
                pdf.set_font("helvetica", style="B", size=11)
                pdf.cell(w=largura_util, h=8, text=nome_cat, new_x="LMARGIN", new_y="NEXT")
                
                pdf.set_font("helvetica", size=10)
                if df_ctx.empty or "importancia" not in df_ctx.columns:
                    filtro = pd.DataFrame()
                else:
                    filtro = df_ctx[(df_ctx["importancia"] == imp) & (df_ctx["urgencia"] == urg)]
                
                if filtro.empty:
                    pdf.cell(w=largura_util, h=6, text="  Nenhuma tarefa nesta categoria.", new_x="LMARGIN", new_y="NEXT")
                else:
                    for _, row in filtro.iterrows():
                        tempo_decorrido = calcular_tempo_decorrido(row.get("criado_em", ""), None)
                        texto_tarefa = f"- {row['titulo']} [Status: {row['status_global']} | Tempo decorrido: {tempo_decorrido}]"
                        texto_sanitizado = texto_tarefa.encode("latin-1", "replace").decode("latin-1")
                        
                        pdf.set_x(pdf.l_margin)
                        pdf.multi_cell(w=largura_util, h=6, text=texto_sanitizado, new_x="LMARGIN", new_y="NEXT")
                
                pdf.ln(3)
                
        return bytes(pdf.output())

    def gerar_pdf_concluidas(df_relatorio, titulo_pdf):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        pdf.set_font("helvetica", style="B", size=15)
        pdf.cell(w=0, h=9, text=titulo_pdf.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT", align="C")
        
        pdf.set_font("helvetica", size=9)
        pdf.cell(w=0, h=5, text=f"Data de Emissao: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(4)
        
        largura_util = pdf.epw
        
        for nome_cat, imp, urg in categorias_eisenhower:
            pdf.set_font("helvetica", style="B", size=11)
            pdf.cell(w=largura_util, h=8, text=nome_cat, new_x="LMARGIN", new_y="NEXT")
            
            pdf.set_font("helvetica", size=10)
            if df_relatorio.empty or "importancia" not in df_relatorio.columns:
                filtro = pd.DataFrame()
            else:
                filtro = df_relatorio[(df_relatorio["importancia"] == imp) & (df_relatorio["urgencia"] == urg)]
            
            if filtro.empty:
                pdf.cell(w=largura_util, h=6, text="  Nenhuma tarefa nesta categoria.", new_x="LMARGIN", new_y="NEXT")
            else:
                for _, row in filtro.iterrows():
                    fim = row.get("concluido_em", None)
                    tempo_resolucao = calcular_tempo_decorrido(row.get("criado_em", ""), fim)
                    texto_tarefa = f"- {row['titulo']} [Contexto: {row['contexto']} | Status: {row['status_global']} | Tempo de resolucao: {tempo_resolucao}]"
                    texto_sanitizado = texto_tarefa.encode("latin-1", "replace").decode("latin-1")
                    
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(w=largura_util, h=6, text=texto_sanitizado, new_x="LMARGIN", new_y="NEXT")
            
            pdf.ln(3)
            
        return bytes(pdf.output())

    df_pendentes = df_tarefas[df_tarefas["status_global"] != "Concluída"].copy()
    df_concluidas_base = df_tarefas[df_tarefas["status_global"] == "Concluída"].copy()

    col_pdf1, col_pdf2 = st.columns(2)
    
    # --- RELATÓRIO DE PENDENTES POR CONTEXTO ---
    with col_pdf1:
        st.markdown("### Tarefas Pendentes")
        st.caption("Selecione os ambientes desejados. Cada ambiente iniciará em uma página separada.")
        
        contextos_selecionados = st.multiselect(
            "Filtrar Ambientes:",
            options=["Pessoal", "InnovaTerra", "Egas"],
            default=["Pessoal", "InnovaTerra", "Egas"],
            key="ms_contextos_pendentes"
        )
        
        if st.button("Gerar Relatório de Pendentes", key="btn_gerar_pend"):
            if not contextos_selecionados:
                st.warning("Selecione ao menos um ambiente para emitir o relatório.")
            else:
                st.session_state["pdf_pendentes_data"] = gerar_pdf_pendentes_por_contexto(
                    df_pendentes, 
                    contextos_selecionados
                )
            
        if "pdf_pendentes_data" in st.session_state:
            st.download_button(
                label="📥 Baixar PDF (Pendentes)",
                data=st.session_state["pdf_pendentes_data"],
                file_name="tarefas_pendentes.pdf",
                mime="application/pdf",
                key="btn_dl_pendentes"
            )

    # --- RELATÓRIO DE CONCLUÍDAS COM FILTRO DE TEMPO ---
    with col_pdf2:
        st.markdown("### Tarefas Concluídas")
        st.caption("Calcula o tempo de resolução total (do cadastro ao encerramento).")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            data_ini = st.date_input("De (dd/mm/aaaa):", value=date.today().replace(day=1), format="DD/MM/YYYY", key="dt_ini")
        with col_d2:
            data_fim = st.date_input("Até (dd/mm/aaaa):", value=date.today(), format="DD/MM/YYYY", key="dt_fim")
            
        if st.button("Gerar Relatório de Concluídas", key="btn_gerar_conc"):
            df_concluidas_filtradas = df_concluidas_base.copy()
            
            if not df_concluidas_filtradas.empty:
                df_concluidas_filtradas["dt_comp"] = pd.to_datetime(df_concluidas_filtradas["concluido_em"], errors="coerce").dt.date
                df_concluidas_filtradas = df_concluidas_filtradas[
                    (df_concluidas_filtradas["dt_comp"] >= data_ini) & (df_concluidas_filtradas["dt_comp"] <= data_fim)
                ]
            else:
                df_concluidas_filtradas = pd.DataFrame(columns=df_tarefas.columns)
                
            st.session_state["pdf_concluidas_data"] = gerar_pdf_concluidas(
                df_concluidas_filtradas, 
                f"Relatorio de Tarefas Concluidas ({data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')})"
            )
            st.session_state["pdf_concluidas_nome"] = f"tarefas_concluidas_{data_ini}_{data_fim}.pdf"

        if "pdf_concluidas_data" in st.session_state:
            st.download_button(
                label="📥 Baixar PDF (Concluídas)",
                data=st.session_state["pdf_concluidas_data"],
                file_name=st.session_state.get("pdf_concluidas_nome", "tarefas_concluidas.pdf"),
                mime="application/pdf",
                key="btn_dl_concluidas"
            )
