from fastapi import FastAPI

from app.review.router import router as review_router


app = FastAPI(title="Quality Inspection", version="0.1.0")
app.include_router(review_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app_name": "quality-inspection"}
