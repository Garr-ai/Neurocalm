"""
Main entry point for backend services
Starts both the FastAPI server, WebSocket server, and frontend
"""
import asyncio
import uvicorn
import sys
import os
import subprocess
import signal
import platform
from multiprocessing import Process
from datetime import datetime

# Add project root to path if running directly
if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from backend.api import app
from backend.websocket_server import WebSocketServer
from backend.firebase_service import FirebaseService

# Global process references for cleanup
api_process = None
websocket_process = None
frontend_process = None

def run_api():
    """Run FastAPI server"""
    uvicorn.run(app, host="0.0.0.0", port=8000)

def run_websocket():
    """Run WebSocket server"""
    server = WebSocketServer()
    asyncio.run(server.start())

def run_frontend():
    """Run frontend development server"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_dir = os.path.join(project_root, "frontend")
    # Check if node_modules exists (dependencies installed)
    node_modules = os.path.join(frontend_dir, "node_modules")
    if not os.path.exists(node_modules):
        print("[WARNING] Frontend dependencies not installed. Run 'npm install' in the frontend directory first.")
        print("[INFO] Skipping frontend startup.")
        return None
    
    # Check if package.json exists
    package_json = os.path.join(frontend_dir, "package.json")
    if not os.path.exists(package_json):
        print("[WARNING] Frontend package.json not found.")
        print("[INFO] Skipping frontend startup.")
        return None
    
    # Determine npm command (npm on Windows/Unix)
    is_windows = platform.system() == "Windows"
    
    try:
        # Check if npm is available
        # On Windows, use shell=True; on Mac/Unix, use shell=False
        npm_check = subprocess.run(
            ["npm", "--version"],
            capture_output=True,
            shell=is_windows,
            timeout=5,
            text=True  # Return string instead of bytes (Python 3.7+)
        )
        
        if npm_check.returncode != 0:
            print("[ERROR] npm not found. Please install Node.js and npm.")
            print("[INFO] On Mac, you can install Node.js via Homebrew: brew install node")
            print("[INFO] Or download from https://nodejs.org/")
            print("[INFO] Skipping frontend startup.")
            return None
        
        npm_version = npm_check.stdout.strip()
        print(f"[FRONTEND] Found npm version: {npm_version}")
        print(f"[FRONTEND] Starting frontend development server...")
        print(f"[FRONTEND] Running: npm start in {frontend_dir}")
        
        # Start npm start process
        # On Windows, use shell=True to properly handle npm.cmd
        # On Unix, we can run npm directly
        if is_windows:
            # Windows: Use shell and create new process group
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            # Optionally hide window (comment out if you want to see npm output)
            # if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            #     creation_flags |= subprocess.CREATE_NO_WINDOW
            
            # Don't pipe output so user can see npm/React dev server output
            process = subprocess.Popen(
                "npm start",
                cwd=frontend_dir,
                shell=True,
                creationflags=creation_flags
                # stdout and stderr go to console (not piped)
            )
        else:
            # Unix/Mac: Run npm directly and create new process group
            # Don't pipe output so user can see npm/React dev server output
            try:
                process = subprocess.Popen(
                    ["npm", "start"],
                    cwd=frontend_dir,
                    preexec_fn=os.setsid
                    # stdout and stderr go to console (not piped)
                )
            except OSError as e:
                # os.setsid might fail in some environments (e.g., if not the session leader)
                # Fall back to regular process creation
                print(f"[WARNING] Could not create process group: {e}")
                print("[INFO] Starting frontend without process group...")
                process = subprocess.Popen(
                    ["npm", "start"],
                    cwd=frontend_dir
                    # stdout and stderr go to console (not piped)
                )
        
        return process
        
    except FileNotFoundError:
        print("[ERROR] npm not found. Please install Node.js and npm.")
        print("[INFO] Skipping frontend startup.")
        return None
    except subprocess.TimeoutExpired:
        print("[ERROR] npm check timed out.")
        print("[INFO] Skipping frontend startup.")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to start frontend: {e}")
        print("[INFO] Skipping frontend startup.")
        return None

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

def cleanup_processes():
    """Clean up all processes"""
    global api_process, websocket_process, frontend_process
    
    print("\n[SHUTDOWN] Stopping all services...")
    
    # Stop frontend
    if frontend_process:
        try:
            print("[SHUTDOWN] Stopping frontend...")
            is_windows = platform.system() == "Windows"
            
            if is_windows:
                # On Windows, use taskkill to kill the process tree
                # This kills npm and all its child processes (like the React dev server)
                try:
                    # First try graceful termination
                    frontend_process.terminate()
                    try:
                        frontend_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(frontend_process.pid)],
                            capture_output=True,
                            check=False
                        )
                        frontend_process.wait(timeout=2)
                except Exception as e:
                    print(f"[WARNING] Error stopping frontend gracefully: {e}")
                    # Try force kill as last resort
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(frontend_process.pid)],
                            capture_output=True,
                            check=False
                        )
                    except Exception:
                        pass
            else:
                # On Unix/Mac, kill the process group (includes all child processes)
                try:
                    # Try to get the process group and kill it
                    try:
                        pgid = os.getpgid(frontend_process.pid)
                        os.killpg(pgid, signal.SIGTERM)
                        try:
                            frontend_process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            # Force kill if it doesn't terminate
                            try:
                                os.killpg(pgid, signal.SIGKILL)
                                frontend_process.wait(timeout=2)
                            except ProcessLookupError:
                                # Process group already dead
                                pass
                    except ProcessLookupError:
                        # Process already dead
                        pass
                    except OSError:
                        # If process group doesn't exist (e.g., if os.setsid failed),
                        # just terminate the process directly
                        frontend_process.terminate()
                        try:
                            frontend_process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            frontend_process.kill()
                            frontend_process.wait(timeout=2)
                except Exception as e:
                    print(f"[WARNING] Error stopping frontend: {e}")
                    try:
                        frontend_process.terminate()
                        frontend_process.wait(timeout=2)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[WARNING] Error stopping frontend: {e}")
        finally:
            frontend_process = None
    
    # Stop API server
    if api_process:
        try:
            print("[SHUTDOWN] Stopping API server...")
            api_process.terminate()
            api_process.join(timeout=5)
            if api_process.is_alive():
                api_process.kill()
                api_process.join()
        except Exception as e:
            print(f"[WARNING] Error stopping API server: {e}")
        finally:
            api_process = None
    
    # Stop WebSocket server
    if websocket_process:
        try:
            print("[SHUTDOWN] Stopping WebSocket server...")
            websocket_process.terminate()
            websocket_process.join(timeout=5)
            if websocket_process.is_alive():
                websocket_process.kill()
                websocket_process.join()
        except Exception as e:
            print(f"[WARNING] Error stopping WebSocket server: {e}")
        finally:
            websocket_process = None
    
    print("[SHUTDOWN] All services stopped.")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    cleanup_processes()
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    # SIGINT (Ctrl+C) works on Windows, Mac, and Linux
    # SIGTERM works on Mac and Linux, but not reliably on Windows
    try:
        signal.signal(signal.SIGINT, signal_handler)
        # SIGTERM is available on Unix systems (Mac, Linux)
        if platform.system() != "Windows" and hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)
    except (ValueError, OSError) as e:
        # Signal handling might fail on some systems
        print(f"[WARNING] Could not set up signal handlers: {e}")
        print("[INFO] You can still stop the services with Ctrl+C")
    
    print("="*60)
    print("Starting Neurocalm Application")
    print("="*60)
    print()
    
    try:
        # Start API server in a separate process
        print("[BACKEND] Starting FastAPI server on http://localhost:8000...")
        api_process = Process(target=run_api)
        api_process.start()
        print("[BACKEND] FastAPI server started.")
        print()
        
        # Start WebSocket server in a separate process
        print("[BACKEND] Starting WebSocket server on ws://localhost:8765...")
        websocket_process = Process(target=run_websocket)
        websocket_process.start()
        print("[BACKEND] WebSocket server started.")
        print()
        
        # Start frontend development server
        print("[FRONTEND] Starting frontend development server...")
        frontend_process = run_frontend()
        if frontend_process:
            print("[FRONTEND] Frontend server starting (may take a moment)...")
            print("[FRONTEND] Frontend will be available at http://localhost:3000")
        print()
        
        print("="*60)
        print("All services started!")
        print("="*60)
        print()
        print("Services:")
        print("  - FastAPI:    http://localhost:8000")
        print("  - WebSocket:  ws://localhost:8765")
        if frontend_process:
            print("  - Frontend:   http://localhost:3000")
        print()
        print("Press Ctrl+C to stop all services")
        print("="*60)
        print()
        
        # Wait for processes to complete (they should run indefinitely)
        # Keep the main process alive and wait for interrupt
        try:
            # Wait for WebSocket process (it runs in the main flow)
            # But since we moved it to a process, we need to wait for any process
            while True:
                # Check if any process has died
                if api_process and not api_process.is_alive():
                    print("[ERROR] API server process died unexpectedly!")
                    break
                if websocket_process and not websocket_process.is_alive():
                    print("[ERROR] WebSocket server process died unexpectedly!")
                    break
                if frontend_process and frontend_process.poll() is not None:
                    print("[ERROR] Frontend process died unexpectedly!")
                    break
                # Sleep to avoid busy waiting
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[INTERRUPT] Received shutdown signal...")
        
    except Exception as e:
        print(f"\n[ERROR] Error starting services: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cleanup_processes()



