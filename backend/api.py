"""
FastAPI REST API for NeuroCalm
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from backend.database import get_db, init_db, Event
from backend.models import (
    EventCreate, EventResponse,
    FirebaseInsertRequest, FirebaseUpdateRequest, FirebaseQueryRequest, FirebaseResponse
)
from backend.firebase_service import FirebaseService

app = FastAPI(title="NeuroCalm API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and Firebase on startup
@app.on_event("startup")
def startup_event():
    init_db()
    # Initialize Firebase (will print warnings if credentials not found)
    try:
        firebase_service = FirebaseService.get_instance()
        if firebase_service.is_available():
            print("✅ Firebase is available and ready")
        else:
            print("⚠️  Firebase is not available. Set FIREBASE_SERVICE_ACCOUNT_KEY or FIREBASE_SERVICE_ACCOUNT_JSON")
    except Exception as e:
        print(f"⚠️  Firebase initialization error: {e}")

@app.get("/")
def root():
    return {"message": "NeuroCalm API", "version": "1.0.0"}

@app.post("/events", response_model=EventResponse)
def create_event(event: EventCreate, db: Session = Depends(get_db), sync_firebase: bool = True):
    """Create a new event (optionally syncs to Firebase if available)"""
    db_event = Event(
        timestamp=datetime.utcnow(),
        mode=event.mode,
        focus_score=event.focus_score,
        load_score=event.load_score,
        anomaly_score=event.anomaly_score,
        context=event.context,
        user_id=event.user_id
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    
    # Optionally sync to Firebase
    if sync_firebase:
        try:
            firebase_service = FirebaseService.get_instance()
            if firebase_service.is_available():
                firebase_data = {
                    "mode": db_event.mode,
                    "focus_score": db_event.focus_score,
                    "load_score": db_event.load_score,
                    "anomaly_score": db_event.anomaly_score,
                    "context": db_event.context,
                    "user_id": db_event.user_id,
                    "timestamp": db_event.timestamp
                }
                firebase_service.insert_event(firebase_data)
        except Exception as e:
            print(f"Warning: Failed to sync event to Firebase: {e}")
    
    return db_event

@app.get("/events", response_model=List[EventResponse])
def get_events(
    user_id: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get events with optional filtering"""
    query = db.query(Event)
    
    if user_id:
        query = query.filter(Event.user_id == user_id)
    if mode:
        query = query.filter(Event.mode == mode)
    
    events = query.order_by(Event.timestamp.desc()).limit(limit).all()
    return events

@app.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """Get a specific event"""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    """Get list of all users"""
    users = db.query(Event.user_id).distinct().all()
    return [user[0] for user in users]

@app.get("/stats/{user_id}")
def get_user_stats(user_id: str, db: Session = Depends(get_db)):
    """Get statistics for a user"""
    events = db.query(Event).filter(Event.user_id == user_id).all()
    
    if not events:
        return {
            "user_id": user_id,
            "total_events": 0,
            "avg_focus": 0,
            "avg_load": 0,
            "avg_anomaly": 0
        }
    
    return {
        "user_id": user_id,
        "total_events": len(events),
        "avg_focus": sum(e.focus_score for e in events) / len(events),
        "avg_load": sum(e.load_score for e in events) / len(events),
        "avg_anomaly": sum(e.anomaly_score for e in events) / len(events),
        "modes": {}
    }

# ==================== Firebase Endpoints ====================

@app.get("/firebase/status")
def get_firebase_status():
    """Check Firebase connection status"""
    try:
        firebase_service = FirebaseService.get_instance()
        return {
            "available": firebase_service.is_available(),
            "message": "Firebase is available" if firebase_service.is_available() else "Firebase is not configured"
        }
    except Exception as e:
        return {
            "available": False,
            "message": f"Error: {str(e)}"
        }

@app.post("/firebase/insert", response_model=FirebaseResponse)
def insert_to_firebase(request: FirebaseInsertRequest):
    """Insert any data into any Firebase collection"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        if request.use_timestamp:
            doc_id = firebase_service.insert_with_timestamp(
                request.collection,
                request.data,
                request.document_id
            )
        else:
            doc_id = firebase_service.insert_document(
                request.collection,
                request.data,
                request.document_id
            )
        
        return FirebaseResponse(
            success=True,
            document_id=doc_id,
            message=f"Document inserted into {request.collection}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inserting to Firebase: {str(e)}")

@app.put("/firebase/update", response_model=FirebaseResponse)
def update_firebase_document(request: FirebaseUpdateRequest):
    """Update a Firebase document"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        firebase_service.update_document(
            request.collection,
            request.document_id,
            request.data,
            request.merge
        )
        
        return FirebaseResponse(
            success=True,
            document_id=request.document_id,
            message=f"Document updated in {request.collection}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating Firebase document: {str(e)}")

@app.post("/firebase/query", response_model=List[Dict])
def query_firebase(request: FirebaseQueryRequest):
    """Query a Firebase collection"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        # Convert filters from dict format to tuple format
        filters = None
        if request.filters:
            filters = []
            for f in request.filters:
                field = f.get("field")
                operator = f.get("operator", "==")
                value = f.get("value")
                if field and value is not None:
                    filters.append((field, operator, value))
        
        results = firebase_service.query_collection(
            request.collection,
            filters=filters,
            limit=request.limit,
            order_by=request.order_by
        )
        
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying Firebase: {str(e)}")

@app.get("/firebase/{collection}/{document_id}")
def get_firebase_document(collection: str, document_id: str):
    """Get a specific document from Firebase"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        doc = firebase_service.get_document(collection, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting Firebase document: {str(e)}")

@app.delete("/firebase/{collection}/{document_id}")
def delete_firebase_document(collection: str, document_id: str):
    """Delete a document from Firebase"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        firebase_service.delete_document(collection, document_id)
        return {"success": True, "message": f"Document {document_id} deleted from {collection}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting Firebase document: {str(e)}")

@app.post("/firebase/batch", response_model=FirebaseResponse)
def batch_insert_firebase(collection: str, documents: List[Dict]):
    """Insert multiple documents in a batch"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        doc_ids = firebase_service.batch_insert(collection, documents)
        return FirebaseResponse(
            success=True,
            data={"document_ids": doc_ids},
            message=f"Inserted {len(doc_ids)} documents into {collection}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error batch inserting to Firebase: {str(e)}")

# Convenience endpoints for common operations

@app.post("/firebase/events")
def insert_event_to_firebase(event: EventCreate):
    """Insert an EEG event directly to Firebase"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        event_data = {
            "mode": event.mode,
            "focus_score": event.focus_score,
            "load_score": event.load_score,
            "anomaly_score": event.anomaly_score,
            "context": event.context,
            "user_id": event.user_id
        }
        
        doc_id = firebase_service.insert_event(event_data)
        return {"success": True, "document_id": doc_id, "message": "Event inserted to Firebase"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inserting event to Firebase: {str(e)}")

@app.get("/firebase/users/{user_id}/events")
def get_user_events_from_firebase(user_id: str, limit: int = 100):
    """Get events for a user from Firebase"""
    try:
        firebase_service = FirebaseService.get_instance()
        if not firebase_service.is_available():
            raise HTTPException(
                status_code=503,
                detail="Firebase is not available. Please configure Firebase credentials."
            )
        
        events = firebase_service.get_user_events(user_id, limit)
        return events
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user events from Firebase: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

