"""
Firebase service for backend data operations
Supports Firestore database for flexible data storage
"""
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import SERVER_TIMESTAMP

class FirebaseService:
    """Service for interacting with Firebase Firestore"""
    
    _instance = None
    _db = None
    
    def __init__(self):
        """Initialize Firebase Admin SDK"""
        if FirebaseService._instance is not None and FirebaseService._instance is not self:
            raise Exception("FirebaseService is a singleton. Use get_instance() instead.")
        
        self._initialize_firebase()
        FirebaseService._instance = self
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of FirebaseService"""
        if cls._instance is None:
            instance = cls.__new__(cls)
            instance.__init__()
            cls._instance = instance
        return cls._instance
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK with credentials"""
        # Check if Firebase is already initialized
        try:
            firebase_admin.get_app()
            self._db = firestore.client()
            print("Firebase already initialized")
            return
        except ValueError:
            pass  # Not initialized, continue
        
        # Try to get credentials from environment variable or file
        cred = None
        
        # Option 1: Service account key file path from environment variable
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")
        if service_account_path and os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            print(f"Using Firebase service account key from: {service_account_path}")
        
        # Option 2: Service account JSON as environment variable
        if not cred and os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
            try:
                service_account_json = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))
                cred = credentials.Certificate(service_account_json)
                print("Using Firebase service account from environment variable")
            except json.JSONDecodeError:
                print("Warning: FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON")
        
        # Option 3: Auto-detect service account file in project root
        if not cred:
            # Get project root directory (parent of backend directory)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            # Common service account file patterns
            possible_files = [
                os.path.join(project_root, "neurocalm-8a63a-firebase-adminsdk-fbsvc-2e9aadd23d.json"),
                os.path.join(project_root, "firebase-service-account.json"),
                os.path.join(project_root, "service-account-key.json"),
                os.path.join(project_root, "firebase-adminsdk.json"),
            ]
            
            # Also check for any file matching the pattern *firebase*adminsdk*.json
            import glob
            pattern = os.path.join(project_root, "*firebase*adminsdk*.json")
            possible_files.extend(glob.glob(pattern))
            
            for file_path in possible_files:
                if os.path.exists(file_path):
                    try:
                        cred = credentials.Certificate(file_path)
                        print(f"Auto-detected Firebase service account key: {file_path}")
                        break
                    except Exception as e:
                        print(f"Warning: Could not load service account from {file_path}: {e}")
                        continue
        
        # Option 4: Default credentials (for Google Cloud environments)
        if not cred:
            try:
                cred = credentials.ApplicationDefault()
                print("Using Firebase Application Default Credentials")
            except Exception as e:
                print(f"Warning: Could not use Application Default Credentials: {e}")
        
        # Initialize Firebase Admin
        if cred:
            try:
                firebase_admin.initialize_app(cred)
                self._db = firestore.client()
                print("Firebase Admin SDK initialized successfully")
            except Exception as e:
                print(f"Error initializing Firebase: {e}")
                print("Firebase operations will be disabled")
                self._db = None
        else:
            print("Warning: No Firebase credentials found. Firebase operations will be disabled.")
            print("To enable Firebase:")
            print("  1. Set FIREBASE_SERVICE_ACCOUNT_KEY to path of service account JSON file")
            print("  2. Or set FIREBASE_SERVICE_ACCOUNT_JSON to JSON string of service account")
            print("  3. Or use Application Default Credentials in Google Cloud environment")
            self._db = None
    
    def is_available(self) -> bool:
        """Check if Firebase is available and initialized"""
        return self._db is not None
    
    def insert_document(self, collection: str, data: Dict[str, Any], document_id: Optional[str] = None) -> str:
        """
        Insert a document into a Firestore collection
        
        Args:
            collection: Collection name (e.g., "events", "users", "sessions")
            data: Dictionary of data to insert
            document_id: Optional document ID. If not provided, Firestore will auto-generate one
        
        Returns:
            Document ID of the inserted document
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        # Convert datetime objects to Firestore timestamps
        data = self._prepare_data(data)
        
        if document_id:
            doc_ref = self._db.collection(collection).document(document_id)
            doc_ref.set(data)
            return document_id
        else:
            doc_ref = self._db.collection(collection).document()
            doc_ref.set(data)
            return doc_ref.id
    
    def insert_with_timestamp(self, collection: str, data: Dict[str, Any], document_id: Optional[str] = None) -> str:
        """
        Insert a document with automatic server timestamp
        
        Args:
            collection: Collection name
            data: Dictionary of data to insert
            document_id: Optional document ID
        
        Returns:
            Document ID of the inserted document
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        # Add server timestamp
        data = self._prepare_data(data)
        data['created_at'] = SERVER_TIMESTAMP
        data['updated_at'] = SERVER_TIMESTAMP
        
        return self.insert_document(collection, data, document_id)
    
    def update_document(self, collection: str, document_id: str, data: Dict[str, Any], merge: bool = True) -> None:
        """
        Update an existing document
        
        Args:
            collection: Collection name
            document_id: Document ID to update
            data: Dictionary of data to update
            merge: If True, merge with existing data. If False, replace entire document
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        data = self._prepare_data(data)
        data['updated_at'] = SERVER_TIMESTAMP
        
        doc_ref = self._db.collection(collection).document(document_id)
        if merge:
            doc_ref.update(data)
        else:
            doc_ref.set(data)
    
    def get_document(self, collection: str, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a document by ID
        
        Args:
            collection: Collection name
            document_id: Document ID
        
        Returns:
            Document data as dictionary, or None if not found
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        doc_ref = self._db.collection(collection).document(document_id)
        doc = doc_ref.get()
        
        if doc.exists:
            return self._convert_firestore_data(doc.to_dict())
        return None
    
    def query_collection(self, collection: str, filters: Optional[List[tuple]] = None, 
                        limit: Optional[int] = None, order_by: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query a collection with optional filters
        
        Args:
            collection: Collection name
            filters: List of tuples (field, operator, value) e.g., [("user_id", "==", "user123")]
            limit: Maximum number of documents to return
            order_by: Field name to order by (use "timestamp desc" for descending)
        
        Returns:
            List of documents as dictionaries
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        query = self._db.collection(collection)
        
        # Apply filters
        if filters:
            for field, operator, value in filters:
                query = query.where(field, operator, value)
        
        # Apply ordering
        if order_by:
            if " desc" in order_by.lower():
                field = order_by.split()[0]
                query = query.order_by(field, direction=firestore.Query.DESCENDING)
            else:
                query = query.order_by(order_by)
        
        # Apply limit
        if limit:
            query = query.limit(limit)
        
        docs = query.stream()
        return [self._convert_firestore_data(doc.to_dict()) | {"id": doc.id} for doc in docs]
    
    def delete_document(self, collection: str, document_id: str) -> None:
        """
        Delete a document
        
        Args:
            collection: Collection name
            document_id: Document ID to delete
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        self._db.collection(collection).document(document_id).delete()
    
    def batch_insert(self, collection: str, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Insert multiple documents in a batch
        
        Args:
            collection: Collection name
            documents: List of document dictionaries
        
        Returns:
            List of document IDs
        """
        if not self.is_available():
            raise RuntimeError("Firebase is not available. Check credentials.")
        
        batch = self._db.batch()
        doc_ids = []
        
        for doc_data in documents:
            doc_data = self._prepare_data(doc_data)
            doc_ref = self._db.collection(collection).document()
            batch.set(doc_ref, doc_data)
            doc_ids.append(doc_ref.id)
        
        batch.commit()
        return doc_ids
    
    def _prepare_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for Firestore (convert datetime, handle nested dicts)"""
        prepared = {}
        for key, value in data.items():
            if isinstance(value, datetime):
                prepared[key] = value
            elif isinstance(value, dict):
                prepared[key] = self._prepare_data(value)
            elif isinstance(value, list):
                prepared[key] = [self._prepare_data(item) if isinstance(item, dict) else item for item in value]
            else:
                prepared[key] = value
        return prepared
    
    def _convert_firestore_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Firestore data types to Python types"""
        if data is None:
            return {}
        
        converted = {}
        for key, value in data.items():
            if hasattr(value, 'timestamp'):  # Firestore Timestamp
                converted[key] = value.timestamp()
            elif isinstance(value, dict):
                converted[key] = self._convert_firestore_data(value)
            elif isinstance(value, list):
                converted[key] = [self._convert_firestore_data(item) if isinstance(item, dict) else item for item in value]
            else:
                converted[key] = value
        return converted
    
    # Convenience methods for common operations
    
    def insert_event(self, event_data: Dict[str, Any]) -> str:
        """Insert an EEG event into Firestore"""
        return self.insert_with_timestamp("events", event_data)
    
    def insert_user_data(self, user_id: str, user_data: Dict[str, Any]) -> str:
        """Insert or update user data"""
        user_data['user_id'] = user_id
        return self.insert_with_timestamp("users", user_data, document_id=user_id)
    
    def insert_session(self, session_data: Dict[str, Any]) -> str:
        """Insert a session into Firestore"""
        return self.insert_with_timestamp("sessions", session_data)
    
    def get_user_events(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a specific user"""
        return self.query_collection(
            "events",
            filters=[("user_id", "==", user_id)],
            limit=limit,
            order_by="timestamp desc"
        )

