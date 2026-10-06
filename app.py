import streamlit as st
import pandas as pd
from dateutil.relativedelta import relativedelta
from datetime import datetime
import math
import os

# Diccionario para forzar los meses en español
MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def load_data():
    conn = st.connection("postgresql", type="sql")
    try:
        # Lee la tabla desde Supabase (ttl=0 para desactivar caché y ver reflejados los cambios al instante)
        df = conn.query("SELECT * FROM mis_cuotas", ttl=0)
        return df
    except Exception:
        # Si falla (ej. tabla no creada aún en la base de datos), devolvemos el DataFrame vacío
        return pd.DataFrame(columns=['Compra_ID', 'Monto_Total', 'N_Cuotas', 'Fecha_Inicio'])

def save_data(df):
    conn = st.connection("postgresql", type="sql")
    # Actualiza la tabla entera en Supabase
    df.to_sql("mis_cuotas", con=conn.engine, if_exists="replace", index=False)

st.set_page_config(page_title="Mis Cuotas", page_icon="📊", layout="centered")
st.title("📊 Rastreador de Compras por Cuotas")

df = load_data()

# ---------------------------------------------------------
# MOTOR DE CÁLCULO (Movido para Métricas)
# ---------------------------------------------------------
resumen_mensual = pd.DataFrame()
df_proy = pd.DataFrame()

if not df.empty:
    proyeccion = []
    # Desglosar compras
    for index, row in df.iterrows():
        # Redondeamos hacia arriba usando math.ceil
        valor_cuota = math.ceil(row['Monto_Total'] / row['N_Cuotas'])
        # Validar formato de fecha por si se guarda con formato timestamp extra
        fecha_str = str(row['Fecha_Inicio']).split(' ')[0]
        fecha_actual = datetime.strptime(fecha_str[:10], '%Y-%m-%d')
        
        for i in range(int(row['N_Cuotas'])):
            mes_num = fecha_actual.month
            proyeccion.append({
                'Mes_ID': fecha_actual.strftime('%Y-%m'), 
                'Nombre_Mes': f"{MESES_ES[mes_num]} {fecha_actual.year}",
                'Compra_ID': row['Compra_ID'],
                'Monto': valor_cuota
            })
            fecha_actual += relativedelta(months=1)
            
    if proyeccion:
        df_proy = pd.DataFrame(proyeccion)
        # Agrupar por mes
        resumen_mensual = df_proy.groupby('Mes_ID').apply(
            lambda x: pd.Series({
                'Nombre_Mes': x['Nombre_Mes'].iloc[0],
                'Formula': ' + '.join(x['Compra_ID']),
                'Total_a_Pagar': x['Monto'].sum()
            })
        ).reset_index()

# ---------------------------------------------------------
# MÉTRICAS PRINCIPALES
# ---------------------------------------------------------
if not resumen_mensual.empty:
    mes_actual_str = datetime.now().strftime('%Y-%m')
    df_pendientes = resumen_mensual[resumen_mensual['Mes_ID'] >= mes_actual_str]
    
    deuda_total_pendiente = df_pendientes['Total_a_Pagar'].sum() if not df_pendientes.empty else 0
    
    # Obtener el pago del mes actual específicamente
    pago_mes_actual = 0
    mes_actual_row = df_pendientes[df_pendientes['Mes_ID'] == mes_actual_str]
    if not mes_actual_row.empty:
        pago_mes_actual = mes_actual_row['Total_a_Pagar'].iloc[0]
        
    # Calcular mes libre de deudas
    if not df_pendientes.empty:
        ultimo_mes_id = df_pendientes['Mes_ID'].iloc[-1]
        ultimo_mes_fecha = datetime.strptime(ultimo_mes_id, '%Y-%m')
        mes_libre_fecha = ultimo_mes_fecha + relativedelta(months=1)
        mes_libre = f"{MESES_ES[mes_libre_fecha.month]} {mes_libre_fecha.year}"
    else:
        mes_libre = "¡Este mes!"

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Deuda Pendiente", f"${int(deuda_total_pendiente):,}".replace(",", "."))
    col2.metric("📅 A Pagar este Mes", f"${int(pago_mes_actual):,}".replace(",", "."))
    col3.metric("🎉 Mes Libre de Deudas", mes_libre)
    st.divider()

# ---------------------------------------------------------
# PANEL DE ADMINISTRACIÓN Y CARGA
# ---------------------------------------------------------
with st.expander("🗑️ Administrar / Eliminar Compras"):
    if not df.empty:
        opciones = df['Compra_ID'].unique().tolist()
        compra_a_eliminar = st.selectbox("Selecciona la compra que deseas eliminar:", opciones)
        
        if st.button("Eliminar Seleccionada", type="primary"):
            df = df[df['Compra_ID'] != compra_a_eliminar]
            save_data(df)
            st.success(f"La compra '{compra_a_eliminar}' fue eliminada con éxito.")
            st.rerun()
    else:
        st.info("No hay compras registradas para eliminar.")

st.subheader("➕ Agregar Nuevas Compras")
tab1, tab2 = st.tabs(["🛒 Nueva Compra en Cuotas", "📌 Cargar Deuda Actual (Un mes)"])

with tab1:
    with st.form("nueva_compra"):
        st.write("Agrega una compra que se dividirá en varios meses:")
        col1, col2 = st.columns(2)
        compra_id = col1.text_input("Identificador (Ej: T, S, Zapatillas)")
        monto = col2.number_input("Monto Total", min_value=0.0, step=1000.0)
        cuotas = col1.number_input("Cantidad de Cuotas", min_value=1, step=1, value=3)
        fecha_inicio = col2.date_input("Fecha de Primera Cuota")
        
        submit1 = st.form_submit_button("Guardar Compra")
        
        if submit1 and compra_id:
            nueva_fila = pd.DataFrame({
                'Compra_ID': [compra_id],
                'Monto_Total': [monto],
                'N_Cuotas': [cuotas],
                'Fecha_Inicio': [fecha_inicio.strftime('%Y-%m-01')]
            })
            df = pd.concat([df, nueva_fila], ignore_index=True)
            save_data(df)
            st.success("¡Compra guardada!")
            st.rerun()

with tab2:
    with st.form("deuda_actual"):
        st.write("Ideal para saldos previos (Ej: 'Deuda Octubre', 1 cuota, Monto exacto):")
        col1, col2 = st.columns(2)
        deuda_id = col1.text_input("Identificador (Ej: Deuda Octubre)")
        monto_unico = col2.number_input("Monto a Pagar", min_value=0.0, step=1000.0)
        fecha_unica = col1.date_input("Mes de Cobro")
        
        submit2 = st.form_submit_button("Guardar Deuda Única")
        
        if submit2 and deuda_id:
            nueva_fila = pd.DataFrame({
                'Compra_ID': [deuda_id],
                'Monto_Total': [monto_unico],
                'N_Cuotas': [1],
                'Fecha_Inicio': [fecha_unica.strftime('%Y-%m-01')]
            })
            df = pd.concat([df, nueva_fila], ignore_index=True)
            save_data(df)
            st.success("¡Deuda registrada!")
            st.rerun()

st.divider()

# ---------------------------------------------------------
# VISUALIZACIÓN Y DETALLE
# ---------------------------------------------------------
if not resumen_mensual.empty:
    st.subheader("📈 Evolución de Deudas")
    
    # Preparar datos para el gráfico
    chart_data = resumen_mensual[['Mes_ID', 'Total_a_Pagar']].set_index('Mes_ID')
    st.bar_chart(chart_data, color="#ff4b4b")
    
    col_lista, col_copiar = st.columns([2, 1])
    
    with col_lista:
        st.subheader("🗓️ Detalle Mensual")
        for index, row in resumen_mensual.iterrows():
            texto_detalle = f"**{row['Nombre_Mes']}:** {row['Formula']} *(Total: ${int(row['Total_a_Pagar']):,})*"
            st.markdown(texto_detalle.replace(",", "."))
            
    with col_copiar:
        st.subheader("📋 Pendientes")
        st.write("Haz clic en el ícono de la esquina de la caja para copiar:")
        
        mes_actual_str = datetime.now().strftime('%Y-%m')
        df_pendientes = resumen_mensual[resumen_mensual['Mes_ID'] >= mes_actual_str]
        
        texto_copiar = ""
        for idx, row in df_pendientes.iterrows():
            monto_str = f"${int(row['Total_a_Pagar']):,}".replace(",", ".")
            texto_copiar += f"{row['Nombre_Mes']}: {monto_str}\n"
        
        st.code(texto_copiar, language="text")

else:
    st.info("No hay compras registradas. Agrega una arriba para comenzar.")