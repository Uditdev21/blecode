from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import get_settings
from database import DatabaseManager, get_db
from schemas import (
    DeleteResponse,
    ErrorResponse,
    RecordResponse,
    ServiceInfoResponse,
    SyncResponse,
)
from security import verify_api_token

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    yield
    db = get_db()
    db.close()


app = FastAPI(
    title="Tronn Data Sync API",
    description=(
        "### Enterprise Data Ingestion & Sync Service\n"
        "**Developed by Tronn**\n\n"
        "Authenticate all data endpoints by passing the API key in the **`token`** request header."
    ),
    version=settings.APP_VERSION,
    contact={
        "name": "Tronn Support & Engineering",
        "url": "https://tronn.io",
    },
    license_info={
        "name": "Proprietary - Developed by Tronn",
    },
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/",
    response_model=ServiceInfoResponse,
    tags=["Product Info"],
    summary="Tronn API Overview & Status",
)
def root():
    """Returns service overview, version, developer attribution, and documentation links."""
    return ServiceInfoResponse(
        status="healthy",
        service=settings.APP_NAME,
        developer=settings.DEVELOPER,
        version=settings.APP_VERSION,
        docs_url="/docs",
        endpoints={
            "post_data": "POST /api/v1/data [Protected: requires 'token' header]",
            "get_latest": "GET /api/v1/data/latest [Protected: requires 'token' header]",
            "get_sync_or_pluck": "GET /api/v1/data/sync [Protected: requires 'token' header]",
            "get_by_id": "GET /api/v1/data/{doc_id} [Protected: requires 'token' header]",
            "delete_by_id": "DELETE /api/v1/data/{doc_id} [Protected: requires 'token' header]",
            "delete_all": "DELETE /api/v1/data [Protected: requires 'token' header]",
            "export_db_file": "GET /api/v1/data/export [Protected: requires 'token' header]",
            "health_check": "GET /health [Public]",
        },
    )


@app.get("/health", tags=["Health"], summary="Health Check")
def health_check():
    """Public health check endpoint."""
    return {"status": "ok", "developer": "Tronn"}


@app.post(
    "/api/v1/data",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Data Operations"],
    summary="Save payload to database",
    dependencies=[Depends(verify_api_token)],
)
@app.post(
    "/data",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
def save_payload(
    payload: Dict[str, Any],
    db: DatabaseManager = Depends(get_db),
):
    """
    Saves an arbitrary JSON payload into TinyDB.
    Automatically assigns an integer `id` and ISO UTC `created_at` timestamp.
    Requires header: `token: <API_KEY>`
    """
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be a valid JSON object.",
        )
    saved_record = db.insert_record(payload)
    return RecordResponse(status="success", developer="Tronn", data=saved_record)


@app.get(
    "/api/v1/data/latest",
    response_model=RecordResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "No data found"},
    },
    tags=["Data Operations"],
    summary="Get latest record",
    dependencies=[Depends(verify_api_token)],
)
@app.get(
    "/data/latest",
    response_model=RecordResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
def get_latest_data(db: DatabaseManager = Depends(get_db)):
    """
    Retrieves the most recently recorded document.
    Requires header: `token: <API_KEY>`
    """
    latest = db.get_latest()
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No data records found in the database.",
        )
    return RecordResponse(status="success", developer="Tronn", data=latest)


@app.get(
    "/api/v1/data/export",
    tags=["Database Export"],
    summary="Download full database file",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Full TinyDB JSON file download",
            "content": {"application/json": {}},
        },
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Database file not found"},
    },
    dependencies=[Depends(verify_api_token)],
)
@app.get(
    "/data/export",
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
@app.get(
    "/api/v1/data/db/file",
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
def export_full_db_file(db: DatabaseManager = Depends(get_db)):
    """
    Sends the entire raw TinyDB database file (`db.json`) back as a downloadable JSON file.
    Requires header: `token: <API_KEY>`
    """
    db_file = db.get_db_file_path()
    if not db_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database file does not exist yet.",
        )

    return FileResponse(
        path=str(db_file),
        filename="tronn_db.json",
        media_type="application/json",
    )


@app.get(
    "/api/v1/data/sync",
    response_model=SyncResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
    tags=["Data Operations"],
    summary="Sync or pluck bulk data",
    dependencies=[Depends(verify_api_token)],
)
@app.get(
    "/data/sync",
    response_model=SyncResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
@app.get(
    "/api/v1/data",
    response_model=SyncResponse,
    tags=["Data Operations"],
    summary="Bulk data retrieval (Alias for sync)",
    dependencies=[Depends(verify_api_token)],
)
def sync_or_pluck_data(
    since: Optional[datetime] = Query(
        None,
        description="Filter records created at or after this ISO timestamp (e.g. 2026-08-24T00:00:00Z)",
    ),
    after_id: Optional[int] = Query(
        None,
        description="Cursor-based sync: fetch records strictly with ID greater than this value",
    ),
    ids: Optional[str] = Query(
        None,
        description="Comma-separated IDs to pluck specific records (e.g. '1,2,5')",
    ),
    fields: Optional[str] = Query(
        None,
        description="Comma-separated field names to pluck from records (e.g. 'id,sensor,temperature')",
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=1000,
        description="Pagination limit: maximum records to return",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Pagination offset: number of records to skip",
    ),
    db: DatabaseManager = Depends(get_db),
):
    """
    Synchronizes records or plucks targeted data.
    - **since**: Time-window sync (`created_at >= since`).
    - **after_id**: Incremental sync cursor (`id > after_id`).
    - **ids**: Pluck specific record IDs.
    - **fields**: Pluck specific fields/keys only.
    - **limit & offset**: Pagination controls.
    Requires header: `token: <API_KEY>`
    """
    parsed_ids = None
    if ids is not None and ids.strip():
        try:
            parsed_ids = [int(i.strip()) for i in ids.split(",") if i.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'ids' must be a comma-separated list of integers.",
            )

    parsed_fields = None
    if fields is not None and fields.strip():
        parsed_fields = [f.strip() for f in fields.split(",") if f.strip()]

    records, total = db.sync_records(
        since=since,
        after_id=after_id,
        ids=parsed_ids,
        fields=parsed_fields,
        limit=limit,
        offset=offset,
    )

    return SyncResponse(
        status="success",
        developer="Tronn",
        count=len(records),
        total=total,
        data=records,
    )


@app.get(
    "/api/v1/data/{doc_id}",
    response_model=RecordResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Record not found"},
    },
    tags=["Data Operations"],
    summary="Get record by ID",
    dependencies=[Depends(verify_api_token)],
)
def get_record_by_id(
    doc_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """
    Retrieves a single record by its integer document ID.
    Requires header: `token: <API_KEY>`
    """
    record = db.get_by_id(doc_id=doc_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record with ID {doc_id} not found.",
        )
    return RecordResponse(status="success", developer="Tronn", data=record)


@app.delete(
    "/api/v1/data/{doc_id}",
    response_model=DeleteResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Record not found"},
    },
    tags=["Data Operations"],
    summary="Delete record by ID",
    dependencies=[Depends(verify_api_token)],
)
@app.delete(
    "/data/{doc_id}",
    response_model=DeleteResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
def delete_record_by_id(
    doc_id: int,
    db: DatabaseManager = Depends(get_db),
):
    """
    Deletes a single record by its integer document ID.
    Requires header: `token: <API_KEY>`
    """
    deleted = db.delete_by_id(doc_id=doc_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record with ID {doc_id} not found.",
        )
    return DeleteResponse(
        status="success",
        developer="Tronn",
        message=f"Record with ID {doc_id} deleted successfully.",
        deleted_count=1,
    )


@app.delete(
    "/api/v1/data",
    response_model=DeleteResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
    tags=["Data Operations"],
    summary="Delete all records / Purge database",
    dependencies=[Depends(verify_api_token)],
)
@app.delete(
    "/data",
    response_model=DeleteResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_api_token)],
)
def delete_all_records(
    db: DatabaseManager = Depends(get_db),
):
    """
    Deletes all records from the database table.
    Requires header: `token: <API_KEY>`
    """
    count = db.delete_all()
    return DeleteResponse(
        status="success",
        developer="Tronn",
        message=f"Successfully purged all records. Total deleted: {count}.",
        deleted_count=count,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
