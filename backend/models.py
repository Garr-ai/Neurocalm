"""
Pydantic models for API requests/responses
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class EventCreate(BaseModel):
    mode: str  # meeting, study, lecture, background
    focus_score: float
    load_score: float
    anomaly_score: float
    context: Dict  # { tab, url, calendar_event_id }
    user_id: Optional[str] = "default"

class EventResponse(BaseModel):
    id: int
    timestamp: datetime
    mode: str
    focus_score: float
    load_score: float
    anomaly_score: float
    context: Dict
    user_id: str
    
    class Config:
        from_attributes = True

# Firebase models
class FirebaseInsertRequest(BaseModel):
    """Flexible model for inserting any data into Firebase"""
    collection: str
    data: Dict[str, Any]
    document_id: Optional[str] = None
    use_timestamp: bool = True

class FirebaseUpdateRequest(BaseModel):
    """Model for updating Firebase documents"""
    collection: str
    document_id: str
    data: Dict[str, Any]
    merge: bool = True

class FirebaseQueryRequest(BaseModel):
    """Model for querying Firebase collections"""
    collection: str
    filters: Optional[List[Dict[str, Any]]] = None  # [{"field": "user_id", "operator": "==", "value": "user123"}]
    limit: Optional[int] = None
    order_by: Optional[str] = None

class FirebaseResponse(BaseModel):
    """Generic Firebase response"""
    success: bool
    document_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None



