
from pydantic import BaseModel, Field


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step.")
    branch: str = Field(..., description="Il branch da aggiornare.")
