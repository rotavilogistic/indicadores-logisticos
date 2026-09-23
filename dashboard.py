import streamlit as st
import duckdb
import pandas as pd
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

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
    
    # 1. Convertir las fechas. 'coerce' transforma las fechas falsas (0000-00-00) en nulos (NaT)
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce') 
    
    # 2. Purga de registros sin fecha
    df = df.dropna(subset=['Fecha'])
    
    # 3. PURGA DE OPERACIONES INTERNAS (NUEVO)
    # Conservamos ÚNICAMENTE las filas donde la Ruta contiene la palabra "CARRO"
    # Esto elimina operaciones como "CIERRE DE MES" o "BONO NUTRESA" de todos los cálculos.
    df = df[df['Ruta'].str.contains('CARRO', case=False, na=False)]
    
    return df

try:
    df_crudo = cargar_datos()
    
    # Creación de Pestañas Principales
    tab1, tab2 = st.tabs(["📊 Análisis Logístico (KPIs)", "💼 Control de Cartera (Pendientes)"])

    # ==========================================
    # PESTAÑA 1: ANÁLISIS LOGÍSTICO (OPERACIÓN)
    # ==========================================
    with tab1:
        st.sidebar.markdown("<h3 style='font-size: 20px;'>Minería de Datos (Logística)</h3>", unsafe_allow_html=True)
        st.sidebar.markdown("Filtros para el análisis de devoluciones:")

        # 1. Filtro Inteligente de Causales Ajenas (Regex)
        excluir_terceros = st.sidebar.checkbox("Excluir Causales Ajenas (Proveedor/Cliente)", value=False)
        
        # 2. CALENDARIOS INDEPENDIENTES (NUEVO)
        # Separamos inicio y fin para facilitar rangos largos (ej. todo el año)
        fecha_minima = df_crudo['Fecha'].min().date()
        fecha_maxima = df_crudo['Fecha'].max().date()

        col_f1, col_f2 = st.sidebar.columns(2)
        with col_f1:
            fecha_inicio = st.date_input("Fecha Inicio", value=fecha_minima, min_value=fecha_minima, max_value=fecha_maxima, key="f_ini_1")
        with col_f2:
            fecha_fin = st.date_input("Fecha Fin", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, key="f_fin_1")

        # Aplicamos la máscara de fechas
        mask = (df_crudo['Fecha'].dt.date >= fecha_inicio) & (df_crudo['Fecha'].dt.date <= fecha_fin)
        df_filtrado = df_crudo.loc[mask].copy()

        # 3. Lógica Regex para exclusión inteligente 
        if excluir_terceros:
            patron_ajenas = 'despacho|entrega|faltante|rotacion|vencimiento'
            mask_salvavidas = (df_filtrado['Estatus_Operacion'] != 'Devolucion') | (~df_filtrado['Motivo_Detalle'].str.contains(patron_ajenas, case=False, na=False))
            df_filtrado = df_filtrado[mask_salvavidas]
            

        # 4. Filtro de Vehículo
        rutas_disponibles = ["TODOS"] + sorted(df_filtrado['Ruta'].dropna().unique().tolist())
        ruta_seleccionada = st.sidebar.selectbox("Filtrar por Vehículo", rutas_disponibles)
        if ruta_seleccionada != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['Ruta'] == ruta_seleccionada]

        # 5. Filtro de Asesor
        asesores_disponibles = ["TODOS"] + sorted(df_filtrado['Asesor'].dropna().unique().tolist())
        asesor_seleccionado = st.sidebar.selectbox("Filtrar por Vendedor", asesores_disponibles)
        if asesor_seleccionado != "TODOS":
            df_filtrado = df_filtrado[df_filtrado['Asesor'] == asesor_seleccionado]

        # 6. Filtro de Causal Operativa (NUEVO)
        causales_disponibles = ["TODAS"] + sorted(df_filtrado['Motivo_Detalle'].dropna().unique().tolist())
        causal_seleccionada = st.sidebar.selectbox("Filtrar por Causal", causales_disponibles)
        if causal_seleccionada != "TODAS":
            df_filtrado = df_filtrado[df_filtrado['Motivo_Detalle'] == causal_seleccionada]    


        st.markdown("<h1 style='font-size: 28px;'>Indicadores logísticos</h1>", unsafe_allow_html=True)
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
        # GRÁFICO MACRO: TENDENCIA MENSUAL (LA JOYA DE LA CORONA)
        # ==========================================
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Tendencia Histórica: Evolución del Índice de Devolución</h2>", unsafe_allow_html=True)
        
        # 1. Crear columna de Mes-Año (Formato YYYY-MM)
        df_filtrado_tendencia = df_filtrado.copy()
        df_filtrado_tendencia['Mes'] = df_filtrado_tendencia['Fecha'].dt.to_period('M').astype(str)
        
        # 2. Agrupar dinero despachado y devuelto por mes
        despacho_mes = df_filtrado_tendencia[df_filtrado_tendencia['Estatus_Operacion'] == 'Despachado'].groupby('Mes')['Valor_Total'].sum().reset_index(name='Despachado')
        devolucion_mes = df_filtrado_tendencia[df_filtrado_tendencia['Estatus_Operacion'] == 'Devolucion'].groupby('Mes')['Valor_Total'].sum().reset_index(name='Devuelto')
        
        # 3. Unir y calcular el porcentaje de impacto
        tendencia = pd.merge(despacho_mes, devolucion_mes, on='Mes', how='outer').fillna(0)
        tendencia = tendencia.sort_values('Mes')
        tendencia['% Devolucion'] = (tendencia['Devuelto'] / tendencia['Despachado']) * 100
        
        # 4. Construir gráfico de doble eje (Barras + Línea)
        fig_tendencia = go.Figure()
        
        # Eje Y Primario: Dinero (Barras)
        fig_tendencia.add_trace(go.Bar(
            x=tendencia['Mes'], y=tendencia['Devuelto'],
            name='Impacto Financiero', marker_color='#d62728',
            hovertemplate='Mes: %{x}<br>Dinero Devuelto: $%{y:,.0f}'
        ))
        
        # Eje Y Secundario: Índice % (Línea)
        fig_tendencia.add_trace(go.Scatter(
            x=tendencia['Mes'], y=tendencia['% Devolucion'],
            name='Índice de Devolución (%)', mode='lines+markers', 
            line=dict(color='#1f77b4', width=4), marker=dict(size=10), 
            yaxis='y2', hovertemplate='Mes: %{x}<br>Índice Relativo: %{y:.2f}%'
        ))
        
        fig_tendencia.update_layout(
            title="Evolución Operativa Mensual", title_x=0.5, title_font_size=18,
            hovermode="x unified",
            xaxis=dict(type='category'), # <--- CORRECCIÓN: Fuerza el eje X a ser texto estático
            yaxis=dict(title="Dinero Devuelto ($)", side='left'),
            yaxis2=dict(title="Índice de Devolución (%)", side='right', overlaying='y', rangemode='tozero'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=400
        )
        # ---> NUEVO: Control de grosor para meses únicos
        if len(tendencia) == 1:
            fig_tendencia.update_traces(width=0.3, selector=dict(type='bar'))
            
        st.plotly_chart(fig_tendencia, use_container_width=True)    

        # GRÁFICOS NIVEL 1: RESPONSABLES
        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            resumen_rutas = df_devoluciones.groupby('Ruta')['Valor_Total'].sum().reset_index()
            resumen_rutas = resumen_rutas.sort_values(by='Valor_Total', ascending=True) 
            fig_rutas = px.bar(
                resumen_rutas, x='Valor_Total', y='Ruta', orientation='h',
                title="Impacto por Vehículo",
                labels={'Valor_Total': 'Dinero Devuelto ($)', 'Ruta': ''}, text_auto='.3s'
            )
            fig_rutas.update_layout(title_x=0.5, title_font_size=18, height=max(400, len(resumen_rutas)*30)) 

            fig_rutas.update_traces(hovertemplate='Ruta: %{y}<br>Dinero Devuelto: $%{x:,.0f}')
            st.plotly_chart(fig_rutas, use_container_width=True)

        with col_graf2:
            resumen_asesor = df_devoluciones.groupby('Asesor')['Valor_Total'].sum().reset_index()
            resumen_asesor = resumen_asesor.sort_values(by='Valor_Total', ascending=True)
            fig_asesor = px.bar(
                resumen_asesor, x='Valor_Total', y='Asesor', orientation='h',
                title="Impacto por Vendedor",
                labels={'Valor_Total': 'Dinero Devuelto ($)', 'Asesor': ''}, text_auto='.3s',
                color_discrete_sequence=['#ff7f0e']
            )
            fig_asesor.update_layout(title_x=0.5, title_font_size=18, height=max(400, len(resumen_asesor)*30))

            fig_asesor.update_traces(hovertemplate='Vendedor: %{y}<br>Dinero Devuelto: $%{x:,.0f}')
            st.plotly_chart(fig_asesor, use_container_width=True)

        # GRÁFICO NIVEL 2: CAUSA RAÍZ (PARETO)
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Análisis de Causa Raíz: Motivos de Devolución (Pareto)</h2>", unsafe_allow_html=True)
        
        resumen_motivos = df_devoluciones.groupby('Motivo_Detalle')['Valor_Total'].sum().reset_index()
        resumen_motivos = resumen_motivos.sort_values(by='Valor_Total', ascending=False)
        resumen_motivos['Porcentaje'] = (resumen_motivos['Valor_Total'] / resumen_motivos['Valor_Total'].sum()) * 100
        resumen_motivos['Acumulado'] = resumen_motivos['Porcentaje'].cumsum()
        
        fig_pareto = go.Figure()
        fig_pareto.add_trace(go.Bar(
            x=resumen_motivos['Motivo_Detalle'], y=resumen_motivos['Valor_Total'],
            name='Impacto Financiero', marker_color='#d62728',
            hovertemplate='Causal: %{x}<br>Dinero Devuelto: $%{y:,.0f}'
        ))
        fig_pareto.add_trace(go.Scatter(
            x=resumen_motivos['Motivo_Detalle'], y=resumen_motivos['Acumulado'],
            name='% Acumulado', mode='lines+markers', line=dict(color='#1f77b4', width=3),
            marker=dict(size=8), yaxis='y2', hovertemplate='% Acumulado: %{y:.1f}%'
        ))
        fig_pareto.update_layout(
            title="Distribución Financiera y Curva de Pareto (Regla 80/20)",
            title_x=0.5, title_font_size=18, hovermode="x unified",
            yaxis=dict(title="Dinero Devuelto ($)", side='left'),
            yaxis2=dict(title="Porcentaje Acumulado (%)", side='right', overlaying='y', range=[0, 105]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # ---> NUEVO: Control de grosor para causales únicas
        if len(resumen_motivos) == 1:
            fig_pareto.update_traces(width=0.3, selector=dict(type='bar'))
            
        st.plotly_chart(fig_pareto, use_container_width=True)

        # MAPA DE CALOR
        st.markdown("<h2 style='font-size: 22px;'>Mapa de Calor: Correlación Vehículo vs. Motivo</h2>", unsafe_allow_html=True)
        heatmap_data = df_devoluciones.groupby(['Ruta', 'Motivo_Detalle'])['Valor_Total'].sum().reset_index()
        heatmap_pivot = heatmap_data.pivot(index='Ruta', columns='Motivo_Detalle', values='Valor_Total').fillna(0)
        fig_heat = px.imshow(
            heatmap_pivot, labels=dict(x="Causal Operativa", y="Vehículo / Ruta", color="Dinero"),
            x=heatmap_pivot.columns, y=heatmap_pivot.index, color_continuous_scale='Reds', aspect="auto", text_auto='.2s'
        )
        fig_heat.update_layout(title_x=0.5, title_font_size=18, height=450)
        fig_heat.update_traces(hovertemplate='Ruta: %{y}<br>Motivo: %{x}<br>Impacto: %{z:,.0f}')
        st.plotly_chart(fig_heat, use_container_width=True)

        # CLIENTES Y PRODUCTOS
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
            fig_cli.update_layout(title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0))
            fig_cli.update_traces(hovertemplate='Cliente: %{y}<br>Dinero Devuelto: $%{x:,.0f}')
            st.plotly_chart(fig_cli, use_container_width=True)


        with col_prod:
            top_productos = df_devoluciones.groupby('Producto').agg({'Cantidad': 'sum', 'Valor_Total': 'sum'}).reset_index()
            top_productos = top_productos.sort_values(by='Cantidad', ascending=True).tail(10)
            fig_prod = px.bar(
                top_productos, x='Cantidad', y='Producto', orientation='h',
                title="Top 10 Productos (Fricción Logística - Unidades)", labels={'Cantidad': '', 'Producto': ''},
                text_auto='.0f', color_discrete_sequence=['#17becf'], hover_data={'Valor_Total': True} 
            )
            fig_prod.update_layout(title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0))
            fig_prod.update_traces(hovertemplate='Producto: %{y}<br>Unidades: %{x:,.0f}<br>Costo Devuelto: $%{customdata[0]:,.0f}')
            st.plotly_chart(fig_prod, use_container_width=True)

        # ÍNDICE DE EFICIENCIA RELATIVA
        st.markdown("---")
        st.markdown("<h2 style='font-size: 22px;'>Índice de Eficiencia: Tasa de Devolución Relativa</h2>", unsafe_allow_html=True)
        col_eff1, col_eff2 = st.columns(2)
        
        def calcular_eficiencia(columna_agrupacion):
            despacho = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Despachado')
            devolucion = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Devuelto')
            eficiencia = pd.merge(despacho, devolucion, on=columna_agrupacion, how='left').fillna(0)
            eficiencia['% Devolución'] = (eficiencia['Devuelto'] / eficiencia['Despachado']) * 100
            return eficiencia.sort_values(by='% Devolución', ascending=False)

        columnas_formateadas = {
            "Despachado": st.column_config.NumberColumn("Despachado", format="%,.0f"),
            "Devuelto": st.column_config.NumberColumn("Devuelto", format="%,.0f"),
            "% Devolución": st.column_config.ProgressColumn("% Devolución", format="%.2f%%", min_value=0, max_value=100)
        }
        with col_eff1:
            st.markdown("**Eficiencia por Vehículo (Ruta)**")
            st.dataframe(calcular_eficiencia('Ruta'), column_config=columnas_formateadas, hide_index=True, use_container_width=True)
        with col_eff2:
            st.markdown("**Eficiencia por Vendedor (Asesor)**")
            st.dataframe(calcular_eficiencia('Asesor'), column_config=columnas_formateadas, hide_index=True, use_container_width=True)

        # AUDITORÍA
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
        st.markdown("<h1 style='font-size: 28px;'>Control de Cartera: Planillas Pendientes </h1>", unsafe_allow_html=True)
        st.markdown("---")

        # CALENDARIOS INDEPENDIENTES (NUEVO)
        col_fecha_cart1, col_fecha_cart2 = st.columns([1, 1])
        with col_fecha_cart1:
            f_ini_cart = st.date_input("Fecha Inicio (Cartera)", value=fecha_minima, min_value=fecha_minima, max_value=fecha_maxima, key="f_ini_2")
        with col_fecha_cart2:
            f_fin_cart = st.date_input("Fecha Fin (Cartera)", value=fecha_maxima, min_value=fecha_minima, max_value=fecha_maxima, key="f_fin_2")

        mask_cart = (df_crudo['Fecha'].dt.date >= f_ini_cart) & (df_crudo['Fecha'].dt.date <= f_fin_cart)
        df_cartera_base = df_crudo.loc[mask_cart]

        # Lógica de Cartera: Filtrar estado 'P' y sumar solo lo despachado
        df_pendientes = df_cartera_base[(df_cartera_base['Estado_Planilla'] == 'P') & (df_cartera_base['Estatus_Operacion'] == 'Despachado')]
        
        if df_pendientes.empty:
            st.success("No hay planillas pendientes en el rango de fechas seleccionado. Toda la cartera está cerrada.")
        else:
            # Agrupación por Planilla, Fecha y Cliente
            cartera_consolidada = df_pendientes.groupby(['Planilla', 'Fecha', 'Cliente'])['Valor_Total'].sum().reset_index()
            # Formateo de fecha visual
            cartera_consolidada['Fecha'] = cartera_consolidada['Fecha'].dt.strftime('%Y-%m-%d')
            cartera_consolidada = cartera_consolidada.sort_values(by='Fecha', ascending=True)

            total_cartera = cartera_consolidada['Valor_Total'].sum()
            st.metric("Cartera Total Pendiente", f"${total_cartera:,.0f}")

            columnas_cartera = {
                "Valor_Total": st.column_config.NumberColumn("Valor a Cobrar", format="%,.0f"),
                "Fecha": st.column_config.TextColumn("Fecha de Entrega")
            }
            
            st.dataframe(cartera_consolidada, column_config=columnas_cartera, hide_index=True, use_container_width=True)

except Exception as e:
    st.error(f"Error al cargar el dashboard: {e}")