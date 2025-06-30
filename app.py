# app.py - BIOETHICARE 360 - Versión Profesional Final
# Autores: Anderson Díaz Pérez, Joseph Javier Sanchez Acuña & AI Colaborativa
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
import plotly.io as pio # Importar plotly.io para leer figuras JSON

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
if 'ai_clinical_analysis_output' not in st.session_state:
    st.session_state.ai_clinical_analysis_output = ""
if 'clinical_history_input' not in st.session_state: # Para persistir el contenido del área de texto
    st.session_state.clinical_history_input = ""

# --- 3. Conexión con Firebase ---
@st.cache_resource
def initialize_firebase():
    """Inicializa la conexión con Firebase de forma segura."""
    try:
        if "firebase_credentials" in st.secrets:
            creds_value = st.secrets["firebase_credentials"]
            creds_dict = None

            if isinstance(creds_value, str):
                try:
                    creds_dict = json.loads(creds_value)
                except json.JSONDecodeError:
                    st.error("❌ Error: Las credenciales de Firebase no son un JSON válido. Asegúrate de que el contenido sea un JSON válido.", icon="❌")
                    return None
            # Verifica si el objeto se comporta como un diccionario (ej. AttrDict de Streamlit)
            elif hasattr(creds_value, 'keys') and callable(getattr(creds_value, 'keys')):
                creds_dict = dict(creds_value) # Convierte AttrDict a un diccionario regular
            else:
                # Este es el camino de error específico de la imagen
                st.error(f"❌ Error: Formato de credenciales de Firebase no reconocido. Tipo recibido: {type(creds_value)}. Asegúrate de que sea una cadena JSON o un diccionario.", icon="❌")
                return None

            cred = credentials.Certificate(creds_dict)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            st.success("🔌 Conexión con Firebase establecida.", icon="🔌")
            return firestore.client()
        else:
            st.warning("⚠️ Credenciales de Firebase no encontradas en `st.secrets`. Asegúrate de que la clave 'firebase_credentials' esté configurada.", icon="⚠️")
            return None
    except Exception as e:
        st.error(f"❌ Error general al conectar con Firebase: {e}", icon="❌")
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
    """Convierte un valor a entero de forma segura, devolviendo un valor predeterminado si falla la conversión."""
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
        self.ai_clinical_analysis_summary = kwargs.get('ai_clinical_analysis_summary', '') # Nuevo campo para el análisis de IA de la historia clínica
        self.perspectivas = {
            "medico": self._extract_perspective("medico", kwargs),
            "familia": self._extract_perspective("familia", kwargs),
            "comite": self._extract_perspective("comite", kwargs),
        }

    def _extract_perspective(self, prefix, kwargs):
        """Extrae las puntuaciones de los principios para una perspectiva dada de los kwargs."""
        return {
            "autonomia": safe_int(kwargs.get(f'nivel_autonomia_{prefix}')),
            "beneficencia": safe_int(kwargs.get(f'nivel_beneficencia_{prefix}')),
            "no_maleficencia": safe_int(kwargs.get(f'nivel_no_maleficencia_{prefix}')),
            "justicia": safe_int(kwargs.get(f'nivel_justicia_{prefix}')),
        }

def generar_reporte_completo(caso, dilema_sugerido, chat_history, chart_jsons=None):
    """Genera el diccionario del reporte con la nueva estructura."""
    resumen_paciente = f"Paciente {caso.nombre_paciente}, {caso.edad} años, género {caso.genero}, condición {caso.condicion}."
    if caso.semanas_gestacion > 0: resumen_paciente += f" Neonato de {caso.semanas_gestacion} sem."
    
    report_data = {
        "ID del Caso": caso.historia_clinica, "Fecha Análisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Analista": caso.nombre_analista, "Resumen del Paciente": resumen_paciente,
        "Dilema Ético Principal (Seleccionado)": caso.dilema_etico,
        "Dilema Sugerido por IA": dilema_sugerido,
        "Descripción Detallada del Caso": caso.descripcion_caso,
        "Contexto Sociocultural y Familiar": caso.antecedentes_culturales,
        "Puntos Clave para Deliberación IA": caso.puntos_clave_ia,
        "Análisis IA de Historia Clínica": caso.ai_clinical_analysis_summary, # Incluir nuevo campo
        "AnalisisMultiperspectiva": {
            "Equipo Médico": caso.perspectivas["medico"],
            "Familia/Paciente": caso.perspectivas["familia"],
            "Comité de Bioética": caso.perspectivas["comite"],
        },
        "Análisis Deliberativo (IA)": "",
        "Historial del Chat de Deliberación": chat_history,
    }
    
    if chart_jsons:
        report_data['radar_chart_json'] = chart_jsons.get('radar_comparativo_json')
        report_data['stats_chart_json'] = chart_jsons.get('estadisticas_json')
        
    return report_data

def generar_visualizaciones_avanzadas(caso): # temp_dir ya no es necesario aquí para guardar imágenes
    """Genera los gráficos y devuelve sus representaciones JSON."""
    perspectivas_data = caso.perspectivas
    labels = ["Autonomía", "Beneficencia", "No Maleficencia", "Justicia"]
    
    # Gráfico de Radar Comparativo
    fig_radar = go.Figure()
    colors_map = {'medico': 'rgba(239, 68, 68, 0.7)', 'familia': 'rgba(59, 130, 246, 0.7)', 'comite': 'rgba(34, 197, 94, 0.7)'}
    nombres = {'medico': 'Equipo Médico', 'familia': 'Familia/Paciente', 'comite': 'Comité de Bioética'}
    for key, data in perspectivas_data.items():
        fig_radar.add_trace(go.Scatterpolar(r=list(data.values()), theta=labels, fill='toself', name=nombres[key], line_color=colors_map[key]))
    fig_radar.update_layout(title="Ponderación de Principios por Perspectiva", polar=dict(radialaxis=dict(visible=True, range=[0, 5])), showlegend=True, font_size=14)
    
    # Gráfico de Consenso y Disenso
    scores = np.array([list(d.values()) for d in perspectivas_data.values()])
    fig_stats = go.Figure()
    fig_stats.add_trace(go.Bar(x=labels, y=np.mean(scores, axis=0), error_y=dict(type='data', array=np.std(scores, axis=0), visible=True), marker_color='#636EFA'))
    fig_stats.update_layout(title="Análisis de Consenso y Disenso", yaxis=dict(range=[0, 6]), font_size=14)
    
    # Devolver figuras como cadenas JSON
    return {
        'radar_comparativo_json': fig_radar.to_json(),
        'estadisticas_json': fig_stats.to_json()
    }

def crear_reporte_pdf_completo(data, temp_dir, filename):
    """Genera el reporte PDF. Los gráficos ya no se incrustan directamente como imágenes estáticas generadas por Kaleido."""
    doc = SimpleDocTemplate(filename, pagesize=letter, topMargin=inch/2, bottomMargin=inch/2)
    styles = getSampleStyleSheet()
    story = []
    
    h1 = ParagraphStyle(name='H1', fontSize=18, fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=20)
    h2 = ParagraphStyle(name='H2', fontSize=14, fontName='Helvetica-Bold', spaceBefore=12, spaceAfter=6, textColor=colors.darkblue)
    body = ParagraphStyle(name='Body', fontSize=10, fontName='Helvetica', leading=14, alignment=TA_JUSTIFY, spaceAfter=10)
    chat_style = ParagraphStyle(name='Chat', fontSize=9, fontName='Helvetica-Oblique', backColor=colors.whitesmoke, borderWidth=1, padding=5)

    story.append(Paragraph("Reporte Deliberativo - BIOETHICARE 360", h1))
    
    order = ["ID del Caso", "Fecha Análisis", "Analista", "Resumen del Paciente", "Dilema Ético Principal (Seleccionado)", "Dilema Sugerido por IA", "Descripción Detallada del Caso", "Contexto Sociocultural y Familiar", "Puntos Clave para Deliberación IA", "Análisis IA de Historia Clínica"] # Orden actualizado
    for key in order:
        if key in data and data[key]:
            story.append(Paragraph(key, h2))
            story.append(Paragraph(str(data[key]).replace('\n', '<br/>'), body))

    if "AnalisisMultiperspectiva" in data:
        story.append(Paragraph("Análisis Multiperspectiva", h2))
        for nombre, valores in data["AnalisisMultiperspectiva"].items():
            texto = f"<b>{nombre}:</b> Autonomía: {valores.get('autonomia', 0)}, Beneficencia: {valores.get('beneficencia', 0)}, No Maleficencia: {valores.get('no_maleficencia', 0)}, Justicia: {valores.get('justicia', 0)}"
            story.append(Paragraph(texto, body))
    
    if data.get("Análisis Deliberativo (IA)"):
        story.append(Paragraph("Análisis Deliberativo (IA)", h2))
        story.append(Paragraph(data["Análisis Deliberativo (IA)"].replace('\n', '<br/>'), body))

    # NOTA: Los gráficos interactivos de Plotly no se incrustan directamente como imágenes en el PDF
    # sin un proceso de renderizado adicional que requeriría Kaleido o un servicio externo.
    # Si se necesitan gráficos estáticos en el PDF, se debería considerar:
    # 1. Usar una biblioteca de gráficos que genere directamente imágenes (ej. matplotlib).
    # 2. Renderizar los gráficos de Plotly a imágenes en un servicio externo y luego incrustar esas imágenes.
    # Por ahora, se omite la sección de gráficos en el PDF para evitar el error de Kaleido.
    story.append(PageBreak())
    story.append(Paragraph("Visualizaciones de Datos (Disponibles en la interfaz web interactiva)", h1))
    story.append(Paragraph("Los gráficos de radar y consenso/disenso se muestran de forma interactiva en la aplicación web BIOETHICARE 360.", body))
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

# --- Función de ayuda para los deslizadores ---
def create_perspective_sliders(prefix, st_container):
    """Genera un conjunto de 4 deslizadores para una perspectiva dada."""
    principles = ["Autonomía", "Beneficencia", "No Maleficencia", "Justicia"]
    values = {}
    cols = st_container.columns(4)
    for i, p in enumerate(principles):
        # Usar una clave única para cada deslizador basada en el prefijo y el principio
        values[p.lower().replace(" ", "_")] = cols[i].slider(p, 0, 5, 3, key=f"{prefix}_{p.lower().replace(' ', '_')}_slider")
    return values

# --- 7. Interfaz de Usuario ---
st.title("BIOETHICARE 360 🏥")
with st.expander("Autores"):
    st.markdown("""
    - **Joseph Javier Sánchez Acuña**: Ingeniero Industrial, Experto en IA y tecnologías de vanguardia.
    - **Anderson Díaz Pérez**: Doctor en Bioética, Doctor en Salud Pública, Magíster en Ciencias Básicas Biomédicas, Especialista en Inteligencia Artificial.
    """)
st.markdown("---")

GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.warning("⚠️ Clave de API de Gemini no encontrada. Funciones de IA deshabilitadas.", icon="⚠️")

tab_analisis, tab_chatbot, tab_consultar = st.tabs(["**Análisis de Caso**", "**Asistente de Bioética (Chatbot)**", "**Consultar Casos Anteriores**"])

def display_case_details(report_data, container=st):
    """Muestra el dashboard del caso con la UI avanzada."""
    with container.container(border=True):
        case_id = report_data.get('ID del Caso', 'N/A')
        st.subheader(f"Dashboard del Caso: `{case_id}`", anchor=False)
        st.markdown("---")
        
        # Obtener los JSON de los gráficos directamente del reporte
        radar_json = report_data.get('radar_chart_json')
        stats_json = report_data.get('stats_chart_json')

        if radar_json and stats_json:
            st.markdown("##### Análisis Gráfico Avanzado")
            c1, c2 = st.columns(2)
            try:
                fig_radar = pio.from_json(radar_json)
                c1.plotly_chart(fig_radar, use_container_width=True)
            except Exception as e:
                c1.warning(f"Error al cargar gráfico de radar: {e}")
            
            try:
                fig_stats = pio.from_json(stats_json)
                c2.plotly_chart(fig_stats, use_container_width=True)
            except Exception as e:
                c2.warning(f"Error al cargar gráfico de estadísticas: {e}")
            st.markdown("---")
        else:
            st.info("No hay gráficos disponibles para este caso (posiblemente un caso antiguo o no se generaron con la nueva versión).")

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
            
            if report_data.get("Análisis IA de Historia Clínica"): # Mostrar nuevo análisis de IA
                st.markdown("**Análisis IA de Historia Clínica (Elementos Clave)**")
                st.info(report_data["Análisis IA de Historia Clínica"])
            
            st.markdown("**Ponderación por Perspectiva**")
            # Acceso seguro a los datos de perspectivas para la visualización
            perspectivas_display = report_data.get("AnalisisMultiperspectiva", {})
            for nombre, valores in perspectivas_display.items():
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
    
    # Nuevo: Entrada de Historia Clínica y Análisis de IA
    st.subheader("Historia Clínica del Paciente (Opcional para Análisis IA)", anchor=False)
    st.text_area(
        "Pega aquí la historia clínica del paciente para que la IA extraiga elementos clave.",
        key="clinical_history_input",
        height=300,
        value=st.session_state.clinical_history_input # Persistir valor
    )

    if st.button("🤖 Analizar Historia Clínica con IA", use_container_width=True, key="analyze_clinical_history_btn"):
        if st.session_state.clinical_history_input and GEMINI_API_KEY:
            with st.spinner("Analizando historia clínica con Gemini..."):
                clinical_history_text = st.session_state.clinical_history_input
                prompt_clinical_analysis = f"""
                Analiza la siguiente historia clínica del paciente. Tu objetivo es extraer los elementos más relevantes para un análisis bioético y sugerir cómo podrían informar los campos de un software de análisis de casos.

                **Historia Clínica:**
                {clinical_history_text}

                **Instrucciones para la Respuesta:**
                1.  **Resumen de Datos Clave:** Un breve resumen de los datos médicos cruciales (diagnóstico principal, estado actual, tratamientos relevantes).
                2.  **Identificación de Conflictos Éticos Potenciales:** ¿Qué dilemas o tensiones éticas se vislumbran en esta historia?
                3.  **Sugerencias para el Campo 'Descripción Detallada del Caso':** Extrae los puntos narrativos más importantes.
                4.  **Sugerencias para el Campo 'Contexto Sociocultural y Familiar':** ¿Hay indicios de factores culturales, familiares o sociales relevantes?
                5.  **Sugerencias para el Campo 'Puntos Clave para Deliberación IA':** Formula preguntas o áreas específicas que la IA debería considerar en una deliberación.
                6.  **Dilema Ético Sugerido (de la lista):** De la siguiente lista de dilemas, ¿cuál es el más probable o prominente? Responde solo el nombre del dilema de la lista, si es posible.
                    Lista de dilemas: {', '.join(dilemas_opciones.keys())}

                Formato de la respuesta: Utiliza encabezados claros para cada sección.
                """
                ai_analysis = llamar_gemini(prompt_clinical_analysis, GEMINI_API_KEY)
                st.session_state.ai_clinical_analysis_output = ai_analysis
                # Intentar extraer el dilema sugerido de la salida de la IA si está ahí
                for line in ai_analysis.split('\n'):
                    if "Dilema Ético Sugerido (de la lista):" in line:
                        suggested_dilemma_raw = line.replace("Dilema Ético Sugerido (de la lista):", "").strip()
                        # Limpiar el dilema sugerido para que coincida exactamente con una de las opciones
                        found_dilemma = None
                        for d_key in dilemas_opciones.keys():
                            if d_key.lower() in suggested_dilemma_raw.lower():
                                found_dilemma = d_key
                                break
                        if found_dilemma:
                            st.session_state.dilema_sugerido = found_dilemma
                            st.success(f"Dilema Sugerido por IA desde Historia Clínica: **{st.session_state.dilema_sugerido}**")
                        break
            st.rerun()
        elif not GEMINI_API_KEY:
            st.error("La clave de API de Gemini es necesaria para analizar la historia clínica.")
        else:
            st.warning("Por favor, pega la historia clínica en el campo de texto para que la IA la analice.")

    if st.session_state.ai_clinical_analysis_output:
        st.subheader("Análisis de la Historia Clínica por IA", anchor=False)
        st.markdown(st.session_state.ai_clinical_analysis_output)
        st.markdown("---")


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
        
        # El botón de sugerencia de dilema de IA ahora está fuera del formulario para un mejor flujo
        # Pero si el usuario aún quiere sugerir basándose en la descripción, esto puede quedarse.
        # Por ahora, lo mantendremos ya que es un prompt diferente.
        if st.form_submit_button("Sugerir Dilema con IA (desde Descripción)", use_container_width=True):
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
        # Creación de deslizadores refactorizada
        medico_scores = {}
        familia_scores = {}
        comite_scores = {}

        with st.expander("Perspectiva del Equipo Médico"):
            medico_scores = create_perspective_sliders("medico", st)
        with st.expander("Perspectiva de la Familia / Paciente"):
            familia_scores = create_perspective_sliders("familia", st)
        with st.expander("Perspectiva del Comité de Bioética"):
            comite_scores = create_perspective_sliders("comite", st)

        submitted = st.form_submit_button("Analizar Caso y Generar Dashboard", use_container_width=True)

    if submitted:
        if not historia_clinica:
            st.error("El campo 'Nº Historia Clínica / ID del Caso' es obligatorio.")
        else:
            with st.spinner("Procesando y generando reporte..."):
                cleanup_temp_dir()
                
                # Recopilar datos del formulario explícitamente, mapeando las salidas de los deslizadores
                form_data_for_caso = {
                    'nombre_paciente': nombre_paciente,
                    'historia_clinica': historia_clinica,
                    'edad': edad,
                    'genero': genero,
                    'nombre_analista': nombre_analista,
                    'dilema_etico': dilema_etico,
                    'descripcion_caso': descripcion_caso,
                    'antecedentes_culturales': antecedentes_culturales,
                    'condicion': condicion,
                    'semanas_gestacion': semanas_gestacion,
                    'puntos_clave_ia': puntos_clave_ia,
                    'ai_clinical_analysis_summary': st.session_state.ai_clinical_analysis_output, # Pasar el resumen del análisis de IA
                }
                # Mapear las puntuaciones de perspectiva de nuevo a la estructura plana esperada por CasoBioetico
                for p_name, scores_dict in [("medico", medico_scores), ("familia", familia_scores), ("comite", comite_scores)]:
                    for principle, value in scores_dict.items():
                        form_data_for_caso[f'nivel_{principle}_{p_name}'] = value

                caso = CasoBioetico(**form_data_for_caso)
                
                # Generar los JSON de los gráficos
                chart_jsons = generar_visualizaciones_avanzadas(caso)

                # Inicia el reporte y la sesión
                st.session_state.chat_history = []
                st.session_state.reporte = generar_reporte_completo(caso, st.session_state.dilema_sugerido, [], chart_jsons) # Pasar chart_jsons
                st.session_state.case_id = caso.historia_clinica
                
                # El temp_dir todavía se usa para el PDF, no para los gráficos
                temp_dir = tempfile.mkdtemp()
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
                    prompt = f"""
                    Como comité de bioética, analiza el siguiente caso.

                    **Información del Caso:**
                    {json.dumps(st.session_state.reporte, indent=2, ensure_ascii=False)}

                    **Puntos Clave para la Deliberación (énfasis en esto):**
                    {p_clave if p_clave else "No se proporcionaron puntos clave adicionales. Enfócate en la descripción y la ponderación."}

                    **Instrucciones para el Análisis:**
                    1.  **Síntesis del Conflicto:** Identifica claramente el conflicto bioético central, destacando los principios o valores en tensión.
                    2.  **Análisis Multiperspectiva:** Delibera sobre cómo las diferentes perspectivas (médico, familia/paciente, comité) ponderan los principios de autonomía, beneficencia, no maleficencia y justicia. Señala las áreas de consenso y disenso.
                    3.  **Consideración de Puntos Clave:** Integra los 'Puntos Clave para Deliberación IA' proporcionados, si existen, para guiar tu análisis.
                    4.  **Recomendación Bioética:** Concluye con una recomendación clara y justificada, considerando el bienestar del paciente, la ética profesional y el contexto legal/social relevante.

                    Tu respuesta debe ser profesional, estructurada y basada en principios bioéticos.
                    """
                    analysis = llamar_gemini(prompt, GEMINI_API_KEY)
                    st.session_state.reporte["Análisis Deliberativo (IA)"] = analysis
                    if db: db.collection('casos_bioeticare360').document(st.session_state.case_id).update({"Análisis Deliberativo (IA)": analysis})
                    st.rerun()
            
        # Generar el PDF usando el temp_dir de la sesión
        pdf_path = os.path.join(st.session_state.temp_dir, f"Reporte_{st.session_state.case_id}.pdf")
        crear_reporte_pdf_completo(st.session_state.reporte, st.session_state.temp_dir, pdf_path)
        with open(pdf_path, "rb") as pdf_file:
            a2.download_button("📄 Descargar Reporte PDF", pdf_file, os.path.basename(pdf_path), "application/pdf", use_container_width=True)
            
        display_case_details(st.session_state.reporte) # temp_dir es manejado internamente ahora

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
                    full_prompt = f"""
                    Eres un asistente de bioética especializado en la deliberación de casos clínicos. Se te ha proporcionado el siguiente caso y su análisis inicial.

                    **Contexto del Caso Actual:**
                    {contexto}

                    **Pregunta del Usuario:**
                    '{prompt}'

                    **Instrucciones para tu respuesta:**
                    1.  **Enfócate en el Caso:** Tu respuesta debe ser directamente relevante al caso proporcionado, utilizando la información disponible.
                    2.  **Rol de Experto:** Responde desde una perspectiva de experto en bioética, aplicando principios y marcos éticos.
                    3.  **Claridad y Concisión:** Sé claro, directo y conciso. Evita la divagación.
                    4.  **No Generalices:** No des respuestas genéricas si el caso permite una respuesta específica.

                    Proporciona tu respuesta basada en el contexto dado y la pregunta:
                    """
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
                    display_case_details(casos[id_sel])
        except Exception as e:
            st.error(f"Ocurrió un error al consultar los casos desde Firebase: {e}")
