
📝 Paso 2: Crear server.py
Donde dice "Name your file..." escribe: server.py

En el cuadro grande de abajo, copia y pega TODO este código:

from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', os.environ.get('MONGODB_URL', 'mongodb://localhost:27017'))
db_name = os.environ.get('DB_NAME', 'consolidacion_db')

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

app = FastAPI(title="Consolidación API")
api_router = APIRouter(prefix="/api")

def serialize_doc(doc):
    if doc:
        doc['id'] = str(doc['_id'])
        del doc['_id']
    return doc

class PersonaCreate(BaseModel):
    nombres: str = Field(..., min_length=1, max_length=100)
    apellidos: str = Field(..., min_length=1, max_length=100)
    edad: int = Field(..., ge=0, le=150)
    telefono: str = Field(..., min_length=1, max_length=20)
    invitado_por: str = Field(default="", max_length=200)

class PersonaUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    edad: Optional[int] = None
    telefono: Optional[str] = None
    invitado_por: Optional[str] = None

class PersonaResponse(BaseModel):
    id: str
    numero: int
    nombres: str
    apellidos: str
    edad: int
    telefono: str
    invitado_por: str
    fecha_creacion: datetime

class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]
    total: int

@api_router.get("/")
async def root():
    return {"message": "Consolidación API"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy"}

@api_router.post("/personas", response_model=PersonaResponse)
async def create_persona(persona: PersonaCreate):
    count = await db.personas.count_documents({})
    persona_dict = persona.dict()
    persona_dict['numero'] = count + 1
    persona_dict['fecha_creacion'] = datetime.utcnow()
    result = await db.personas.insert_one(persona_dict)
    created = await db.personas.find_one({"_id": result.inserted_id})
    return serialize_doc(created)

@api_router.get("/personas", response_model=PersonaListResponse)
async def get_personas(
    buscar: Optional[str] = None,
    ordenar_por: Optional[str] = "reciente",
    orden: Optional[str] = "desc"
):
    query = {}
    if buscar:
        search_regex = {"$regex": buscar, "$options": "i"}
        query["$or"] = [{"nombres": search_regex}, {"apellidos": search_regex}, {"telefono": search_regex}]
    
    sort_direction = 1 if orden == "asc" else -1
    sort_field = {"edad": "edad", "invitado_por": "invitado_por", "numero": "numero"}.get(ordenar_por, "fecha_creacion")
    
    cursor = db.personas.find(query).sort(sort_field, sort_direction)
    personas = await cursor.to_list(1000)
    return {"personas": [serialize_doc(p) for p in personas], "total": len(personas)}

@api_router.put("/personas/{persona_id}", response_model=PersonaResponse)
async def update_persona(persona_id: str, persona: PersonaUpdate):
    try:
        obj_id = ObjectId(persona_id)
    except:
        raise HTTPException(status_code=400, detail="ID inválido")
    
    update_data = {k: v for k, v in persona.dict().items() if v is not None}
    if update_data:
        await db.personas.update_one({"_id": obj_id}, {"$set": update_data})
    
    updated = await db.personas.find_one({"_id": obj_id})
    if not updated:
        raise HTTPException(status_code=404, detail="No encontrada")
    return serialize_doc(updated)

@api_router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str):
    try:
        obj_id = ObjectId(persona_id)
    except:
        raise HTTPException(status_code=400, detail="ID inválido")
    
    result = await db.personas.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No encontrada")
    return {"message": "Eliminada"}

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

logging.basicConfig(level=logging.INFO)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
