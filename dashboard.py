import streamlit as st
import duckdb
import pandas as pd
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# 1. Configuración de la página
st.set_page_config(page_title="KPI Logística", layout="wide")

# 2. Conexión a DuckDB
directorio_actual = os.path.dirname(os.path.abspath(__file__))
ruta_db = os.path.join(directorio_actual, 'base de datos', 'logistica_master.duckdb')

@st.cache_data
def cargar_datos():
    con = duckdb.connect(database=ruta_db, read_only=True)
    df = con.execute("SELECT * FROM historico_entregas").df()
    con.close()
    
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce') 
    df = df.dropna(subset=['Fecha'])
    df = df[df['Ruta'].str.contains('CARRO', case=False, na=False)]
    
    # Pre-cálculos de velocidad y formato
    df['Fecha_Date'] = df['Fecha'].dt.date
    df['Mes_Num'] = df['Fecha'].dt.strftime('%m')
    df['Anio'] = df['Fecha'].dt.strftime('%Y')
    
    meses_es = {'01':'Ene', '02':'Feb', '03':'Mar', '04':'Abr', '05':'May', '06':'Jun', 
                '07':'Jul', '08':'Ago', '09':'Sep', '10':'Oct', '11':'Nov', '12':'Dic'}
    
    df['Mes_Texto'] = df['Mes_Num'].map(meses_es) + ' ' + df['Anio']
    df['Mes_Sort'] = df['Fecha'].dt.to_period('M').astype(str)
    
    patron_ajenas = 'despacho|entrega|faltante|rotacion|vencimiento'
    df['es_causal_ajena'] = df['Motivo_Detalle'].str.contains(patron_ajenas, case=False, na=False)
    
    return df

def formato_kpi(valor):
    if valor >= 1e6:
        return f"${valor/1e6:.1f}M".replace('.0M', 'M')
    elif valor >= 1e3:
        return f"${valor/1e3:.1f}k".replace('.0k', 'k')
    return f"${valor:.0f}"

try:
    df_crudo = cargar_datos()
    
    tab1, tab2 = st.tabs(["Análisis Logístico (KPIs)", "Control de Cartera (Pendientes)"])

    # ==========================================
    # PESTAÑA 1: ANÁLISIS LOGÍSTICO (OPERACIÓN)
    # ==========================================
    with tab1:
        st.sidebar.markdown("<h3 style='font-size: 20px;'>Minería de Datos (Logística)</h3>", unsafe_allow_html=True)
        st.sidebar.markdown("Filtros para el análisis de devoluciones:")

        excluir_terceros = st.sidebar.checkbox("Excluir Causales Ajenas (Proveedor/Cliente)", value=False)
        
        fecha_minima = df_crudo['Fecha_Date'].min()
        fecha_maxima = df_crudo['Fecha_Date'].max()

        col_f1, col_f2 = st.sidebar.columns(2)
        with col_f1:
            fecha_inicio = st.date_input("Fecha Inicio", value=fecha_minima, min_value=fecha_minima, max_value=fecha_maxima, key="f_ini_1")
        with col_f2:
            fecha_fin = st.date_input("Fecha Fin", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, key="f_fin_1")

        mask = (df_crudo['Fecha_Date'] >= fecha_inicio) & (df_crudo['Fecha_Date'] <= fecha_fin)
        df_filtrado = df_crudo.loc[mask].copy()

        if excluir_terceros:
            mask_salvavidas = (df_filtrado['Estatus_Operacion'] != 'Devolucion') | (~df_filtrado['es_causal_ajena'])
            df_filtrado = df_filtrado[mask_salvavidas]
            
        rutas_disponibles = ["TODOS"] + sorted(df_filtrado['Ruta'].dropna().unique().tolist())
        ruta_seleccionada = st.sidebar.selectbox("Filtrar por Vehículo", rutas_disponibles)
        if ruta_seleccionada != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['Ruta'] == ruta_seleccionada]

        asesores_disponibles = ["TODOS"] + sorted(df_filtrado['Asesor'].dropna().unique().tolist())
        asesor_seleccionado = st.sidebar.selectbox("Filtrar por Vendedor", asesores_disponibles)
        if asesor_seleccionado != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['Asesor'] == asesor_seleccionado]

        causales_disponibles = ["TODAS"] + sorted(df_filtrado['Motivo_Detalle'].dropna().unique().tolist())
        causal_seleccionada = st.sidebar.selectbox("Filtrar por Causal", causales_disponibles)
        if causal_seleccionada != "TODAS":
            df_filtrado = df_filtrado[df_filtrado['Motivo_Detalle'] == causal_seleccionada]    

        st.markdown("<h1 style='font-size: 28px;'>Indicadores Logísticos</h1>", unsafe_allow_html=True)
        st.markdown("---")

        total_despachado = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado']['Valor_Total'].sum()
        total_devuelto = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion']['Valor_Total'].sum()
        porcentaje_devolucion = (total_devuelto / total_despachado) * 100 if total_despachado > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Facturado / Despachado", f"${total_despachado:,.0f}")
        col2.metric("Total Devuelto", f"${total_devuelto:,.0f}")
        col3.metric("% de Devolución (Valor)", f"{porcentaje_devolucion:.2f}%")
        
        df_devoluciones = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion']

        # ==========================================
        # GRÁFICO MACRO: TENDENCIA MENSUAL
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Tendencia Histórica: Evolución del Índice de Devolución</h2>", unsafe_allow_html=True)
        
        despacho_mes = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado'].groupby(['Mes_Sort', 'Mes_Texto'])['Valor_Total'].sum().reset_index(name='Despachado')
        devolucion_mes = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion'].groupby(['Mes_Sort', 'Mes_Texto'])['Valor_Total'].sum().reset_index(name='Devuelto')
        
        tendencia = pd.merge(despacho_mes, devolucion_mes, on=['Mes_Sort', 'Mes_Texto'], how='outer').fillna(0)
        tendencia = tendencia.sort_values('Mes_Sort')
        tendencia['% Devolucion'] = np.where(tendencia['Despachado'] > 0, (tendencia['Devuelto'] / tendencia['Despachado']) * 100, 0)
        
        tendencia['Eje_X'] = tendencia['Mes_Texto'] + '<br><b>' + tendencia['Devuelto'].apply(formato_kpi) + '</b>'
        
        fig_tendencia = go.Figure()
        
        if len(tendencia) > 1:
            x_numeric = np.arange(len(tendencia))
            z = np.polyfit(x_numeric, tendencia['% Devolucion'].values, 1)
            p = np.poly1d(z)
            fig_tendencia.add_trace(go.Scatter(
                x=tendencia['Eje_X'], y=p(x_numeric), 
                name='Tendencia Global', mode='lines', 
                line=dict(color='rgba(241, 196, 15, 0.6)', width=2, dash='dot'), yaxis='y2',
                hoverinfo='skip'
            ))

        fig_tendencia.add_trace(go.Bar(
            x=tendencia['Eje_X'], y=tendencia['Devuelto'],
            name='Impacto Financiero', marker_color='rgba(214, 39, 40, 0.85)',
            hovertemplate='Dinero Devuelto: $%{y:,.0f}'
        ))
        
        fig_tendencia.add_trace(go.Scatter(
            x=tendencia['Eje_X'], y=tendencia['% Devolucion'],
            name='Índice de Devolución (%)', mode='lines+markers', 
            line=dict(color='#3498db', width=3), 
            marker=dict(size=8, color='#3498db', symbol='circle-open', line=dict(width=2)), 
            yaxis='y2', hovertemplate='Índice Relativo: %{y:.2f}%'
        ))

        for i, row in tendencia.iterrows():
            if row['Despachado'] > 0: 
                fig_tendencia.add_annotation(
                    x=row['Eje_X'], y=row['% Devolucion'], yref="y2",
                    text=f"{row['% Devolucion']:.2f}%",
                    showarrow=False,
                    yshift=25, 
                    font=dict(color="#3498db", size=12, family="Arial"),
                    bgcolor="rgba(15, 23, 42, 0.9)", bordercolor="rgba(52, 152, 219, 0.4)", borderwidth=1, borderpad=3
                )

        max_money = tendencia['Devuelto'].max() if not tendencia.empty else 100
        max_pct = tendencia['% Devolucion'].max() if not tendencia.empty else 100
        
        fig_tendencia.update_layout(
            title="", hovermode="x unified",
            xaxis=dict(type='category', showgrid=False, title=""), 
            yaxis=dict(title="Dinero Devuelto ($)", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, max_money * 1.2]), 
            yaxis2=dict(title="Índice (%)", showgrid=False, showticklabels=True, overlaying='y', side='right', range=[0, max_pct * 1.4]), 
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=480, margin=dict(t=30, b=60, l=10, r=10)
        )
        st.plotly_chart(fig_tendencia, use_container_width=True)

        # ==========================================
        # GRÁFICOS NIVEL 1: RESPONSABLES
        # ==========================================
        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            resumen_rutas = df_devoluciones.groupby('Ruta')['Valor_Total'].sum().reset_index()
            resumen_rutas = resumen_rutas.sort_values(by='Valor_Total', ascending=True).tail(10)
            fig_rutas = px.bar(
                resumen_rutas, x='Valor_Total', y='Ruta', orientation='h',
                title="Top 10: Impacto por Vehículo",
                labels={'Valor_Total': '', 'Ruta': ''}, text_auto='.3s'
            )
            fig_rutas.update_layout(
                title_x=0.5, title_font_size=18, height=380,
                xaxis=dict(title="Dinero ($)", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, resumen_rutas['Valor_Total'].max() * 1.2]),
                yaxis=dict(showgrid=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_rutas.update_traces(hovertemplate='Ruta: %{y}<br>Dinero Devuelto: $%{x:,.0f}', textposition='outside')
            st.plotly_chart(fig_rutas, use_container_width=True)

        with col_graf2:
            resumen_asesor = df_devoluciones.groupby('Asesor')['Valor_Total'].sum().reset_index()
            resumen_asesor = resumen_asesor.sort_values(by='Valor_Total', ascending=True).tail(10)
            fig_asesor = px.bar(
                resumen_asesor, x='Valor_Total', y='Asesor', orientation='h',
                title="Top 10: Impacto por Vendedor",
                labels={'Valor_Total': '', 'Asesor': ''}, text_auto='.3s',
                color_discrete_sequence=['#ff7f0e']
            )
            fig_asesor.update_layout(
                title_x=0.5, title_font_size=18, height=380,
                xaxis=dict(title="Dinero ($)", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, resumen_asesor['Valor_Total'].max() * 1.2]),
                yaxis=dict(showgrid=False), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_asesor.update_traces(hovertemplate='Vendedor: %{y}<br>Dinero Devuelto: $%{x:,.0f}', textposition='outside')
            st.plotly_chart(fig_asesor, use_container_width=True)

        # ==========================================
        # GRÁFICO NIVEL 2: CAUSA RAÍZ (PARETO TOP 5)
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Análisis de Causa Raíz: Top 5 Motivos de Devolución</h2>", unsafe_allow_html=True)
        
        resumen_motivos = df_devoluciones.groupby('Motivo_Detalle')['Valor_Total'].sum().reset_index()
        resumen_motivos = resumen_motivos.sort_values(by='Valor_Total', ascending=False)
        resumen_motivos['Porcentaje'] = (resumen_motivos['Valor_Total'] / resumen_motivos['Valor_Total'].sum()) * 100
        resumen_motivos['Acumulado'] = resumen_motivos['Porcentaje'].cumsum()
        
        resumen_motivos = resumen_motivos.head(5) 
        resumen_motivos['Eje_X'] = resumen_motivos['Motivo_Detalle'] + '<br><b>' + resumen_motivos['Valor_Total'].apply(formato_kpi) + '</b>'
        
        fig_pareto = go.Figure()
        
        fig_pareto.add_trace(go.Bar(
            x=resumen_motivos['Eje_X'], y=resumen_motivos['Valor_Total'],
            name='Impacto Financiero', marker_color='rgba(214, 39, 40, 0.85)',
            hovertemplate='Dinero Devuelto: $%{y:,.0f}'
        ))
        
        fig_pareto.add_trace(go.Scatter(
            x=resumen_motivos['Eje_X'], y=resumen_motivos['Acumulado'],
            name='% Acumulado', mode='lines+markers', 
            line=dict(color='#3498db', width=3), marker=dict(size=8, color='#3498db', symbol='circle-open', line=dict(width=2)), yaxis='y2', 
            hovertemplate='% Acumulado: %{y:.1f}%'
        ))

        for i, row in resumen_motivos.iterrows():
            fig_pareto.add_annotation(
                x=row['Eje_X'], y=row['Acumulado'], yref="y2",
                text=f"{row['Acumulado']:.1f}%",
                showarrow=False,
                yshift=25, 
                font=dict(color="#3498db", size=12, family="Arial"),
                bgcolor="rgba(15, 23, 42, 0.9)", bordercolor="rgba(52, 152, 219, 0.4)", borderwidth=1, borderpad=3
            )
        
        max_motivos_money = resumen_motivos['Valor_Total'].max() if not resumen_motivos.empty else 100
        
        fig_pareto.update_layout(
            title="", hovermode="x unified",
            xaxis=dict(type='category', showgrid=False, title=""),
            yaxis=dict(title="Dinero Devuelto ($)", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, max_motivos_money * 1.2]),
            yaxis2=dict(title="Porcentaje (%)", showgrid=False, showticklabels=True, overlaying='y', side='right', range=[0, 115]), 
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=480, margin=dict(t=30, b=60, l=10, r=10)
        )
        st.plotly_chart(fig_pareto, use_container_width=True)

        # ==========================================
        # CLIENTES Y PRODUCTOS
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Análisis Específico: Clientes y Fricción de Inventario</h2>", unsafe_allow_html=True)
        col_cli, col_prod = st.columns(2)
        with col_cli:
            top_clientes = df_devoluciones.groupby('Cliente')['Valor_Total'].sum().reset_index()
            top_clientes = top_clientes.sort_values(by='Valor_Total', ascending=True).tail(10) 
            fig_cli = px.bar(
                top_clientes, x='Valor_Total', y='Cliente', orientation='h',
                title="Top 10 Clientes (Impacto Financiero)", labels={'Valor_Total': '', 'Cliente': ''},
                text_auto='.3s', color_discrete_sequence=['#8c564b']
            )
            fig_cli.update_layout(
                title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(title="Dinero ($)", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, top_clientes['Valor_Total'].max() * 1.2]), yaxis=dict(showgrid=False),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_cli.update_traces(hovertemplate='Cliente: %{y}<br>Dinero Devuelto: $%{x:,.0f}', textposition='outside')
            st.plotly_chart(fig_cli, use_container_width=True)

        with col_prod:
            top_productos = df_devoluciones.groupby('Producto').agg({'Cantidad': 'sum', 'Valor_Total': 'sum'}).reset_index()
            top_productos = top_productos.sort_values(by='Cantidad', ascending=True).tail(10)
            fig_prod = px.bar(
                top_productos, x='Cantidad', y='Producto', orientation='h',
                title="Top 10 Productos (Fricción Logística - Unidades)", labels={'Cantidad': '', 'Producto': ''},
                text_auto='.0f', color_discrete_sequence=['#17becf'], hover_data={'Valor_Total': True} 
            )
            fig_prod.update_layout(
                title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0),
                xaxis=dict(title="Unidades", showgrid=True, gridcolor='rgba(255,255,255,0.08)', showticklabels=True, range=[0, top_productos['Cantidad'].max() * 1.2]), yaxis=dict(showgrid=False),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
            )
            fig_prod.update_traces(hovertemplate='Producto: %{y}<br>Unidades: %{x:,.0f}<br>Costo Devuelto: $%{customdata[0]:,.0f}', textposition='outside')
            st.plotly_chart(fig_prod, use_container_width=True)

        # ==========================================
        # ÍNDICE DE EFICIENCIA RELATIVA
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Índice de Eficiencia: Tasa de Devolución Relativa</h2>", unsafe_allow_html=True)
        col_eff1, col_eff2 = st.columns(2)
        
        def calcular_eficiencia(columna_agrupacion):
            despacho = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Despachado')
            devolucion = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Devuelto')
            eficiencia = pd.merge(despacho, devolucion, on=columna_agrupacion, how='left').fillna(0)
            eficiencia['% Devolución'] = np.where(eficiencia['Despachado'] > 0, (eficiencia['Devuelto'] / eficiencia['Despachado']) * 100, 0)
            return eficiencia.sort_values(by='% Devolución', ascending=False)

        columnas_formateadas = {
            "Despachado": st.column_config.NumberColumn("Despachado", format="%,.0f"),
            "Devuelto": st.column_config.NumberColumn("Devuelto", format="%,.0f"),
            "% Devolución": st.column_config.NumberColumn("% Devolución", format="%.2f%%")
        }
        with col_eff1:
            st.markdown("**Eficiencia por Vehículo (Ruta)**")
            st.dataframe(calcular_eficiencia('Ruta'), column_config=columnas_formateadas, hide_index=True, use_container_width=True)
        with col_eff2:
            st.markdown("**Eficiencia por Vendedor (Asesor)**")
            st.dataframe(calcular_eficiencia('Asesor'), column_config=columnas_formateadas, hide_index=True, use_container_width=True)

        # ==========================================
        # AUDITORÍA
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Auditoría de Facturas (Drill-Down)</h2>", unsafe_allow_html=True)
        columnas_auditoria = {
            "Valor_Total": st.column_config.NumberColumn("Valor_Total", format="%,.0f"),
            "Cantidad": st.column_config.NumberColumn("Cantidad", format="%,.0f")
        }
        st.dataframe(df_devoluciones.sort_values(by='Valor_Total', ascending=False), column_config=columnas_auditoria, hide_index=True, use_container_width=True)

    # ==========================================
    # PESTAÑA 2: CONTROL DE CARTERA (PENDIENTES)
    # ==========================================
    with tab2:
        st.markdown("<h1 style='font-size: 28px;'>Control de Cartera: Estado de Planillas</h1>", unsafe_allow_html=True)
        st.markdown("---")

        col_fecha_cart1, col_fecha_cart2 = st.columns([1, 1])
        with col_fecha_cart1:
            f_ini_cart = st.date_input("Fecha Inicio (Cartera)", value=fecha_minima, min_value=fecha_minima, max_value=fecha_maxima, key="f_ini_2")
        with col_fecha_cart2:
            f_fin_cart = st.date_input("Fecha Fin (Cartera)", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, key="f_fin_2")

        # Filtro ultra-rápido de fechas ya formateadas
        mask_cart = (df_crudo['Fecha_Date'] >= f_ini_cart) & (df_crudo['Fecha_Date'] <= f_fin_cart)
        df_cartera_base = df_crudo.loc[mask_cart]

        # 1. INDICADORES DE CIERRE GERENCIALES
        total_planillas = df_cartera_base['Planilla'].nunique()
        planillas_cerradas = df_cartera_base[df_cartera_base['Estado_Planilla'] == 'C']['Planilla'].nunique()
        planillas_pendientes = df_cartera_base[df_cartera_base['Estado_Planilla'] == 'P']['Planilla'].nunique()
        porcentaje_cierre = (planillas_cerradas / total_planillas * 100) if total_planillas > 0 else 0
        
        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
        col_kpi1.metric("Total Planillas (Ruta)", f"{total_planillas:,}")
        col_kpi2.metric("Planillas Cerradas", f"{planillas_cerradas:,}")
        col_kpi3.metric("Planillas Pendientes", f"{planillas_pendientes:,}")
        col_kpi4.metric("Índice de Cierre", f"{porcentaje_cierre:.1f}%")
        
        st.markdown("---")

        # 2. TABLAS DE RESUMEN
        df_pendientes = df_cartera_base[(df_cartera_base['Estado_Planilla'] == 'P') & (df_cartera_base['Estatus_Operacion'] == 'Despachado')]
        
        if df_pendientes.empty:
            st.info("No hay planillas pendientes en el rango de fechas seleccionado. Toda la cartera está cerrada.")
        else:
            total_cartera = df_pendientes['Valor_Total'].sum()
            st.markdown(f"### Cartera Total Pendiente: **${total_cartera:,.0f}**")
            
            col_tab1, col_tab2 = st.columns([1, 2])
            
            with col_tab1:
                st.markdown("#### Resumen por Asesor")
                cartera_asesor = df_pendientes.groupby('Asesor')['Valor_Total'].sum().reset_index()
                cartera_asesor = cartera_asesor.sort_values('Valor_Total', ascending=False)
                
                st.dataframe(
                    cartera_asesor,
                    column_config={
                        "Asesor": "Asesor Comercial",
                        "Valor_Total": st.column_config.NumberColumn("Cartera Total", format="$%,.0f")
                    },
                    hide_index=True,
                    use_container_width=True
                )
            
            with col_tab2:
                st.markdown("#### Planillas Pendientes")
                
                # Se removió la columna Asesor a petición
                cartera_planilla = df_pendientes.groupby(['Fecha_Date', 'Planilla']).agg(
                    Clientes_Distintos=('Codigo_Cliente', 'nunique'),
                    Valor_Total=('Valor_Total', 'sum')
                ).reset_index()
                cartera_planilla = cartera_planilla.sort_values('Fecha_Date', ascending=True)
                
                columnas_planilla = {
                    "Fecha_Date": "Fecha Ruta",
                    "Planilla": "N° Planilla",
                    "Clientes_Distintos": "N° Clientes",
                    "Valor_Total": st.column_config.NumberColumn("Valor a Cobrar", format="$%,.0f")
                }

                # Funcionalidad de clic en la fila (Drill-Down)
                try:
                    seleccion = st.dataframe(
                        cartera_planilla,
                        column_config=columnas_planilla,
                        hide_index=True,
                        use_container_width=True,
                        on_select="rerun",
                        selection_mode="single-row"
                    )
                    
                    st.markdown("---")
                    
                    if len(seleccion.selection.rows) > 0:
                        fila_idx = seleccion.selection.rows[0]
                        planilla_id = cartera_planilla.iloc[fila_idx]['Planilla']
                        
                        st.markdown(f"#### Detalle Operativo: Planilla {planilla_id}")
                        df_detalle = df_pendientes[df_pendientes['Planilla'] == planilla_id][['Fecha_Date', 'Planilla', 'Asesor', 'Codigo_Cliente', 'Cliente', 'Factura', 'Valor_Total']]
                        df_detalle = df_detalle.sort_values('Cliente')
                        
                        st.dataframe(
                            df_detalle,
                            column_config={
                                "Fecha_Date": "Fecha",
                                "Planilla": "Planilla",
                                "Asesor": "Asesor",
                                "Codigo_Cliente": "Cód.",
                                "Cliente": "Cliente",
                                "Factura": "Factura",
                                "Valor_Total": st.column_config.NumberColumn("Valor", format="$%,.0f")
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.info("Haz clic en una fila de la tabla superior para desplegar el detalle de las facturas.")

                except TypeError:
                    st.dataframe(cartera_planilla, column_config=columnas_planilla, hide_index=True, use_container_width=True)
                    st.markdown("---")
                    st.markdown("#### Detalle Operativo")
                    planilla_seleccionada = st.selectbox("Seleccionar Planilla para Detalle:", ["Ver Todas"] + list(cartera_planilla['Planilla'].unique()))
                    
                    if planilla_seleccionada == "Ver Todas":
                        df_detalle = df_pendientes[['Fecha_Date', 'Planilla', 'Asesor', 'Codigo_Cliente', 'Cliente', 'Factura', 'Valor_Total']]
                    else:
                        df_detalle = df_pendientes[df_pendientes['Planilla'] == planilla_seleccionada][['Fecha_Date', 'Planilla', 'Asesor', 'Codigo_Cliente', 'Cliente', 'Factura', 'Valor_Total']]
                        
                    st.dataframe(
                        df_detalle.sort_values(['Planilla', 'Cliente']),
                        column_config={
                            "Fecha_Date": "Fecha",
                            "Planilla": "Planilla",
                            "Asesor": "Asesor",
                            "Codigo_Cliente": "Cód.",
                            "Cliente": "Cliente",
                            "Factura": "Factura",
                            "Valor_Total": st.column_config.NumberColumn("Valor", format="$%,.0f")
                        },
                        hide_index=True,
                        use_container_width=True
                    )

            # 3. TABLA ORIGINAL RESTAURADA A PANTALLA COMPLETA
            st.markdown("---")
            st.markdown("### Detalle General de Cartera por Cliente")
            
            cartera_consolidada = df_pendientes.groupby(['Planilla', 'Fecha_Date', 'Cliente'])['Valor_Total'].sum().reset_index()
            cartera_consolidada = cartera_consolidada.sort_values(by=['Fecha_Date', 'Planilla'], ascending=True)

            columnas_cartera = {
                "Planilla": "Planilla",
                "Fecha_Date": "Fecha de Entrega",
                "Cliente": "Cliente",
                "Valor_Total": st.column_config.NumberColumn("Valor a Cobrar", format="$%,.0f")
            }
            
            st.dataframe(cartera_consolidada, column_config=columnas_cartera, hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"Error al cargar el dashboard: {e}")