import streamlit as st
import duckdb
import pandas as pd
import os
from datetime import datetime
import plotly.express as px

# 1. Configuración de la página (Sin emoji en la pestaña del navegador)
st.set_page_config(page_title="KPI Logística", layout="wide")

# 2. Conexión a DuckDB
directorio_actual = os.path.dirname(os.path.abspath(__file__))
ruta_db = os.path.join(directorio_actual, 'base de datos', 'logistica_master.duckdb')

@st.cache_data
def cargar_datos():
    con = duckdb.connect(database=ruta_db, read_only=True)
    df = con.execute("SELECT * FROM historico_entregas").df()
    con.close()
    df['Fecha'] = pd.to_datetime(df['Fecha']) 
    return df

try:
    df_crudo = cargar_datos()
    
    # ==========================================
    # EL CONTROL REMOTO (Filtros de Minería de Datos)
    # ==========================================
    # Título del panel lateral en 20px
    st.sidebar.markdown("<h3 style='font-size: 20px;'>Minería de Datos</h3>", unsafe_allow_html=True)
    st.sidebar.markdown("Filtros en cascada para desglose:")

    # Filtro de Fechas
    fecha_minima = df_crudo['Fecha'].min().date()
    fecha_maxima = df_crudo['Fecha'].max().date()

    rango_fechas = st.sidebar.date_input(
        "Rango de Fechas",
        value=(fecha_minima, fecha_maxima),
        min_value=fecha_minima,
        max_value=fecha_maxima
    )

    if len(rango_fechas) == 2:
        fecha_inicio, fecha_fin = rango_fechas
        mask = (df_crudo['Fecha'].dt.date >= fecha_inicio) & (df_crudo['Fecha'].dt.date <= fecha_fin)
        df_filtrado = df_crudo.loc[mask]
    else:
        df_filtrado = df_crudo 

    # Filtro de Vehículo
    rutas_disponibles = ["TODOS"] + sorted(df_filtrado['Ruta'].dropna().unique().tolist())
    ruta_seleccionada = st.sidebar.selectbox("Filtrar por Vehículo", rutas_disponibles)
    
    if ruta_seleccionada != "TODOS":
        df_filtrado = df_filtrado[df_filtrado['Ruta'] == ruta_seleccionada]

    # Filtro de Asesor
    asesores_disponibles = ["TODOS"] + sorted(df_filtrado['Asesor'].dropna().unique().tolist())
    asesor_seleccionado = st.sidebar.selectbox("Filtrar por Vendedor", asesores_disponibles)
    
    if asesor_seleccionado != "TODOS":
        df_filtrado = df_filtrado[df_filtrado['Asesor'] == asesor_seleccionado]


    # ==========================================
    # LA VITRINA (Dashboard Principal)
    # ==========================================
    # Título principal ajustado a 28px (puedes cambiar este número a tu gusto)
    st.markdown("<h1 style='font-size: 28px;'>Indicadores logísticos</h1>", unsafe_allow_html=True)
    st.markdown("---")

    # Cálculos KPI
    total_despachado = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado']['Valor_Total'].sum()
    total_devuelto = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion']['Valor_Total'].sum()
    porcentaje_devolucion = (total_devuelto / total_despachado) * 100 if total_despachado > 0 else 0
    
    # Tarjetas de Resumen
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Facturado / Despachado", f"${total_despachado:,.0f}")
    col2.metric("Total Devuelto", f"${total_devuelto:,.0f}")
    col3.metric("% de Devolución (Valor)", f"{porcentaje_devolucion:.2f}%")
    st.markdown("---")

    df_devoluciones = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion']

    # ==========================================
    # GRÁFICOS NIVEL 1: RESPONSABLES
    # ==========================================
    col_graf1, col_graf2 = st.columns(2)
    
    with col_graf1:
        resumen_rutas = df_devoluciones.groupby('Ruta')['Valor_Total'].sum().reset_index()
        resumen_rutas = resumen_rutas.sort_values(by='Valor_Total', ascending=True) 
        
        fig_rutas = px.bar(
            resumen_rutas, x='Valor_Total', y='Ruta', orientation='h',
            title="Impacto por Vehículo",
            labels={'Valor_Total': 'Dinero Devuelto ($)', 'Ruta': ''},
            text_auto='.3s'
        )
        # Centramos el título del gráfico y le damos tamaño 18px
        fig_rutas.update_layout(title_x=0.5, title_font_size=18, height=max(400, len(resumen_rutas)*30)) 
        st.plotly_chart(fig_rutas, use_container_width=True)
        
    with col_graf2:
        resumen_asesor = df_devoluciones.groupby('Asesor')['Valor_Total'].sum().reset_index()
        resumen_asesor = resumen_asesor.sort_values(by='Valor_Total', ascending=True)
        
        fig_asesor = px.bar(
            resumen_asesor, x='Valor_Total', y='Asesor', orientation='h',
            title="Impacto por Vendedor",
            labels={'Valor_Total': 'Dinero Devuelto ($)', 'Asesor': ''},
            text_auto='.3s',
            color_discrete_sequence=['#ff7f0e']
        )
        # Centramos el título del gráfico y le damos tamaño 18px
        fig_asesor.update_layout(title_x=0.5, title_font_size=18, height=max(400, len(resumen_asesor)*30))
        st.plotly_chart(fig_asesor, use_container_width=True)

 # ==========================================
    # GRÁFICO NIVEL 2: CAUSA RAÍZ
    # ==========================================
    st.markdown("---")
    st.markdown("<h2 style='font-size: 22px;'>Análisis de Causa Raíz: Motivos de Devolución</h2>", unsafe_allow_html=True)
    
    resumen_motivos = df_devoluciones.groupby('Motivo_Detalle')['Valor_Total'].sum().reset_index()
    resumen_motivos = resumen_motivos.sort_values(by='Valor_Total', ascending=False) 
    
    fig_motivos = px.bar(
        resumen_motivos, x='Motivo_Detalle', y='Valor_Total',
        title="Distribución Financiera por Motivo de Rechazo",
        labels={'Valor_Total': 'Dinero Devuelto ($)', 'Motivo_Detalle': 'Causal Operativa'},
        text_auto='.3s', color_discrete_sequence=['#d62728'] 
    )
    fig_motivos.update_layout(title_x=0.5, title_font_size=18)
    # Formateo profesional del globo interactivo con separadores de miles
    fig_motivos.update_traces(hovertemplate='Causal: %{x}<br>Dinero Devuelto: $%{y:,.0f}')
    st.plotly_chart(fig_motivos, use_container_width=True)

  # ==========================================
    # EL MAPA DE CALOR (Vehículo vs Motivo)
    # ==========================================
    st.markdown("<h2 style='font-size: 22px;'>Mapa de Calor: Correlación Vehículo vs. Motivo</h2>", unsafe_allow_html=True)
    
    heatmap_data = df_devoluciones.groupby(['Ruta', 'Motivo_Detalle'])['Valor_Total'].sum().reset_index()
    heatmap_pivot = heatmap_data.pivot(index='Ruta', columns='Motivo_Detalle', values='Valor_Total').fillna(0)

    fig_heat = px.imshow(
        heatmap_pivot,
        labels=dict(x="Causal Operativa", y="Vehículo / Ruta", color="Dinero"),
        x=heatmap_pivot.columns, y=heatmap_pivot.index,
        color_continuous_scale='Reds', aspect="auto", text_auto='.2s'
    )
    fig_heat.update_layout(title_x=0.5, title_font_size=18, height=450)
    fig_heat.update_traces(hovertemplate='Ruta: %{y}<br>Motivo: %{x}<br>Impacto: %{z:,.0f}')
    st.plotly_chart(fig_heat, use_container_width=True)

    # ==========================================
    # ANÁLISIS PROFUNDO: CLIENTES Y PRODUCTOS
    # ==========================================
    st.markdown("---")
    st.markdown("<h2 style='font-size: 22px;'>Análisis Específico: Clientes y Fricción de Inventario</h2>", unsafe_allow_html=True)
    
    col_cli, col_prod = st.columns(2)
    
    with col_cli:
        top_clientes = df_devoluciones.groupby('Cliente')['Valor_Total'].sum().reset_index()
        top_clientes = top_clientes.sort_values(by='Valor_Total', ascending=True).tail(10) 
        
        fig_cli = px.bar(
            top_clientes, x='Valor_Total', y='Cliente', orientation='h',
            title="Top 10 Clientes (Impacto Financiero)",
            labels={'Valor_Total': '', 'Cliente': ''},
            text_auto='.3s', color_discrete_sequence=['#8c564b']
        )
        fig_cli.update_layout(title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0))
        fig_cli.update_traces(hovertemplate='Cliente: %{y}<br>Dinero Devuelto: %{x:,.0f}')
        st.plotly_chart(fig_cli, use_container_width=True)

    with col_prod:
        top_productos = df_devoluciones.groupby('Producto').agg({'Cantidad': 'sum', 'Valor_Total': 'sum'}).reset_index()
        # Ordenamos de menor a mayor para que en el gráfico de barras horizontales el mayor quede arriba
        top_productos = top_productos.sort_values(by='Cantidad', ascending=True).tail(10)
        
        fig_prod = px.bar(
            top_productos, x='Cantidad', y='Producto', orientation='h',
            title="Top 10 Productos (Fricción Logística - Unidades)",
            labels={'Cantidad': '', 'Producto': ''},
            text_auto='.0f', color_discrete_sequence=['#17becf'],
            hover_data={'Valor_Total': True} 
        )
        fig_prod.update_layout(title_x=0.5, title_font_size=16, height=350, margin=dict(l=0, r=0, t=40, b=0))
        fig_prod.update_traces(hovertemplate='Producto: %{y}<br>Unidades devueltas: %{x:,.0f}<br>Costo de las unidades: %{customdata[0]:,.0f}')
        st.plotly_chart(fig_prod, use_container_width=True)

    # ==========================================
    # ÍNDICE DE EFICIENCIA RELATIVA
    # ==========================================
    st.markdown("---")
    st.markdown("<h2 style='font-size: 22px;'>Índice de Eficiencia: Tasa de Devolución Relativa</h2>", unsafe_allow_html=True)
    st.markdown("Mide el % de devolución frente al volumen real despachado (Rendimiento Operativo real).")
    
    col_eff1, col_eff2 = st.columns(2)
    
    def calcular_eficiencia(columna_agrupacion):
        despacho = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Despachado'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Despachado')
        devolucion = df_filtrado[df_filtrado['Estatus_Operacion'] == 'Devolucion'].groupby(columna_agrupacion)['Valor_Total'].sum().reset_index(name='Devuelto')
        eficiencia = pd.merge(despacho, devolucion, on=columna_agrupacion, how='left').fillna(0)
        eficiencia['% Devolución'] = (eficiencia['Devuelto'] / eficiencia['Despachado']) * 100
        # Mantenemos los datos como números puros y ordenamos de mayor ineficiencia a menor
        return eficiencia.sort_values(by='% Devolución', ascending=False)

    df_eff_ruta = calcular_eficiencia('Ruta')
    df_eff_asesor = calcular_eficiencia('Asesor')
    
    # Configuramos el motor visual de Streamlit para aplicar formato sin alterar el tipo de dato
    columnas_formateadas = {
        "Despachado": st.column_config.NumberColumn("Despachado", format="%,.0f"),
        "Devuelto": st.column_config.NumberColumn("Devuelto", format="%,.0f"),
        "% Devolución": st.column_config.ProgressColumn(
            "% Devolución", format="%.2f%%", min_value=0, max_value=100
        )
    }

    with col_eff1:
        st.markdown("**Eficiencia por Vehículo (Ruta)**")
        st.dataframe(df_eff_ruta, column_config=columnas_formateadas, hide_index=True, use_container_width=True)

    with col_eff2:
        st.markdown("**Eficiencia por Vendedor (Asesor)**")
        st.dataframe(df_eff_asesor, column_config=columnas_formateadas, hide_index=True, use_container_width=True)

    # ==========================================
    # AUDITORÍA PROFUNDA
    # ==========================================
    st.markdown("---")
    st.markdown("<h2 style='font-size: 22px;'>Auditoría de Facturas (Drill-Down)</h2>", unsafe_allow_html=True)
    st.markdown("Detalle línea a línea de las operaciones devueltas (Aplica filtros laterales para aislar la búsqueda).")
    
    # Ordenamos y aplicamos el mismo principio visual al Drill-Down
    df_auditoria = df_devoluciones.sort_values(by='Valor_Total', ascending=False)
    
    columnas_auditoria = {
        "Valor_Total": st.column_config.NumberColumn("Valor_Total", format="%,.0f"),
        "Cantidad": st.column_config.NumberColumn("Cantidad", format="%,.0f")
    }
    
    st.dataframe(df_auditoria, column_config=columnas_auditoria, hide_index=True, use_container_width=True)



except Exception as e:
    st.error(f"Error al cargar el dashboard: {e}")