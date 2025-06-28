# app.py - BIOETHICARE 360 - Versión Profesional Definitiva
# Autores: Anderson Díaz Pérez & Joseph Javier Sánchez Acuña
# VERSIÓN CONSOLIDADA CON UI PROFESIONAL, ANÁLISIS MULTIPERSPECTIVA Y MEJORAS INTEGRADAS

# --- 1. Importaciones ---
import os
import json
import requests
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import tempfile # Para manejo de archivos temporales
import shutil   # Para eliminar directorios temporales

# Importaciones para PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import inch
from reportlab.lib import colors

# Importaciones para Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# --- 2. Configuración Inicial y Estado de la Sesión ---
st.set_page_config(layout="wide", page_title="BIOETHICARE 360")

# Inicialización del estado para todo el ciclo de vida de la app
if 'reporte' not in st.session_state:
    st.session_state.reporte = None
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = None
if 'case_id' not in st.session_state:
    st.session_state.case_id = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'last_question' not in st.session_state:
    st.session_state.last_question = ""
if 'dilema_sugerido' not in st.session_state:
    st.session_state.dilema_sugerido = None

# --- 3. Conexión con Firebase ---
@st.cache_resource
def initialize_firebase():
    """Inicializa la conexión con Firebase de forma segura."""
    try:
        if "firebase_credentials" in st.secrets:
            creds_dict = dict(st.secrets["firebase_credentials"])
            cred = credentials.Certificate(creds_dict)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            st.success("🔌 Conexión con Firebase establecida.", icon="🔌")
            return firestore.client()
        else:
            st.warning("⚠️ Credenciales de Firebase no encontradas.", icon="⚠️")
            return None
    except Exception as e:
        st.error(f"❌ Error al conectar con Firebase: {e}", icon="❌")
        return None

db = initialize_firebase()

# --- 4. Base de Conocimiento (LISTA DE DILEMAS FINAL) ---
dilemas_opciones = {
    "Dilemas Éticos en Neonatología": {},
    "Limitación del Esfuerzo Terapéutico (Adultos/Pediatría)": {},
    "Consentimiento Informado": {},
    "Confidencialidad y Manejo de Datos": {},
    "Cuidados Paliativos y Futilidad": {},
    "Eutanasia y Muerte Digna": {},
    "Asignación de Recursos Escasos": {},
    "Ética en la Genética y Medicina Predictiva": {},
    "Conflictos de Interés": {},
}


# --- 5. Lógica de Negocio y Reportes ---
def safe_int(value, default=0):
    if value is None or value == '': return default
    try: return int(value)
    except (ValueError, TypeError): return default

class CasoBioetico:
    """Modela los datos del caso con la estructura multiperspectiva."""
    def __init__(self, **kwargs):
        self.nombre_paciente = kwargs.get('nombre_paciente', 'N/A')
        self.historia_clinica = kwargs.get('historia_clinica') or f"caso_{int(datetime.now().timestamp())}"
        self.edad = safe_int(kwargs.get('edad'), 0)
        self.genero = kwargs.get('genero', 'N/A')
        self.nombre_analista = kwargs.get('nombre_analista', 'N/A')
        self.dilema_etico = kwargs.get('dilema_etico', list(dilemas_opciones.keys())[0])
        self.descripcion_caso = kwargs.get('descripcion_caso', '')
        self.antecedentes_culturales = kwargs.get('antecedentes_culturales', '')
        self.condicion = kwargs.get('condicion', 'Estable')
        self.semanas_gestacion = safe_int(kwargs.get('semanas_gestacion'), 0)
        self.puntos_clave_ia = kwargs.get('puntos_clave_ia', '')
        self.perspectivas = {
            "medico": self._extract_perspective("medico", kwargs),
            "familia": self._extract_perspective("familia", kwargs),
            "comite": self._extract_perspective("comite", kwargs),
        }

    def _extract_perspective(self, prefix, kwargs):
        return {
            "autonomia": safe_int(kwargs.get(f'nivel_autonomia_{prefix}')),
            "beneficencia": safe_int(kwargs.get(f'nivel_beneficencia_{prefix}')),
            "no_maleficencia": safe_int(kwargs.get(f'nivel_no_maleficencia_{prefix}')),
            "justicia": safe_int(kwargs.get(f'nivel_justicia_{prefix}')),
        }

def generar_reporte_completo(caso, dilema_sugerido, chat_history):
    """Genera el diccionario del reporte con la nueva estructura."""
    resumen_paciente = f"Paciente {caso.nombre_paciente}, {caso.edad} años, género {caso.genero}, condición {caso.condicion}."
    if caso.semanas_gestacion > 0: resumen_paciente += f" Neonato de {caso.semanas_gestacion} sem."
    return {
        "ID del Caso": caso.historia_clinica, "Fecha Análisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Analista": caso.nombre_analista, "Resumen del Paciente": resumen_paciente,
        "Dilema Ético Principal (Seleccionado)": caso.dilema_etico,
        "Dilema Sugerido por IA": dilema_sugerido,
        "Descripción Detallada del Caso": caso.descripcion_caso,
        "Contexto Sociocultural y Familiar": caso.antecedentes_culturales,
        "Puntos Clave para Deliberación IA": caso.puntos_clave_ia,
        "AnalisisMultiperspectiva": {
            "Equipo Médico": caso.perspectivas["medico"],
            "Familia/Paciente": caso.perspectivas["familia"],
            "Comité de Bioética": caso.perspectivas["comite"],
        },
        "Análisis Deliberativo (IA)": "",
        "Historial del Chat de Deliberación": chat_history,
    }

def generar_visualizaciones_avanzadas(caso, temp_dir):
    """Genera los gráficos y los guarda en un directorio temporal."""
    perspectivas_data = caso.perspectivas
    labels = ["Autonomía", "Beneficencia", "No Maleficencia", "Justicia"]
    
    # Gráfico de Radar Comparativo
    fig_radar = go.Figure()
    colors_map = {'medico': 'rgba(239, 68, 68, 0.7)', 'familia': 'rgba(59, 130, 246, 0.7)', 'comite': 'rgba(34, 197, 94, 0.7)'}
    nombres = {'medico': 'Equipo Médico', 'familia': 'Familia/Paciente', 'comite': 'Comité de Bioética'}
    for key, data in perspectivas_data.items():
        fig_radar.add_trace(go.Scatterpolar(r=list(data.values()), theta=labels, fill='toself', name=nombres[key], line_color=colors_map[key]))
    fig_radar.update_layout(title="Ponderación de Principios por Perspectiva", polar=dict(radialaxis=dict(visible=True, range=[0, 5])), showlegend=True, font_size=14)
    radar_path = os.path.join(temp_dir, "radar_comparativo.png")
    fig_radar.write_image(radar_path)
    
    # Gráfico de Consenso y Disenso
    scores = np.array([list(d.values()) for d in perspectivas_data.values()])
    fig_stats = go.Figure()
    fig_stats.add_trace(go.Bar(x=labels, y=np.mean(scores, axis=0), error_y=dict(type='data', array=np.std(scores, axis=0), visible=True), marker_color='#636EFA'))
    fig_stats.update_layout(title="Análisis de Consenso y Disenso", yaxis=dict(range=[0, 6]), font_size=14)
    stats_path = os.path.join(temp_dir, "estadisticas.png")
    fig_stats.write_image(stats_path)
    
    return {'radar_comparativo': radar_path, 'estadisticas': stats_path}

def crear_reporte_pdf_completo(data, temp_dir, filename):
    """Genera el reporte PDF usando los archivos del directorio temporal."""
    doc = SimpleDocTemplate(filename, pagesize=letter, topMargin=inch/2, bottomMargin=inch/2)
    styles = getSampleStyleSheet()
    story = []
    
    h1 = ParagraphStyle(name='H1', fontSize=18, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=20)
    h2 = ParagraphStyle(name='H2', fontSize=14, fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=6, textColor=colors.darkblue)
    body = ParagraphStyle(name='Body', fontSize=10, fontName='Helvetica', leading=14, alignment=TA_JUSTIFY, spaceAfter=10)
    chat_style = ParagraphStyle(name='Chat', fontSize=9, fontName='Helvetica-Oblique', backColor=colors.whitesmoke, borderWidth=1, padding=5)

    story.append(Paragraph("Reporte Deliberativo - BIOETHICARE 360", h1))
    
    order = ["ID del Caso", "Fecha Análisis", "Analista", "Resumen del Paciente", "Dilema Ético Principal (Seleccionado)", "Dilema Sugerido por IA", "Descripción Detallada del Caso", "Contexto Sociocultural y Familiar", "Puntos Clave para Deliberación IA"]
    for key in order:
        if key in data and data[key]:
            story.append(Paragraph(key, h2))
            story.append(Paragraph(str(data[key]).replace('\n', '<br/>'), body))

    if "AnalisisMultiperspectiva" in data:
        story.append(Paragraph("Análisis Multiperspectiva", h2))
        for nombre, valores in data["AnalisisMultiperspectiva"].items():
            texto = f"<b>{nombre}:</b> Autonomía: {valores['autonomia']}, Beneficencia: {valores['beneficencia']}, No Maleficencia: {valores['no_maleficencia']}, Justicia: {valores['justicia']}"
            story.append(Paragraph(texto, body))
    
    if data.get("Análisis Deliberativo (IA)"):
        story.append(Paragraph("Análisis Deliberativo (IA)", h2))
        story.append(Paragraph(data["Análisis Deliberativo (IA)"].replace('\n', '<br/>'), body))

    # Añadir gráficos desde el directorio temporal
    if temp_dir and os.path.exists(temp_dir):
        story.append(PageBreak())
        story.append(Paragraph("Visualizaciones de Datos", h1))
        image_paths = [os.path.join(temp_dir, f) for f in sorted(os.listdir(temp_dir)) if f.endswith('.png')]
        for img_path in image_paths:
            if os.path.exists(img_path):
                story.append(Image(img_path, width=7*inch, height=4.5*inch, hAlign='CENTER'))
                story.append(Spacer(1, 0.5*inch))
            
    if data.get("Historial del Chat de Deliberación"):
        story.append(PageBreak())
        story.append(Paragraph("Historial del Chat de Deliberación", h1))
        for msg in data["Historial del Chat de Deliberación"]:
            role_text = f"<b>{'Usuario' if msg['role'] == 'user' else 'Asistente IA'}:</b> {msg['content']}"
            story.append(Paragraph(role_text, chat_style))

    doc.build(story)

# --- 6. Función para llamar a Gemini API ---
def llamar_gemini(prompt, api_key):
    """Realiza la llamada a la API de Gemini con manejo de errores mejorado."""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        result = response.json()
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text']
        st.warning(f"Respuesta inesperada de la API: {result}")
        return "No se pudo obtener una respuesta válida."
    except requests.exceptions.RequestException as e:
        st.error(f"Error de conexión con la API de Gemini: {e}")
        return "Error de conexión."

# --- 7. Interfaz de Usuario ---
st.title("BIOETHICARE 360 🏥")
with st.expander("Autores"):
    st.markdown("""
    - **Joseph Javier Sánchez Acuña**: Ingeniero Industrial, Experto en IA y tecnologías de vanguardia.
    - **Anderson Díaz Pérez**: Doctor en Bioética, Doctor en Salud Pública, Magíster en Ciencias Básicas Biomédicas (Énfasis en Inmunología), Especialista en Inteligencia Artificial.
    """)
st.markdown("---")

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.warning("⚠️ Clave de API de Gemini no encontrada. Funciones de IA deshabilitadas.", icon="⚠️")

tab_analisis, tab_chatbot, tab_consultar = st.tabs(["**Análisis de Caso**", "**Asistente de Bioética (Chatbot)**", "**Consultar Casos Anteriores**"])

def display_case_details(report_data, temp_dir=None, container=st):
    """Muestra el dashboard del caso con la UI avanzada."""
    with container.container(border=True):
        case_id = report_data.get('ID del Caso', 'N/A')
        st.subheader(f"Dashboard del Caso: `{case_id}`", anchor=False)
        st.markdown("---")
        
        # Mostrar gráficos si el directorio temporal existe
        if temp_dir and os.path.exists(temp_dir):
            st.markdown("##### Análisis Gráfico Avanzado")
            c1, c2 = st.columns(2)
            radar_path = os.path.join(temp_dir, 'radar_comparativo.png')
            stats_path = os.path.join(temp_dir, 'estadisticas.png')
            if os.path.exists(radar_path): c1.image(radar_path, caption="Gráfico Comparativo de Perspectivas")
            if os.path.exists(stats_path): c2.image(stats_path, caption="Análisis de Consenso vs. Disenso")
            st.markdown("---")

        if report_data.get("Análisis Deliberativo (IA)"):
            st.markdown("##### Análisis Deliberativo por IA")
            st.info(report_data["Análisis Deliberativo (IA)"])
            st.markdown("---")

        st.markdown("##### Resumen y Contexto del Caso")
        col_a, col_b = st.columns(2)
        col_a.markdown(f"**Paciente:** {report_data.get('Resumen del Paciente', 'N/A')}")
        col_a.markdown(f"**Analista:** {report_data.get('Analista', 'N/A')}")
        col_b.markdown(f"**Dilema Seleccionado:** {report_data.get('Dilema Ético Principal (Seleccionado)', 'N/A')}")
        if report_data.get("Dilema Sugerido por IA"):
            col_b.markdown(f"**Dilema Sugerido por IA:** {report_data.get('Dilema Sugerido por IA')}")
        
        with st.expander("Ver Detalles Completos, Ponderación y Chat"):
            st.text_area("Descripción:", value=report_data.get('Descripción Detallada del Caso',''), height=150, disabled=True, key=f"desc_{case_id}")
            st.text_area("Contexto Sociocultural:", value=report_data.get('Contexto Sociocultural y Familiar',''), height=100, disabled=True, key=f"context_{case_id}")
            
            st.markdown("**Ponderación por Perspectiva**")
            for nombre, valores in report_data.get("AnalisisMultiperspectiva", {}).items():
                st.markdown(f"**{nombre}**")
                p_cols = st.columns(4)
                p_cols[0].metric("Autonomía", f"{valores.get('autonomia', 0)}/5")
                p_cols[1].metric("Beneficencia", f"{valores.get('beneficencia', 0)}/5")
                p_cols[2].metric("No Maleficencia", f"{valores.get('no_maleficencia', 0)}/5")
                p_cols[3].metric("Justicia", f"{valores.get('justicia', 0)}/5")
            
            st.markdown("**Historial del Chat**")
            chat_history = report_data.get("Historial del Chat de Deliberación", [])
            if not chat_history:
                st.write("No hay historial de chat para este caso.")
            for msg in chat_history:
                with st.chat_message(msg['role']): st.markdown(msg['content'])

def cleanup_temp_dir():
    """Elimina el directorio temporal de la sesión si existe."""
    if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
    st.session_state.temp_dir = None


with tab_analisis:
    st.header("1. Registro y Contexto del Caso", anchor=False)
    with st.form("caso_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Identificación", anchor=False)
            nombre_paciente = st.text_input("Nombre del Paciente")
            edad = st.number_input("Edad (años)", 0, 120)
            genero = st.selectbox("Género", ["Masculino", "Femenino", "Otro"])
            semanas_gestacion = st.number_input("Semanas Gestación (si aplica)", 0, 42)
        with col2:
            st.subheader("Datos Administrativos", anchor=False)
            historia_clinica = st.text_input("Nº Historia Clínica / ID del Caso")
            nombre_analista = st.text_input("Nombre del Analista")
            condicion = st.selectbox("Condición", ["Estable", "Crítico", "Terminal", "Neonato"])

        st.subheader("Contexto Clínico y Ético", anchor=False)
        dilema_etico = st.selectbox("Dilema Ético Principal", options=list(dilemas_opciones.keys()))
        descripcion_caso = st.text_area("Descripción Detallada del Caso", height=150)
        
        # El botón de sugerencia ahora es un botón normal, no de formulario
        if st.form_submit_button("Sugerir Dilema con IA", use_container_width=True):
            if descripcion_caso and GEMINI_API_KEY:
                with st.spinner("Consultando a Gemini para sugerencia..."):
                    prompt = f"De estos dilemas: {', '.join(dilemas_opciones.keys())}. ¿Cuál es el más prominente en este caso? '{descripcion_caso}'. Responde solo el nombre del dilema."
                    sugerencia = llamar_gemini(prompt, GEMINI_API_KEY)
                    st.session_state.dilema_sugerido = sugerencia.strip()
            elif not GEMINI_API_KEY: st.error("La clave de API de Gemini es necesaria.")
            else: st.warning("Ingrese una descripción del caso.")

        if st.session_state.dilema_sugerido:
             st.success(f"Dilema Sugerido por IA: **{st.session_state.dilema_sugerido}**")

        antecedentes_culturales = st.text_area("Contexto Sociocultural y Familiar", height=100)
        puntos_clave_ia = st.text_area("Puntos Clave para Deliberación IA (Opcional)", height=100, help="Guíe a la IA con los conflictos o preguntas principales.")
        
        st.header("2. Ponderación Multiperspectiva (0-5)", anchor=False)
        with st.expander("Perspectiva del Equipo Médico"):
            c = st.columns(4); nivel_autonomia_medico = c[0].slider("Autonomía",0,5,3,key="am"); nivel_beneficencia_medico = c[1].slider("Beneficencia",0,5,3,key="bm"); nivel_no_maleficencia_medico = c[2].slider("No Maleficencia",0,5,3,key="nmm"); nivel_justicia_medico = c[3].slider("Justicia",0,5,3,key="jm")
        with st.expander("Perspectiva de la Familia / Paciente"):
            c = st.columns(4); nivel_autonomia_familia = c[0].slider("Autonomía",0,5,3,key="af"); nivel_beneficencia_familia = c[1].slider("Beneficencia",0,5,3,key="bf"); nivel_no_maleficencia_familia = c[2].slider("No Maleficencia",0,5,3,key="nmf"); nivel_justicia_familia = c[3].slider("Justicia",0,5,3,key="jf")
        with st.expander("Perspectiva del Comité de Bioética"):
            c = st.columns(4); nivel_autonomia_comite = c[0].slider("Autonomía",0,5,3,key="ac"); nivel_beneficencia_comite = c[1].slider("Beneficencia",0,5,3,key="bc"); nivel_no_maleficencia_comite = c[2].slider("No Maleficencia",0,5,3,key="nmc"); nivel_justicia_comite = c[3].slider("Justicia",0,5,3,key="jc")

        submitted = st.form_submit_button("Analizar Caso y Generar Dashboard", use_container_width=True)

    if submitted:
        if not historia_clinica:
            st.error("El campo 'Nº Historia Clínica / ID del Caso' es obligatorio.")
        else:
            with st.spinner("Procesando y generando reporte..."):
                cleanup_temp_dir()
                form_data = locals()
                caso = CasoBioetico(**form_data)
                temp_dir = tempfile.mkdtemp()
                generar_visualizaciones_avanzadas(caso, temp_dir)
                
                # Inicia el reporte y la sesión
                st.session_state.chat_history = []
                st.session_state.reporte = generar_reporte_completo(caso, st.session_state.dilema_sugerido, [])
                st.session_state.case_id = caso.historia_clinica
                st.session_state.temp_dir = temp_dir
                
                if db:
                    db.collection('casos_bioeticare360').document(caso.historia_clinica).set(st.session_state.reporte)
                    st.success(f"Caso '{caso.historia_clinica}' guardado en Firebase.")
                
                st.rerun()

    if st.session_state.reporte:
        st.markdown("---")
        a1, a2 = st.columns([3, 1])
        if a1.button("🤖 Generar/Regenerar Análisis Deliberativo con Gemini", use_container_width=True):
            if GEMINI_API_KEY:
                with st.spinner("Contactando a Gemini..."):
                    p_clave = st.session_state.reporte.get("Puntos Clave para Deliberación IA", "")
                    prompt = f"""Como comité de bioética, analiza: {json.dumps(st.session_state.reporte, indent=2, ensure_ascii=False)}. 
                    Instrucciones: 1.Sintetiza el conflicto. 2.Delibera sobre la tensión entre principios/perspectivas. 3.Enfócate en estos Puntos Clave: '{p_clave}'. 4.Concluye con una recomendación.
                    """
                    analysis = llamar_gemini(prompt, GEMINI_API_KEY)
                    st.session_state.reporte["Análisis Deliberativo (IA)"] = analysis
                    if db: db.collection('casos_bioeticare360').document(st.session_state.case_id).update({"Análisis Deliberativo (IA)": analysis})
                    st.rerun()
        
        pdf_path = os.path.join(st.session_state.temp_dir, f"Reporte_{st.session_state.case_id}.pdf")
        crear_reporte_pdf_completo(st.session_state.reporte, st.session_state.temp_dir, pdf_path)
        with open(pdf_path, "rb") as pdf_file:
            a2.download_button("📄 Descargar Reporte PDF", pdf_file, os.path.basename(pdf_path), "application/pdf", use_container_width=True)
        
        display_case_details(st.session_state.reporte, st.session_state.temp_dir)

with tab_chatbot:
    st.header("🤖 Asistente de Bioética con Gemini", anchor=False)
    if not st.session_state.case_id:
        st.info("Primero analiza un caso para poder usar el chatbot contextual.")
    else:
        st.info(f"Chatbot activo para el caso: **{st.session_state.case_id}**.")
        st.subheader("Preguntas Guiadas para Deliberación", anchor=False)
        preguntas = ["¿Cuál es el conflicto principal?", "¿Qué dice el marco legal?", "¿Cómo mediar entre las partes?", "¿Qué opciones no se han considerado?", "¿Cómo afecta la cultura/religión?", "¿Cuál es el curso de acción si priorizamos la beneficencia?"]
        def handle_q_click(q): st.session_state.last_question = q
        q_cols = st.columns(2)
        for i, q in enumerate(preguntas):
            q_cols[i%2].button(q, on_click=handle_q_click, args=(q,), use_container_width=True, key=f"q_{i}")
            
        if prompt := st.chat_input("Escribe tu pregunta...") or st.session_state.last_question:
            st.session_state.last_question = ""
            if GEMINI_API_KEY:
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with st.spinner("Pensando..."):
                    contexto = json.dumps(st.session_state.reporte, indent=2, ensure_ascii=False)
                    full_prompt = f"Eres un experto en bioética. Caso: {contexto}. Pregunta: '{prompt}'. Responde concisamente."
                    respuesta = llamar_gemini(full_prompt, GEMINI_API_KEY)
                    st.session_state.chat_history.append({"role": "assistant", "content": respuesta})
                if db: db.collection('casos_bioeticare360').document(st.session_state.case_id).update({"Historial del Chat de Deliberación": st.session_state.chat_history})
                st.rerun()

        st.subheader("Historial del Chat", anchor=False)
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

with tab_consultar:
    st.header("🔍 Consultar Casos Guardados", anchor=False)
    if not db: st.error("La conexión con Firebase no está disponible.")
    else:
        try:
            casos_ref = db.collection('casos_bioeticare360').stream()
            casos = {caso.id: caso.to_dict() for caso in casos_ref}
            if not casos: st.info("No hay casos guardados.")
            else:
                id_sel = st.selectbox("Selecciona un caso para ver sus detalles", options=list(casos.keys()))
                if id_sel: 
                    # Al consultar, no tenemos un directorio temporal, por lo que no lo pasamos
                    display_case_details(casos[id_sel], temp_dir=None)
        except Exception as e:
            st.error(f"Ocurrió un error al consultar los casos desde Firebase: {e}")
