import os
import time
from datetime import datetime
from typing import Optional, List
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi import Request
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from pydantic import BaseModel
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

# =============================
# CONFIG
# =============================

load_dotenv()

ACCESS_KEY = os.getenv("ACCESS_KEY")
ADMIN_PERMISSION_KEY = os.getenv("ADMIN_PERMISSION_KEY")
MEDICO_PERMISSION_KEY = os.getenv("MEDICO_PERMISSION_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([ACCESS_KEY, ADMIN_PERMISSION_KEY, MEDICO_PERMISSION_KEY, DATABASE_URL, ENCRYPTION_KEY]):
    raise Exception("Faltan variables en el .env")

cipher = Fernet(ENCRYPTION_KEY.encode())

app = FastAPI(title="API Gestión Clínica")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiadas solicitudes. Intenta más tarde."},
    )

# =============================
# RATE LIMIT
# =============================

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Demasiadas solicitudes. Intenta más tarde."},
    )

# =============================
# DB
# =============================

def get_db_connection():
    return psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)

def create_tables():
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id VARCHAR(50) PRIMARY KEY,
                family_name VARCHAR(100) NOT NULL,
                given_name VARCHAR(100) NOT NULL,
                gender VARCHAR(10) NOT NULL CHECK (gender IN ('male','female','other')),
                birth_date DATE NOT NULL,
                medical_summary TEXT,
                patient_key VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id SERIAL PRIMARY KEY,
                patient_id VARCHAR(50) REFERENCES patients(id) ON DELETE CASCADE,
                code VARCHAR(100) NOT NULL,
                value NUMERIC NOT NULL,
                unit VARCHAR(50),
                is_abnormal BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

@app.on_event("startup")
def startup():
    create_tables()

# =============================
# SEGURIDAD
# =============================

def verify_access_key(x_access_key: str = Header(...)):
    if x_access_key != ACCESS_KEY:
        raise HTTPException(401, "Access-Key inválida")

def get_user(x_permission_key: str = Header(...)):

    if x_permission_key == ADMIN_PERMISSION_KEY:
        return {"role": "admin", "patient_id": None}

    if x_permission_key == MEDICO_PERMISSION_KEY:
        return {"role": "medico", "patient_id": None}

    # buscar paciente
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM patients
            WHERE patient_key=%s
        """, (x_permission_key,))
        patient = cur.fetchone()

        if patient:
            return {
                "role": "paciente",
                "patient_id": patient["id"]
            }

    raise HTTPException(403, "Permission Key inválida")

# =============================
# ENCRIPTACION
# =============================

def encrypt(text: str):
    return cipher.encrypt(text.encode()).decode()

def decrypt(text: str):
    return cipher.decrypt(text.encode()).decode()

# =============================
# RANGOS ANORMALES
# =============================
def evaluate_abnormal(code: str, value: float) -> bool:

    normal_ranges = {
        "heart_rate": (60, 100),
        "temperature": (36, 37.5),
        "glucose": (70, 140),
        "platelets": (150000, 450000),
        "systolic_pressure": (90, 120),
        "diastolic_pressure": (60, 80)
    }

    if code in normal_ranges:
        min_val, max_val = normal_ranges[code]
        return value < min_val or value > max_val

    return False

# =============================
# MODELOS
# =============================

class Patient(BaseModel):
    id: str
    family_name: str
    given_name: str
    gender: str
    birthDate: str
    medical_summary: str
    patient_key: str

class Observation(BaseModel):
    patient_id: str
    code: str
    value: float
    unit: Optional[str] = None

# ===============================================
# ROOT
# ===============================================

@app.get("/")
def root():
    return {"api": "API Gestión Clínica", "status": "running"}

# =========================================================
# PATIENT
# =========================================================

# -----------------------------------------------
# CREATE PATIENT (Admin y Médico)
# -----------------------------------------------
@app.post("/fhir/Patient",
          dependencies=[Depends(verify_access_key)])
def create_patient(patient: Patient,
                   user=Depends(get_user)):

    if user["role"] not in ["admin", "medico"]:
        raise HTTPException(403, "No autorizado para crear pacientes")

    encrypted_summary = encrypt(patient.medical_summary)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patients
            (id, family_name, given_name, gender, birth_date,
             medical_summary, patient_key)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (patient.id,
              patient.family_name,
              patient.given_name,
              patient.gender,
              patient.birthDate,
              encrypted_summary,
              patient.patient_key))

    return {"mensaje": "Paciente creado correctamente"}


# -----------------------------------------------
# GET TODOS LOS PACIENTES (Paginado)
# -----------------------------------------------
@app.get("/fhir/Patient",
         dependencies=[Depends(verify_access_key)])
@limiter.limit("30/minute")
def get_patients(request: Request,
                 user=Depends(get_user),
                 limit: int = 10,
                 offset: int = 0):

    with get_db_connection() as conn:
        cur = conn.cursor()

        if user["role"] == "paciente":
            cur.execute("""
                SELECT * FROM patients
                WHERE id=%s
                LIMIT %s OFFSET %s
            """, (user["patient_id"], limit, offset))

        else:
            cur.execute("""
                SELECT * FROM patients
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

        data = cur.fetchall()

        # Comportamiento por rol
        if user["role"] == "admin":
            result = []
            for p in data:
                result.append({
                    "id": p["id"],
                    "serialized_data": encrypt(
                        f"{p['family_name']}|{p['given_name']}|{p['gender']}|{p['birth_date']}"
                    )
                })
            return {"limit": limit, "offset": offset, "data": result}

        else:
            for p in data:
                if p["medical_summary"]:
                    p["medical_summary"] = decrypt(p["medical_summary"])
            return {"limit": limit, "offset": offset, "data": data}


# -----------------------------------------------
# GET PACIENTE INDIVIDUAL
# -----------------------------------------------
@app.get("/fhir/Patient/{patient_id}",
         dependencies=[Depends(verify_access_key)])
def get_patient(patient_id: str,
                user=Depends(get_user)):

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients WHERE id=%s", (patient_id,))
        patient = cur.fetchone()

        if not patient:
            raise HTTPException(404, "Paciente no encontrado")

        if user["role"] == "paciente" and user["patient_id"] != patient_id:
            raise HTTPException(403, "Solo puede ver su propia información")

        if patient["medical_summary"]:
            patient["medical_summary"] = decrypt(patient["medical_summary"])

    return patient


# -----------------------------------------------
# PUT PACIENTE (Solo Admin)
# -----------------------------------------------
@app.put("/fhir/Patient/{patient_id}",
         dependencies=[Depends(verify_access_key)])
def update_patient(patient_id: str,
                   updated: Patient,
                   user=Depends(get_user)):

    # SOLO ADMIN
    if user["role"] != "admin":
        raise HTTPException(status_code=403,
                            detail="Solo el administrador puede editar pacientes")

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
                    UPDATE patients
                    SET family_name=%s,
                        given_name=%s,
                        gender=%s,
                        birth_date=%s,
                        medical_summary=%s,
                        patient_key=%s
                    WHERE id=%s
                """, (
                    updated.family_name,
                    updated.given_name,
                    updated.gender,
                    updated.birthDate,
                    encrypt(updated.medical_summary) if updated.medical_summary else None,
                    updated.patient_key,
                    patient_id
                ))

        if cur.rowcount == 0:
            raise HTTPException(status_code=404,
                                detail="Paciente no encontrado")

    return {"mensaje": "Paciente actualizado correctamente"}


# -----------------------------------------------
# DELETE PACIENTE (Solo Admin)
# -----------------------------------------------
@app.delete("/fhir/Patient/{patient_id}",
            dependencies=[Depends(verify_access_key)])
def delete_patient(patient_id: str,
                   user=Depends(get_user)):

    if user["role"] != "admin":
        raise HTTPException(403, "Solo admin puede borrar pacientes")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM patients WHERE id=%s", (patient_id,))

        if cur.rowcount == 0:
            raise HTTPException(404, "Paciente no encontrado")

    return {"mensaje": "Paciente eliminado correctamente"}


# =========================================================
# OBSERVATION
# =========================================================

# -----------------------------------------------
# CREATE OBSERVATION (Admin y Médico)
# -----------------------------------------------
@app.post("/fhir/Observation",
          dependencies=[Depends(verify_access_key)])
def create_observation(observation: Observation,
                       user=Depends(get_user)):

    if user["role"] not in ["admin", "medico"]:
        raise HTTPException(403, "No autorizado")

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("SELECT id FROM patients WHERE id=%s",
                    (observation.patient_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Paciente no encontrado")

        # evaluar anormalidad
        is_abnormal = evaluate_abnormal(observation.code,
                                        observation.value)

        cur.execute("""
            INSERT INTO observations
            (patient_id, code, value, unit, is_abnormal)
            VALUES (%s,%s,%s,%s,%s)
        """, (observation.patient_id,
              observation.code,
              observation.value,
              observation.unit,
              is_abnormal))

    return {"mensaje": "Observación registrada"}

# -----------------------------------------------
# GET OBSERVACIONES (Paginado)
# -----------------------------------------------
@app.get("/fhir/Observation",
         dependencies=[Depends(verify_access_key)])
@limiter.limit("30/minute")
def get_observations(request: Request,
                     user=Depends(get_user),
                     limit: int = 10,
                     offset: int = 0):

    with get_db_connection() as conn:
        cur = conn.cursor()

        # ADMIN → SOLO VE CONTEO
        if user["role"] == "admin":

            cur.execute("""
                SELECT patient_id, COUNT(*) as total
                FROM observations
                GROUP BY patient_id
            """)

            data = cur.fetchall()
            return {"data": data}

        # PACIENTE → SOLO SUS OBSERVACIONES
        if user["role"] == "paciente":
            cur.execute("""
                SELECT * FROM observations
                WHERE patient_id=%s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (user["patient_id"], limit, offset))

        # MÉDICO → TODAS
        else:
            cur.execute("""
                SELECT * FROM observations
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))

        data = cur.fetchall()

        # ALERTAS SOLO PARA MÉDICO
        if user["role"] == "medico":

            alerts = []

            for obs in data:

                # Alerta por valor anormal individual
                if obs.get("is_abnormal"):
                    alerts.append({
                        "type": "valor_anormal",
                        "observation_id": obs["id"],
                        "patient_id": obs["patient_id"],
                        "code": obs["code"],
                        "value": float(obs["value"]),
                        "message": "Valor fuera de rango normal"
                    })

                # Alerta simple de tendencia (últimos 5 del mismo tipo)
                cur.execute("""
                    SELECT value
                    FROM observations
                    WHERE patient_id=%s AND code=%s
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (obs["patient_id"], obs["code"]))

                last_values = cur.fetchall()

                if len(last_values) == 5:
                    values = [float(v["value"]) for v in last_values]

                    # tendencia ascendente continua
                    if values == sorted(values) and len(set(values)) > 1:
                        alerts.append({
                            "type": "tendencia_ascendente",
                            "patient_id": obs["patient_id"],
                            "code": obs["code"],
                            "message": "Tendencia ascendente detectada"
                        })

                    # tendencia descendente continua
                    if values == sorted(values, reverse=True) and len(set(values)) > 1:
                        alerts.append({
                            "type": "tendencia_descendente",
                            "patient_id": obs["patient_id"],
                            "code": obs["code"],
                            "message": "Tendencia descendente detectada"
                        })

            return {
                "limit": limit,
                "offset": offset,
                "data": data,
                "alerts": alerts
            }

        # PACIENTE → OCULTAR BANDERA CLÍNICA
        else:
            for obs in data:
                obs.pop("is_abnormal", None)

            return {
                "limit": limit,
                "offset": offset,
                "data": data
            }

# -----------------------------------------------
# GET OBSERVACION POR ID
# -----------------------------------------------
@app.get("/fhir/Observation/{observation_id}",
         dependencies=[Depends(verify_access_key)])
def get_observation_by_id(observation_id: int,
                          user=Depends(get_user)):

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM observations WHERE id=%s",
                    (observation_id,))
        obs = cur.fetchone()

        if not obs:
            raise HTTPException(404, "Observación no encontrada")

        if user["role"] == "paciente" and obs["patient_id"] != user["patient_id"]:
            raise HTTPException(403, "Solo puede ver sus propias observaciones")

    return obs

# -----------------------------------------------
# PUT OBSERVACION (Solo Admin)
# -----------------------------------------------
@app.put("/fhir/Observation/{observation_id}",
         dependencies=[Depends(verify_access_key)])
def update_observation(observation_id: int,
                       updated: Observation,
                       user=Depends(get_user)):

    if user["role"] not in ["admin", "medico"]:
        raise HTTPException(403, "No autorizado")

    # recalcular anormalidad
    is_abnormal = evaluate_abnormal(updated.code,
                                    updated.value)

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            UPDATE observations
            SET code=%s,
                value=%s,
                unit=%s,
                is_abnormal=%s
            WHERE id=%s
        """, (updated.code,
              updated.value,
              updated.unit,
              is_abnormal,
              observation_id))

        if cur.rowcount == 0:
            raise HTTPException(404, "Observación no encontrada")

    return {"mensaje": "Observación actualizada"}

# -----------------------------------------------
# DELETE OBSERVACION (Solo Admin)
# -----------------------------------------------
@app.delete("/fhir/Observation/{observation_id}",
            dependencies=[Depends(verify_access_key)])
def delete_observation(observation_id: int,
                       user=Depends(get_user)):

    if user["role"] not in ["admin", "medico"]:
        raise HTTPException(403, "No autorizado")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM observations WHERE id=%s",
                    (observation_id,))

        if cur.rowcount == 0:
            raise HTTPException(404, "Observación no encontrada")

    return {"mensaje": "Observación eliminada"}

