import uvicorn
from fastapi import FastAPI

app = FastAPI(title="flubpub")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/pages")
def create_page():
    return {"status": "todo"}


@app.get("/api/pages")
def list_pages():
    return {"status": "todo"}


if __name__ == "__main__":
    uvicorn.run("flubpub.server:app", host="0.0.0.0", port=8000, reload=True)
