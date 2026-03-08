# 🏥 Sistema de Gestión Clínica

API REST con protocolo FHIR-Lite y dashboard interactivo para la gestión de pacientes y observaciones clínicas. Implementa autenticación de doble llave, encriptación de datos sensibles y control de acceso por roles.

---

## 👥 Integrantes del Equipo

| Nombre |
|--------|
| Camilo Jose Delgado |
| David Melo Valbuena |
| Miguel Angel Ruales |

---

## 🌐 Despliegue Activo

| Servicio | URL |
|----------|-----|
| **Backend (API)** | https://gestion-clinica-backend-b7w6.onrender.com |
| **Frontend (Dashboard)** | https://gestion-clinica-dashboard.onrender.com |

> ⚠️ El plan gratuito de Render apaga los servicios tras 15 minutos de inactividad. Si la página no carga de inmediato, espera 30 segundos y recarga.

---

## 🔑 Credenciales de Prueba

Para probar el sistema usa las siguientes credenciales en el dashboard:

| Campo | Valor |
|-------|-------|
| **Access Key** | `gestion_clinica_key` |

| Rol | Permission Key |
|-----|---------------|
| **Admin** | `admin_rol_2026` |
| **Médico** | `medico_rol_2026` |
| **Paciente** | `juan_key_123` |

> 💡 La **Patient Key** es generada al momento de crear un paciente desde el dashboard. `juan_key_123` corresponde a un paciente ya registrado en el sistema para fines de prueba.

---

## 📁 Estructura del Repositorio

```
gestion-clinica/
├── backend/
│   ├── main.py               # API FastAPI
│   ├── requirements.txt      # Dependencias del backend
├── frontend/
│   ├── dashboard.py          # Dashboard Streamlit
│   └── requirements.txt      # Dependencias del frontend
└── .gitignore
└── README.md
```

---

## 🚀 Despliegue en Render

> 🛠️ El despliegue de este proyecto se realizó en [Render](https://render.com) usando dos servicios independientes (backend y frontend) conectados al mismo repositorio de GitHub. Si deseas replicarlo, sigue los pasos a continuación — solo necesitas una cuenta en Render y el repositorio forkeado.

### Paso 1 — Base de Datos PostgreSQL

1. En Render → **New** → **PostgreSQL**
2. Asigna un nombre, ej: `gestion-clinica-db`
3. Una vez creada, copia el **Internal Database URL** para usarlo como `DATABASE_URL`

---

### Paso 2 — Backend

1. En Render → **New** → **Web Service**
2. Conecta tu repositorio de GitHub
3. Configura los siguientes campos:

| Campo | Valor |
|-------|-------|
| **Root Directory** | `backend` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port 10000` |

4. En la pestaña **Environment**, agrega estas variables:

| Variable | Descripción |
|----------|-------------|
| `ACCESS_KEY` | Token de entrada requerido en todas las peticiones |
| `ADMIN_PERMISSION_KEY` | Clave de acceso para el rol Admin |
| `MEDICO_PERMISSION_KEY` | Clave de acceso para el rol Médico |
| `DATABASE_URL` | URL de conexión a PostgreSQL (Internal URL de Render) |
| `ENCRYPTION_KEY` | Clave Fernet para encriptar datos sensibles |

> **¿Cómo generar una ENCRYPTION_KEY válida?**
> ```python
> from cryptography.fernet import Fernet
> print(Fernet.generate_key().decode())
> ```

5. Haz clic en **Deploy** y espera a que el servicio esté activo
6. Copia la URL del backend, ej: `https://gestion-clinica-backend.onrender.com`

---

### Paso 3 — Frontend

1. En Render → **New** → **Web Service**
2. Conecta el **mismo repositorio** de GitHub
3. Configura los siguientes campos:

| Campo | Valor |
|-------|-------|
| **Root Directory** | `frontend` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `streamlit run dashboard.py --server.port 10000 --server.address 0.0.0.0` |

4. Asegúrate de que `API_URL` en `dashboard.py` apunte al backend desplegado:
```python
API_URL = "https://gestion-clinica-backend.onrender.com"
```

5. Haz clic en **Deploy**
6. El dashboard estará disponible en la URL asignada por Render

---

## 🔐 Credenciales de Acceso

| Rol | Header | Valor |
|-----|--------|-------|
| **Admin** | `x-permission-key` | Valor de `ADMIN_PERMISSION_KEY` |
| **Médico** | `x-permission-key` | Valor de `MEDICO_PERMISSION_KEY` |
| **Paciente** | `x-permission-key` | `patient_key` asignada al crear el paciente |

Todos los roles requieren además el header `x-access-key` con el valor de `ACCESS_KEY`.