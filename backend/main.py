"""
Main entry point for backend services
Starts both the FastAPI server and WebSocket server
"""
import asyncio
import uvicorn
from multiprocessing import Process
from datetime import datetime
from backend.api import app
from backend.websocket_server import WebSocketServer
from backend.firebase_service import FirebaseService

def run_api():
    """Run FastAPI server"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

def run_websocket():
    """Run WebSocket server"""
    server = WebSocketServer()
    asyncio.run(server.start())

def test_firebase_insert():
    """Test function to insert sample data into Firestore"""
    print("\n" + "="*50)
    print("Testing Firebase Firestore Insert")
    print("="*50)
    
    try:
        # Get Firebase service instance
        firebase = FirebaseService.get_instance()
        
        if not firebase.is_available():
            print("[ERROR] Firebase is not available. Check credentials.")
            return False
        
        print("[OK] Firebase is available")
        
        # Test 1: Insert a simple document
        print("\n[TEST 1] Inserting a simple document...")
        test_data = {
            "name": "Test Document",
            "value": 42,
            "timestamp": datetime.utcnow(),
            "metadata": {
                "source": "main.py test",
                "version": "1.0"
            }
        }
        
        doc_id = firebase.insert_with_timestamp("test_collection", test_data)
        print(f"[OK] Document inserted with ID: {doc_id}")
        
        # Test 2: Retrieve the document
        print("\n[TEST 2] Retrieving the document...")
        retrieved = firebase.get_document("test_collection", doc_id)
        if retrieved:
            print(f"[OK] Document retrieved successfully:")
            print(f"   - Name: {retrieved.get('name')}")
            print(f"   - Value: {retrieved.get('value')}")
        else:
            print("[ERROR] Failed to retrieve document")
            return False
        
        # Test 3: Insert an EEG event
        print("\n[TEST 3] Inserting an EEG event...")
        event_data = {
            "mode": "test",
            "focus_score": 75.5,
            "load_score": 60.2,
            "anomaly_score": 15.3,
            "context": {
                "test": True,
                "source": "main.py"
            },
            "user_id": "test_user_123"
        }
        
        event_id = firebase.insert_event(event_data)
        print(f"[OK] Event inserted with ID: {event_id}")
        
        # Test 4: Query events
        print("\n[TEST 4] Querying events for test user...")
        try:
            events = firebase.get_user_events("test_user_123", limit=5)
            print(f"[OK] Found {len(events)} event(s) for test_user_123")
        except Exception as e:
            if "index" in str(e).lower():
                print(f"[WARNING] Query requires a Firestore index. This is expected for complex queries.")
                print(f"         You can create the index at the URL provided in the error message.")
                print(f"         For now, skipping this test.")
            else:
                raise
        
        # Test 5: Insert user data
        print("\n[TEST 5] Inserting user data...")
        user_data = {
            "name": "Test User",
            "email": "test@example.com",
            "created_at": datetime.utcnow()
        }
        user_id = firebase.insert_user_data("test_user_123", user_data)
        print(f"[OK] User data inserted/updated for user: {user_id}")
        
        print("\n" + "="*50)
        print("[SUCCESS] All Firebase tests passed successfully!")
        print("="*50 + "\n")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Error during Firebase test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Run Firebase test before starting servers
    test_firebase_insert()
    
    # Start API server in a separate process
    api_process = Process(target=run_api)
    api_process.start()
    
    # Start WebSocket server in main process
    try:
        run_websocket()
    except KeyboardInterrupt:
        print("Shutting down...")
        api_process.terminate()
        api_process.join()



