import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import uuid

# ==========================
# CONFIG GENERAL
# ==========================
API_URL = "https://proyecto-salud-digital.onrender.com"

st.set_page_config(page_title="Dashboard Clínica", layout="wide")
st.title("Dashboard de Gestión Clínica")

# ==========================
# LOGIN SEGURO
# ==========================

if "auth" not in st.session_state:
    st.session_state.auth = False

with st.sidebar.form("login_form"):
    st.header("Login")

    access_key_input = st.text_input("Access Key", type="password")
    permission_key_input = st.text_input("Permission Key", type="password")

    submitted = st.form_submit_button("Ingresar")

    if submitted:
        st.session_state.access_key = access_key_input
        st.session_state.permission_key = permission_key_input
        st.session_state.auth = True
        st.rerun()

if not st.session_state.auth:
    st.stop()

access_key = st.session_state.access_key
permission_key = st.session_state.permission_key

HEADERS = {
    "x-access-key": access_key,
    "x-permission-key": permission_key
}

# ==========================
# FUNCIONES API
# ==========================

@st.cache_data(ttl=15)
def fetch_patients(access_key, permission_key):
    headers = {
        "x-access-key": access_key,
        "x-permission-key": permission_key
    }
    r = requests.get(
        f"{API_URL}/fhir/Patient?limit=100&offset=0",
        headers=headers
    )
    if r.status_code != 200:
        return None
    return pd.DataFrame(r.json()["data"])


@st.cache_data(ttl=15)
def fetch_observations(access_key, permission_key):
    headers = {
        "x-access-key": access_key,
        "x-permission-key": permission_key
    }
    r = requests.get(
        f"{API_URL}/fhir/Observation?limit=500&offset=0",
        headers=headers
    )
    if r.status_code != 200:
        return None, None
    data = r.json()
    obs_df = pd.DataFrame(data.get("data", []))
    alerts_df = pd.DataFrame(data.get("alerts", []))
    return obs_df, alerts_df


# ==========================
# CARGAR DATOS
# ==========================

patients_df = fetch_patients(access_key, permission_key)
obs_df, alerts_df = fetch_observations(access_key, permission_key)

if patients_df is None or patients_df.empty:
    st.error("No se pudieron cargar pacientes.")
    st.stop()

if obs_df is None:
    st.error("No se pudieron cargar observaciones.")
    st.stop()

# ==========================
# DETECTAR ROL
# ==========================

is_admin = "serialized_data" in patients_df.columns

if not is_admin:

    if alerts_df is not None and "patient_id" in alerts_df.columns or \
       (alerts_df is not None and alerts_df.empty and len(patients_df) > 1):
        is_medico = True
        is_patient = False
    elif len(patients_df) == 1 and alerts_df is not None and alerts_df.empty:

        if "is_abnormal" in obs_df.columns:
            is_medico = True
            is_patient = False
        else:
            is_medico = False
            is_patient = True
    else:
        is_medico = True
        is_patient = False
else:
    is_medico = False
    is_patient = False

# ==========================
# SELECCIÓN PACIENTE
# ==========================

if is_admin:
    st.subheader("Pacientes (Admin)")
    st.dataframe(patients_df[["id"]])
    selected_patient = st.selectbox("Seleccionar Paciente", patients_df["id"])

elif is_patient:
    selected_patient = patients_df.iloc[0]["id"]
    st.subheader(f"Paciente: {selected_patient}")

elif is_medico:
    st.subheader("Pacientes Registrados")
    display_cols = [
        c for c in
        ["id", "given_name", "family_name", "gender", "birth_date"]
        if c in patients_df.columns
    ]
    display_df = patients_df[display_cols].reset_index(drop=True)
    st.dataframe(display_df)
    idx = st.number_input(
        "Seleccione índice paciente",
        min_value=0,
        max_value=len(display_df) - 1,
        step=1
    )
    selected_patient = display_df.iloc[idx]["id"]

# ==========================
# INFO PACIENTE
# ==========================

patient_info = patients_df[patients_df["id"] == selected_patient]

if not patient_info.empty:
    info = patient_info.iloc[0]
    st.markdown("### Información Paciente")
    col1, col2, col3 = st.columns(3)
    col1.metric("Nombre", f"{info.get('given_name', '')} {info.get('family_name', '')}")
    col2.metric("Genero", info.get("gender", "N/A"))
    col3.metric("Nacimiento", info.get("birth_date", "N/A"))

    if is_medico and info.get("medical_summary"):
        st.markdown("**📋 Medical Summary:**")
        st.info(info.get("medical_summary", ""))

# ==========================
# MEDICAL SUMMARY (SOLO MEDICO)
# ==========================

if is_medico:
    r = requests.get(
        f"{API_URL}/medical_summary/{selected_patient}",
        headers=HEADERS
    )
    if r.status_code == 200:
        summary = r.json()
        st.subheader("Resumen Médico")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Observaciones", summary.get("total_observations", 0))
        c2.metric("Alertas", summary.get("alerts", 0))
        c3.metric("Tipos Signos", summary.get("vital_types", 0))

# ==========================
# ALERTAS CLÍNICAS
# ==========================

if is_medico and alerts_df is not None and not alerts_df.empty:
    patient_alerts = alerts_df[alerts_df["patient_id"] == selected_patient]
    if not patient_alerts.empty:
        st.error("⚠ ALERTAS CLINICAS")
        for _, a in patient_alerts.iterrows():
            st.warning(f"{a['code']} = {a['value']} → {a['message']}")

# ==========================
# CREAR OBSERVACION
# ==========================

if is_medico or is_admin:
    st.subheader("Nueva Observación")
    with st.form("new_obs"):
        col1, col2 = st.columns(2)
        code = col1.selectbox(
            "Signo Vital",
            ["heart_rate", "temperature", "glucose",
             "platelets", "systolic_pressure", "diastolic_pressure"]
        )
        value = col2.number_input("Valor", step=0.1)
        unit = st.text_input("Unidad")
        submit = st.form_submit_button("Guardar")

        if submit:
            impossible = False
            if code == "temperature" and value > 45:
                impossible = True
            if code == "heart_rate" and value > 250:
                impossible = True
            if code == "systolic_pressure" and value > 350:
                impossible = True

            if impossible:
                st.error("Valor clínicamente imposible")
            else:
                payload = {
                    "patient_id": selected_patient,
                    "code": code,
                    "value": value,
                    "unit": unit
                }
                r = requests.post(
                    f"{API_URL}/fhir/Observation",
                    headers=HEADERS,
                    json=payload
                )
                if r.status_code == 200:
                    st.success("Observación creada")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(r.text)

# ==========================
# EDITAR OBSERVACION
# ==========================

if is_admin or is_medico:
    st.subheader("Editar Observación")
    with st.form("edit_obs"):
        obs_id = st.number_input("ID de la Observación", min_value=1, step=1)
        col1, col2 = st.columns(2)
        edit_code = col1.selectbox(
            "Signo Vital",
            ["heart_rate", "temperature", "glucose",
             "platelets", "systolic_pressure", "diastolic_pressure"],
            key="edit_code"
        )
        edit_value = col2.number_input("Nuevo Valor", step=0.1, key="edit_value")
        edit_unit = st.text_input("Unidad", key="edit_unit")
        update_btn = st.form_submit_button("Actualizar Observación")

        if update_btn:
            payload = {
                "patient_id": selected_patient,
                "code": edit_code,
                "value": edit_value,
                "unit": edit_unit
            }
            r = requests.put(
                f"{API_URL}/fhir/Observation/{int(obs_id)}",
                headers=HEADERS,
                json=payload
            )
            if r.status_code == 200:
                st.success("Observación actualizada")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(r.text)

# ==========================
# ELIMINAR OBSERVACION
# ==========================

if is_admin or is_medico:
    st.subheader("Eliminar Observación")
    with st.form("delete_obs"):
        delete_id = st.number_input("ID eliminar", min_value=1, step=1)
        del_btn = st.form_submit_button("Eliminar Observación")
        if del_btn:
            r = requests.delete(
                f"{API_URL}/fhir/Observation/{int(delete_id)}",
                headers=HEADERS
            )
            if r.status_code == 200:
                st.success("Observación eliminada")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(r.text)

# ==========================
# CREAR PACIENTE
# ==========================

if is_admin or is_medico:
    st.subheader("Crear Paciente")
    with st.form("create_patient"):
        col1, col2 = st.columns(2)
        given = col1.text_input("Nombre")
        family = col2.text_input("Apellido")
        col3, col4 = st.columns(2)
        gender = col3.selectbox("Genero", ["male", "female", "other"])
        birth = col4.text_input("Nacimiento (YYYY-MM-DD)")
        medical_summary = st.text_area("Medical Summary")
        patient_key_input = st.text_input(
            "Patient Key",
            help="Clave que usará el paciente para iniciar sesión. Si la dejas vacía se genera automáticamente."
        )
        submit = st.form_submit_button("Crear Paciente")

        if submit:
            if not given or not family or not birth:
                st.error("Todos los campos son obligatorios")
            else:
                patient_id = f"pac-{uuid.uuid4().hex[:8]}"
                patient_key = patient_key_input.strip() if patient_key_input.strip() else uuid.uuid4().hex

                payload = {
                    "id": patient_id,
                    "given_name": given,
                    "family_name": family,
                    "gender": gender,
                    "birthDate": birth,
                    "medical_summary": medical_summary,
                    "patient_key": patient_key
                }
                r = requests.post(
                    f"{API_URL}/fhir/Patient",
                    headers=HEADERS,
                    json=payload
                )
                if r.status_code == 200:
                    st.success("✅ Paciente creado correctamente")
                    # Mostrar credenciales generadas para el paciente
                    st.info("🔑 Guarda estas credenciales para el paciente:")
                    st.code(f"ID del paciente:  {patient_id}\nPatient Key:      {patient_key}", language="text")
                    st.warning("⚠️ Esta key no se volverá a mostrar. Cópiala ahora.")
                    st.cache_data.clear()
                else:
                    st.error("Error al crear paciente")
                    st.write(r.status_code, r.text)

# ==========================
# EDITAR PACIENTE (ADMIN)
# ==========================

if is_admin:
    st.subheader("Editar Paciente")
    with st.form("edit_patient"):
        p_id = st.text_input("ID Paciente a editar")
        col1, col2 = st.columns(2)
        new_given = col1.text_input("Nuevo Nombre")
        new_family = col2.text_input("Nuevo Apellido")
        col3, col4 = st.columns(2)
        new_gender = col3.selectbox(
            "Nuevo Genero",
            ["", "male", "female", "other"]
        )
        new_birth = col4.text_input("Nueva Fecha Nacimiento (YYYY-MM-DD)")
        new_summary = st.text_area("Nuevo Medical Summary")
        new_patient_key = st.text_input(
            "Nueva Patient Key",
            help="Déjala vacía para mantener la key actual del paciente."
        )
        update_p_btn = st.form_submit_button("Actualizar Paciente")

        if update_p_btn:
            if not p_id:
                st.error("Debes ingresar el ID del paciente")
            else:
                r_get = requests.get(
                    f"{API_URL}/fhir/Patient/{p_id}",
                    headers=HEADERS
                )
                if r_get.status_code != 200:
                    st.error(f"Paciente no encontrado: {r_get.text}")
                else:
                    current = r_get.json()

                    resolved_key = new_patient_key.strip() if new_patient_key.strip() else current.get("patient_key", "")
                    payload = {
                        "id": p_id,
                        "given_name": new_given.strip() or current.get("given_name", ""),
                        "family_name": new_family.strip() or current.get("family_name", ""),
                        "gender": new_gender if new_gender else current.get("gender", ""),
                        "birthDate": new_birth.strip() or str(current.get("birth_date", "")),
                        "medical_summary": new_summary.strip() or current.get("medical_summary", ""),
                        "patient_key": resolved_key
                    }
                    r = requests.put(
                        f"{API_URL}/fhir/Patient/{p_id}",
                        headers=HEADERS,
                        json=payload
                    )
                    if r.status_code == 200:
                        st.success("Paciente actualizado")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"Error {r.status_code}: {r.text}")

# ==========================
# ELIMINAR PACIENTE (ADMIN)
# ==========================

if is_admin:
    st.subheader("Eliminar Paciente")
    with st.form("delete_patient"):
        p_del = st.text_input("ID eliminar")
        del_p_btn = st.form_submit_button("Eliminar Paciente")
        if del_p_btn:
            r = requests.delete(
                f"{API_URL}/fhir/Patient/{p_del}",
                headers=HEADERS
            )
            if r.status_code == 200:
                st.success("Paciente eliminado")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(r.text)

# ==========================
# FILTRAR OBSERVACIONES
# ==========================

if "total" in obs_df.columns:
    st.subheader("Conteo Observaciones")
    st.dataframe(obs_df)
    st.stop()


if is_patient:
    patient_obs = obs_df.copy()
elif "patient_id" in obs_df.columns:
    patient_obs = obs_df[obs_df["patient_id"] == selected_patient].copy()
else:
    patient_obs = obs_df.copy()

if patient_obs.empty:
    st.info("Sin observaciones")
    st.stop()

# ==========================
# LIMPIEZA
# ==========================

patient_obs["value_num"] = pd.to_numeric(patient_obs["value"], errors="coerce")
patient_obs["created_at"] = pd.to_datetime(patient_obs["created_at"])

# ==========================
# OUTLIERS
# ==========================

def is_outlier(v, c):
    if c == "temperature":
        return v < 30 or v > 45
    if c == "heart_rate":
        return v < 30 or v > 250
    if c == "systolic_pressure":
        return v < 50 or v > 300
    return False

patient_obs["outlier"] = patient_obs.apply(
    lambda r: is_outlier(r["value_num"], r["code"]), axis=1
)

# ==========================
# GRAFICAS
# ==========================

st.subheader("Tendencias")

# Rangos normales para marcar puntos anormales en gráfica (solo médico)
NORMAL_RANGES = {
    "heart_rate":         (60, 100),
    "temperature":        (36, 37.5),
    "glucose":            (70, 140),
    "platelets":          (150000, 450000),
    "systolic_pressure":  (90, 120),
    "diastolic_pressure": (60, 80),
}

import plotly.graph_objects as go

for code in patient_obs["code"].unique():
    df = patient_obs[patient_obs["code"] == code].sort_values("created_at").copy()

    fig = px.line(df, x="created_at", y="value_num", title=code, markers=True)
    fig.update_traces(marker=dict(size=8, color="#2196F3"), line=dict(color="#2196F3"))

    # Puntos rojos SOLO para médico
    if is_medico and code in NORMAL_RANGES:
        lo, hi = NORMAL_RANGES[code]
        abnormal = df[(df["value_num"] < lo) | (df["value_num"] > hi)]
        if not abnormal.empty:
            fig.add_trace(go.Scatter(
                x=abnormal["created_at"],
                y=abnormal["value_num"],
                mode="markers",
                marker=dict(color="red", size=13, symbol="circle",
                            line=dict(color="darkred", width=2)),
                name="⚠ Anormal"
            ))

    st.plotly_chart(fig, use_container_width=True)

# ==========================
# HEATMAP MEDICO
# ==========================

if is_medico:
    st.subheader("Mapa Calor")
    heat_df = patient_obs.pivot_table(
        index="created_at",
        columns="code",
        values="value_num",
        aggfunc="mean"
    )
    fig = px.imshow(heat_df, aspect="auto")
    st.plotly_chart(fig, use_container_width=True)

# ==========================
# TABLA RESUMEN
# ==========================

st.subheader("Resumen Observaciones")

cols = [
    c for c in
    ["id", "created_at", "code", "value", "value_num", "outlier"]
    if c in patient_obs.columns
]

df = patient_obs[cols].sort_values("created_at", ascending=False)

def style(row):
    if row["outlier"]:
        return ["color:red;font-weight:bold"] * len(row)
    return [""] * len(row)

styled = df.style.apply(style, axis=1)
styled = styled.hide(axis="columns", subset=["outlier"])

st.dataframe(styled, use_container_width=True)