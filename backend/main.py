from fastapi import FastAPI

app = FastAPI(
    title="Diagno-Pilot API",
    description="API d'aide au diagnostic des maladies infectieuses et à la prescription antibiotique",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
