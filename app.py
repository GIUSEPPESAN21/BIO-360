# app.py - BIOETHICARE 360 - Versión Profesional Definitiva
# Autores: Anderson Díaz Pérez & Joseph Javier Sánchez Acuña
# VERSIÓN CON CORRECCIÓN DE ERRORES DE KEY, ANÁLISIS DE HISTORIA CLÍNICA Y ARQUITECTURA ROBUSTA

# --- 1. Importaciones ---
import os
import json
import requests
import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import tempfile
import shutil
import plotly.io as pio # Para leer figuras desde JSON

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

# Inicialización robusta del estado de la sesión
session_defaults = {
    'reporte': None,
    'temp_dir': None,
    'case_id': None,
    'chat_history': [],
    'last_question': "",
    'dilema_sugerido': None,
    'ai_clinical_analysis_output': "",
    'clinical_history_input': ""
}
for key, default_value in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

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

# --- 4. Base de Conocimiento ---
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
        self.edad = safe_int(kwargs.get('edad'))
        self.genero = kwargs.get('genero', 'N/A')
        self.nombre_analista = kwargs.get('nombre_analista', 'N/A')
        self.dilema_etico = kwargs.get('dilema_etico', list(dilemas_opciones.keys())[0])
        self.descripcion_caso = kwargs.get('descripcion_caso', '')
        self.antecedentes_culturales = kwargs.get('antecedentes_culturales', '')
        self.condicion = kwargs.get('condicion', 'Estable')
        self.semanas_gestacion = safe_int(kwargs.get('semanas_gestacion'))
        self.puntos_clave_ia = kwargs.get('puntos_clave_ia', '')
        self.ai_clinical_analysis_summary = kwargs.get('ai_clinical_analysis_summary', '')
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

def generar_reporte_completo(caso, dilema_sugerido, chat_history, chart_jsons):
    """Genera el diccionario del reporte, incluyendo los JSON de los gráficos."""
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
        "Análisis IA de Historia Clínica": caso.ai_clinical_analysis_summary,
        "AnalisisMultiperspectiva": {
            "Equipo Médico": caso.perspectivas["medico"],
            "Familia/Paciente": caso.perspectivas["familia"],
            "Comité de Bioética": caso.perspectivas["comite"],
        },
        "Análisis Deliberativo (IA)": "",
        "Historial del Chat de Deliberación": chat_history,
        "radar_chart_json": chart_jsons.get('radar_comparativo_json'),
        "stats_chart_json": chart_jsons.get('estadisticas_json'),
    }

def generar_visualizaciones_avanzadas(caso):
    """Genera los gráficos y devuelve sus representaciones JSON."""
    perspectivas_data = caso.perspectivas
    labels = ["Autonomía", "Beneficencia", "No Maleficencia", "Justicia"]
    
    fig_radar = go.Figure()
    colors_map = {'medico':'rgba(239, 68, 68, 0.7)','familia':'rgba(59, 130, 246, 0.7)','comite':'rgba(34, 197, 94, 0.7)'}
    nombres = {'medico': 'Equipo Médico', 'familia': 'Familia/Paciente', 'comite': 'Comité de Bioética'}
    for key, data in perspectivas_data.items():
        fig_radar.add_trace(go.Scatterpolar(r=list(data.values()), theta=labels, fill='toself', name=nombres[key], line_color=colors_map[key]))
    fig_radar.update_layout(title="Ponderación por Perspectiva", polar=dict(radialaxis=dict(visible=True, range=[0, 5])), showlegend=True, font_size=14)
    
    scores = np.array([list(d.values()) for d in perspectivas_data.values()])
    fig_stats = go.Figure()
    fig_stats.add_trace(go.Bar(x=labels, y=np.mean(scores, axis=0), error_y=dict(type='data', array=np.std(scores, axis=0), visible=True), marker_color='#636EFA'))
    fig_stats.update_layout(title="Análisis de Consenso y Disenso", yaxis=dict(range=[0, 6]), font_size=14)
    
    return {
        'radar_comparativo_json': fig_radar.to_json(),
        'estadisticas_json': fig_stats.to_json()
    }

def crear_reporte_pdf_completo(data, filename):
    """Genera el reporte PDF. Los gráficos no se incrustan para evitar errores con Kaleido."""
    doc = SimpleDocTemplate(filename, pagesize=letter, topMargin=inch/2, bottomMargin=inch/2)
    styles = getSampleStyleSheet()
    story = []
    
    h1 = ParagraphStyle(name='H1', fontSize=18, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=20)
    h2 = ParagraphStyle(name='H2', fontSize=14, fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=6, textColor=colors.darkblue)
    body = ParagraphStyle(name='Body', fontSize=10, fontName='Helvetica', leading=14, alignment=TA_JUSTIFY, spaceAfter=10)
    chat_style = ParagraphStyle(name='Chat', fontSize=9, fontName='Helvetica-Oblique', backColor=colors.whitesmoke, borderWidth=1, padding=5)

    story.append(Paragraph("Reporte Deliberativo - BIOETHICARE 360", h1))
    
    order = ["ID del Caso", "Fecha Análisis", "Analista", "Resumen del Paciente", "Dilema Ético Principal (Seleccionado)", "Dilema Sugerido por IA", "Descripción Detallada del Caso", "Contexto Sociocultural y Familiar", "Puntos Clave para Deliberación IA", "Análisis IA de Historia Clínica"]
    for key in order:
        if key in data and data.get(key):
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

    story.append(PageBreak())
    story.append(Paragraph("Visualizaciones de Datos", h1))
    story.append(Paragraph("Los gráficos de radar y consenso/disenso se muestran de forma interactiva en la aplicación web.", body))
            
    if data.get("Historial del Chat de Deliberación"):
        story.append(PageBreak())
        story.append(Paragraph("Historial del Chat de Deliberación", h1))
        for msg in data["Historial del Chat de Deliberación"]:
            role_text = f"<b>{'Usuario' if msg['role'] == 'user' else 'Asistente IA'}:</b> {msg['content']}"
            story.append(Paragraph(role_text, chat_style))

    doc.build(story)

# --- 6. Función para llamar a Gemini API ---
def llamar_gemini(prompt, api_key):
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

def display_case_details(report_data, key_prefix, container=st):
    """Muestra el dashboard del caso con la UI avanzada y llaves únicas."""
    with container.container(border=True):
        case_id = report_data.get('ID del Caso', 'N/A')
        st.subheader(f"Dashboard del Caso: `{case_id}`", anchor=False)
        st.markdown("---")
        
        radar_json = report_data.get('radar_chart_json')
        stats_json = report_data.get('stats_chart_json')
        if radar_json and stats_json:
            st.markdown("##### Análisis Gráfico Avanzado")
            c1, c2 = st.columns(2)
            try:
                c1.plotly_chart(pio.from_json(radar_json), use_container_width=True, key=f"{key_prefix}_radar_{case_id}")
                c2.plotly_chart(pio.from_json(stats_json), use_container_width=True, key=f"{key_prefix}_stats_{case_id}")
            except Exception as e:
                st.warning(f"No se pudieron cargar los gráficos para el caso {case_id}. Error: {e}")
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
            st.text_area("Descripción:", value=report_data.get('Descripción Detallada del Caso',''), height=150, disabled=True, key=f"{key_prefix}_desc_{case_id}")
            st.text_area("Contexto Sociocultural:", value=report_data.get('Contexto Sociocultural y Familiar',''), height=100, disabled=True, key=f"{key_prefix}_context_{case_id}")
            if report_data.get("Análisis IA de Historia Clínica"):
                st.markdown("**Análisis IA de Historia Clínica (Elementos Clave)**")
                st.info(report_data["Análisis IA de Historia Clínica"])
            
            # --- SECCIÓN CORREGIDA (v2) ---
            # El error 'TypeError' se debe a caracteres inválidos (espacios, '/') en la llave del widget.
            # La solución es "sanitizar" el nombre de la perspectiva para crear una llave limpia y válida.
            st.markdown("**Ponderación por Perspectiva (escala 0-5)**")
            for nombre, valores in report_data.get("AnalisisMultiperspectiva", {}).items():
                st.markdown(f"**{nombre}**")
                p_cols = st.columns(4)
                
                # Sanitizar el 'nombre' para que sea una llave válida (ej: "Familia/Paciente" -> "FamiliaPaciente")
                nombre_sanitized = "".join(filter(str.isalnum, nombre))

                p_cols[0].metric("Autonomía", valores.get('autonomia', 0), key=f"{key_prefix}_metric_aut_{nombre_sanitized}_{case_id}")
                p_cols[1].metric("Beneficencia", valores.get('beneficencia', 0), key=f"{key_prefix}_metric_ben_{nombre_sanitized}_{case_id}")
                p_cols[2].metric("No Maleficencia", valores.get('no_maleficencia', 0), key=f"{key_prefix}_metric_nom_{nombre_sanitized}_{case_id}")
                p_cols[3].metric("Justicia", valores.get('justicia', 0), key=f"{key_prefix}_metric_jus_{nombre_sanitized}_{case_id}")
            # --- FIN DE LA SECCIÓN CORREGIDA ---
            
            st.markdown("**Historial del Chat**")
            for msg in report_data.get("Historial del Chat de Deliberación", []):
                with st.chat_message(msg['role']): st.markdown(msg['content'])

def cleanup_temp_dir():
    if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir)
    st.session_state.temp_dir = tempfile.mkdtemp()

with tab_analisis:
    st.header("1. Asistente de Análisis Previo (Opcional)", anchor=False)
    st.text_area(
        "Pega aquí la historia clínica del paciente para que la IA extraiga elementos clave.",
        key="clinical_history_input",
        height=250,
        value=st.session_state.clinical_history_input
    )
    if st.button("🤖 Analizar Historia Clínica con IA", use_container_width=True):
        if st.session_state.clinical_history_input and GEMINI_API_KEY:
            with st.spinner("Analizando historia clínica con Gemini..."):
                prompt = f"""Analiza la siguiente historia clínica. Extrae los elementos más relevantes para un análisis bioético.
                **Historia Clínica:**\n{st.session_state.clinical_history_input}\n
                **Instrucciones:**
                1. **Resumen de Datos Clave:** Diagnóstico, estado, tratamientos.
                2. **Conflictos Éticos Potenciales:** ¿Qué dilemas se vislumbran?
                3. **Sugerencias para 'Descripción Detallada':** Extrae la narrativa principal.
                4. **Sugerencias para 'Contexto Sociocultural':** ¿Hay factores familiares o culturales?
                5. **Sugerencias para 'Puntos Clave para Deliberación':** Formula preguntas clave.
                6. **Dilema Ético Sugerido:** De la lista `{', '.join(dilemas_opciones.keys())}`, ¿cuál es el más probable? Responde solo el nombre.
                """
                ai_analysis = llamar_gemini(prompt, GEMINI_API_KEY)
                st.session_state.ai_clinical_analysis_output = ai_analysis
                st.rerun()
        else: st.warning("Por favor, pega la historia clínica y asegúrate de que la clave de API de Gemini está configurada.")

    if st.session_state.ai_clinical_analysis_output:
        st.info(st.session_state.ai_clinical_analysis_output)

    st.header("2. Registro y Contexto del Caso", anchor=False)
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
        antecedentes_culturales = st.text_area("Contexto Sociocultural y Familiar", height=100)
        puntos_clave_ia = st.text_area("Puntos Clave para Deliberación IA (Opcional)", height=100)
        
        st.header("3. Ponderación Multiperspectiva (0-5)", anchor=False)
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
                chart_jsons = generar_visualizaciones_avanzadas(caso)
                
                st.session_state.chat_history = []
                st.session_state.reporte = generar_reporte_completo(caso, st.session_state.dilema_sugerido, [], chart_jsons)
                st.session_state.case_id = caso.historia_clinica
                
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
                    Instrucciones: 1.Sintetiza el conflicto. 2.Delibera sobre la tensión entre principios/perspectivas. 3.Enfócate en estos Puntos Clave: '{p_clave}'. 4.Concluye con una recomendación."""
                    analysis = llamar_gemini(prompt, GEMINI_API_KEY)
                    st.session_state.reporte["Análisis Deliberativo (IA)"] = analysis
                    if db: db.collection('casos_bioeticare360').document(st.session_state.case_id).update({"Análisis Deliberativo (IA)": analysis})
                    st.rerun()
        
        pdf_path = os.path.join(st.session_state.temp_dir, f"Reporte_{st.session_state.case_id}.pdf")
        crear_reporte_pdf_completo(st.session_state.reporte, pdf_path)
        with open(pdf_path, "rb") as pdf_file:
            a2.download_button("📄 Descargar Reporte PDF", pdf_file, os.path.basename(pdf_path), "application/pdf", use_container_width=True)
        
        display_case_details(st.session_state.reporte, key_prefix="active")

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
                id_sel = st.selectbox("Selecciona un caso para ver sus detalles", options=list(casos.keys()), key="case_selector_consultar")
                if id_sel: 
                    display_case_details(casos[id_sel], key_prefix="consult")
        except Exception as e:
            st.error(f"Ocurrió un error al consultar los casos desde Firebase: {e}")
