# Tronn Data Sync API

> **Developed by Tronn**  
> Enterprise-grade JSON payload ingestion, latest state retrieval, sync/pluck data engine, and database backup/export powered by FastAPI & TinyDB.

---

## ⚡ Key Capabilities

- **Arbitrary JSON Ingestion (`POST /api/v1/data`)**: Ingest any JSON payload with automatic UTC ISO timestamps and unique incremental doc IDs.
- **Latest State Fetch (`GET /api/v1/data/latest`)**: Instantly fetch the single most recent record.
- **Data Sync & Pluck (`GET /api/v1/data/sync`)**:
  - **Cursor-based sync**: `?after_id=10` (efficient incremental sync).
  - **Time-range sync**: `?since=2026-08-24T00:00:00Z`.
  - **Field plucking**: `?fields=id,device_id,temperature` (returns only requested keys).
  - **Target ID plucking**: `?ids=1,5,9`.
  - **Pagination**: `?limit=50&offset=0`.
- **Delete Operations (`DELETE /api/v1/data/{id}` & `DELETE /api/v1/data`)**: Delete a specific record by ID or purge/clear all records.
- **Full Database Export (`GET /api/v1/data/export`)**: Download the complete raw TinyDB JSON database file.
- **Security**: Authentication enforced on all data and export endpoints via header: `token: <API_KEY>`.
- **Interactive Swagger Documentation**: Available at `http://localhost:8000/docs` with built-in Authorize padlock.

---

## 🔐 Environment Configuration (`.env`)

Configure your environment settings in `.env` (or copy from `.env.example`):

```ini
# Tronn API Environment Configuration

# API Key used in request header: `token: <API_KEY>`
API_KEY=tronn_sec_token_889900

# Application Details
APP_NAME=Tronn Data Sync API
APP_VERSION=1.0.0
DEVELOPER=Tronn
ENVIRONMENT=development

# Database Storage Path
DB_PATH=data/db.json
```

---

## 🚀 Getting Started

### 1. Activate Environment & Install Dependencies
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Start the Server

You can run the server locally or using Docker:

#### Option A: Using Docker Compose (Recommended for Containerized Run)
```powershell
# Build and run container in detached mode
docker compose up -d --build

# View real-time logs
docker compose logs -f

# Stop the container
docker compose down
```

#### Option B: Using Plain Docker
```powershell
# Build image
docker build -t tronn-api .

# Run container with volume mount and env file
docker run -d -p 8000:8000 --env-file .env -v "${PWD}/data:/app/data" --name tronn_data_sync_api tronn-api
```

#### Option C: FastAPI CLI (Local)
```powershell
fastapi dev main.py
```

#### Option D: Direct Python script (Local)
```powershell
python main.py
```

#### Option E: Uvicorn (Local)
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

### 3. Run the BLE Scanner (`test.py`)

You can run the Bluetooth scanner in three ways:

#### Option A: Direct Python Execution
```powershell
python test.py
```

#### Option B: Docker Scanner Container
```bash
# Build scanner image
docker build -f Dockerfile.scanner -t tronn-ble-scanner .

# Run scanner with host Bluetooth and D-Bus access (Linux)
docker run -d --name tronn_ble_scanner --network host --privileged -v /var/run/dbus:/var/run/dbus tronn-ble-scanner
```

#### Option C: Linux Systemd Service (`tronn-ble-scanner.service`)
```bash
# 1. Copy service file
sudo cp tronn-ble-scanner.service /etc/systemd/system/

# 2. Reload daemon and enable on boot
sudo systemctl daemon-reload
sudo systemctl enable tronn-ble-scanner

# 3. Start the service
sudo systemctl start tronn-ble-scanner

# 4. Check service status / logs
sudo systemctl status tronn-ble-scanner
journalctl -u tronn-ble-scanner -f
```



---

## 📡 API Reference & Examples

### Authentication
All data endpoints require the `token` header:
```http
token: tronn_sec_token_889900
```

---

### 1. Ingest Payload (`POST /api/v1/data`)
- **Headers**: `token: <API_KEY>`, `Content-Type: application/json`
- **Request**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/data" \
       -H "token: tronn_sec_token_889900" \
       -H "Content-Type: application/json" \
       -d '{"device": "tronn-sensor-alpha", "temperature": 24.8, "status": "active"}'
  ```
- **Response (`201 Created`)**:
  ```json
  {
    "status": "success",
    "developer": "Tronn",
    "data": {
      "device": "tronn-sensor-alpha",
      "temperature": 24.8,
      "status": "active",
      "created_at": "2026-08-24T17:45:00.123456+00:00",
      "id": 1
    }
  }
  ```

---

### 2. Get Latest Data (`GET /api/v1/data/latest`)
- **Request**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/latest" \
       -H "token: tronn_sec_token_889900"
  ```
- **Response (`200 OK`)**:
  ```json
  {
    "status": "success",
    "developer": "Tronn",
    "data": {
      "id": 1,
      "device": "tronn-sensor-alpha",
      "temperature": 24.8,
      "status": "active",
      "created_at": "2026-08-24T17:45:00.123456+00:00"
    }
  }
  ```

---

### 3. Sync or Pluck Data (`GET /api/v1/data/sync`)

- **Bulk Fetch All**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/sync" \
       -H "token: tronn_sec_token_889900"
  ```

- **Incremental Sync (`after_id`)**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/sync?after_id=5" \
       -H "token: tronn_sec_token_889900"
  ```

- **Pluck Specific Fields**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/sync?fields=id,device,status" \
       -H "token: tronn_sec_token_889900"
  ```

- **Pluck Specific IDs**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/sync?ids=1,3,7" \
       -H "token: tronn_sec_token_889900"
  ```

---

### 4. Delete Data (`DELETE /api/v1/data/{id}` & `DELETE /api/v1/data`)

- **Delete Single Record by ID**:
  ```bash
  curl -X DELETE "http://localhost:8000/api/v1/data/1" \
       -H "token: tronn_sec_token_889900"
  ```
  **Response (`200 OK`)**:
  ```json
  {
    "status": "success",
    "developer": "Tronn",
    "message": "Record with ID 1 deleted successfully.",
    "deleted_count": 1
  }
  ```

- **Purge / Delete All Records**:
  ```bash
  curl -X DELETE "http://localhost:8000/api/v1/data" \
       -H "token: tronn_sec_token_889900"
  ```
  **Response (`200 OK`)**:
  ```json
  {
    "status": "success",
    "developer": "Tronn",
    "message": "Successfully purged all records. Total deleted: 15.",
    "deleted_count": 15
  }
  ```

---

### 5. Download Full Database File (`GET /api/v1/data/export`)

- **Download Full DB**:
  ```bash
  curl -X GET "http://localhost:8000/api/v1/data/export" \
       -H "token: tronn_sec_token_889900" \
       -o tronn_db_backup.json
  ```
  *Streams the raw TinyDB database file directly.*

---

### 6. Product Overview & Health (Public)
- **`GET /`**: Overview and developer information.
- **`GET /health`**: Health status check.

---

## 🧪 Automated Testing

Run the full pytest suite:
```bash
.\venv\Scripts\python.exe -m pytest test_api.py -v
```
