import duckdb
import pandas as pd
import glob
import os

print("Iniciando motor SQL Analítico...")

# ==========================================
# 1. RUTAS DINÁMICAS
# ==========================================
directorio_actual = os.path.dirname(os.path.abspath(__file__))
ruta_csvs = os.path.join(directorio_actual, 'csv mensuales', '*.csv')
ruta_db = os.path.join(directorio_actual, 'base de datos', 'logistica_master.duckdb')

con = duckdb.connect(database=ruta_db)

# ==========================================
# 2. LECTURA Y TRADUCCIÓN (Con Pandas)
# ==========================================
archivos = glob.glob(ruta_csvs)
lista_dfs = []

for archivo in archivos:
    tipos_de_datos = {
        'nbPlanilla': str,
        'nbFactura': str,
        'idPuntoVenta': str,
        'nbProducto': str,
        'motivo': str,
        'estadoPlanilla': str  # <-- NUEVO: Captura del estado para Cartera
    }
    
    df = pd.read_csv(
        archivo, 
        sep='|', 
        encoding='latin-1', 
        decimal='.',
        thousands=',',
        low_memory=False,
        dtype=tipos_de_datos
    )
    lista_dfs.append(df)

if not lista_dfs:
    print("No se encontraron archivos en la carpeta 'csv mensuales'.")
else:
    df_erp = pd.concat(lista_dfs, ignore_index=True)
    
    # ==========================================
    # BLINDAJE ANTIDUPLICADOS EN MEMORIA (NUEVO)
    # ==========================================
    # 1. Ordenamos para que el estado 'C' (Cerrado) quede por encima del 'P' (Provisional)
    df_erp = df_erp.sort_values(by=['estadoPlanilla'], ascending=True)
    
    # 2. Eliminamos las filas duplicadas, conservando la primera que encuentre (la 'C')
    # La llave lógica que define un registro único es: Planilla + Factura + Producto + Cantidad
    # (La cantidad se incluye porque un despacho [1] y una devolución [-1] del mismo producto son eventos distintos)
    df_erp = df_erp.drop_duplicates(subset=['nbPlanilla', 'nbFactura', 'nbProducto', 'cantAsignada'], keep='first')
    
    # ==========================================
    # 3. PROCESAMIENTO SQL E INSERCIÓN QUIRÚRGICA
    # ==========================================
    query_transformacion = """
    SELECT 
        dtEntrega AS Fecha,
        nbPlanilla AS Planilla,
        nbFactura AS Factura,
        nbRuta AS Ruta,
        nmZona AS Asesor,
        idPuntoVenta AS Codigo_Cliente,
        nmPuntoVenta AS Cliente,
        nbProducto AS Codigo_Producto,
        nmProducto AS Producto,
        estadoPlanilla AS Estado_Planilla, -- <-- NUEVO: Proyección a la base maestra
        COALESCE(motivo, 'ENTREGA INICIAL') AS Motivo_Detalle,
        CASE 
            WHEN CAST(cantAsignada AS DOUBLE) >= 0 THEN 'Despachado' 
            ELSE 'Devolucion' 
        END AS Estatus_Operacion,
        ABS(CAST(cantAsignada AS DOUBLE)) AS Cantidad,
        ABS(CAST(vlrTotalconIva AS DOUBLE)) AS Valor_Total
    FROM df_erp
    """
    
    try:
        print("Analizando los datos nuevos frente a la base histórica...")
        
        tablas = con.execute("SHOW TABLES").df()
        
        if 'historico_entregas' not in tablas['name'].values:
            print("Creando la Base de Datos maestra por primera vez...")
            con.execute(f"CREATE TABLE historico_entregas AS {query_transformacion}")
            conteo_final = con.execute("SELECT COUNT(*) FROM historico_entregas").fetchone()[0]
            print(f"✅ ¡Éxito! Base creada con {conteo_final:,} filas.")
        else:
            print("Bóveda de datos detectada. Sincronizando registros mutables...")
            
            conteo_antes = con.execute("SELECT COUNT(*) FROM historico_entregas").fetchone()[0]
            
            con.execute(f"CREATE TEMP TABLE temp_nuevos AS {query_transformacion}")
            
            query_delete = """
            DELETE FROM historico_entregas 
            WHERE Planilla IN (SELECT DISTINCT Planilla FROM temp_nuevos)
            """
            con.execute(query_delete)
            
            query_insert = """
            INSERT INTO historico_entregas 
            SELECT * FROM temp_nuevos
            """
            con.execute(query_insert)
            
            con.execute("DROP TABLE temp_nuevos")
            
            conteo_despues = con.execute("SELECT COUNT(*) FROM historico_entregas").fetchone()[0]
            
            print(f"✅ SINCRONIZACIÓN EXITOSA: Base de datos sobreescrita con los cierres definitivos.")
            print(f"Filas procesadas antes: {conteo_antes:,} | Filas consolidadas ahora: {conteo_despues:,}")
        
    except Exception as e:
        print(f"❌ Error al procesar el SQL: {e}")
    finally:
        con.close()
        print("-" * 50)
        print("Proceso finalizado.")