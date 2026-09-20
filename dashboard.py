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
    # Subtítulo en 22px
    st.markdown("<h2 style='font-size: 22px;'>Análisis de Causa Raíz: Motivos de Devolución</h2>", unsafe_allow_html=True)
    
    resumen_motivos = df_devoluciones.groupby('Motivo_Detalle')['Valor_Total'].sum().reset_index()
    resumen_motivos = resumen_motivos.sort_values(by='Valor_Total', ascending=False) 
    
    fig_motivos = px.bar(
        resumen_motivos, x='Motivo_Detalle', y='Valor_Total',
        title="Distribución Financiera por Motivo de Rechazo",
        labels={'Valor_Total': 'Dinero Devuelto ($)', 'Motivo_Detalle': 'Causal Operativa'},
        text_auto='.3s',
        color_discrete_sequence=['#d62728'] 
    )
    # Centramos el título del gráfico y le damos tamaño 18px
    fig_motivos.update_layout(title_x=0.5, title_font_size=18)
    st.plotly_chart(fig_motivos, use_container_width=True)

    # ==========================================
    # AUDITORÍA PROFUNDA
    # ==========================================
    st.markdown("---")
    # Subtítulo en 22px
    st.markdown("<h2 style='font-size: 22px;'>Detalle de Facturas</h2>", unsafe_allow_html=True)
    st.dataframe(df_filtrado.sort_values(by='Valor_Total', ascending=False))

except Exception as e:
    st.error(f"Error al cargar el dashboard: {e}")