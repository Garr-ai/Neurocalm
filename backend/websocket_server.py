"""
WebSocket server for real-time EEG data streaming
"""
import asyncio
import websockets
import json
import sys
import os
from typing import Set
from datetime import datetime, timezone
from brainflow.board_shim import BoardIds

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.eeg_service import EEGService
from backend.database import SessionLocal, Event
from backend.firebase_service import FirebaseService

class WebSocketServer:
    """WebSocket server to stream EEG data to frontend"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        # Use Ganglion board (can be overridden with environment variable)
        board_id = int(os.getenv("BOARD_ID", BoardIds.GANGLION_BOARD))
        self.eeg_service = EEGService(board_id=board_id)
        self.connected_clients: Set = set()
        self.current_mode = "background"
        self.current_context = {}
        self.current_user_id = "default"
        self.stream_task = None
    
    async def register_client(self, websocket):
        """Register a new client"""
        self.connected_clients.add(websocket)
        print(f"[CLIENT] Client connected. Total clients: {len(self.connected_clients)}")
        print(f"[CLIENT] WebSocket object: {websocket}, Remote: {getattr(websocket, 'remote_address', 'N/A')}")
        
        # Send current state to new client
        try:
            await websocket.send(json.dumps({
                "type": "state_sync",
                "is_recording": self.eeg_service.is_streaming,
                "mode": self.current_mode
            }))
            print(f"[CLIENT] State sync message sent successfully")
        except Exception as e:
            print(f"[CLIENT] Error sending state sync: {e}")
            self.connected_clients.discard(websocket)
    
    async def unregister_client(self, websocket):
        """Unregister a client"""
        self.connected_clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(self.connected_clients)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.connected_clients:
            print(f"[BROADCAST] WARNING: No connected clients to broadcast to!")
            return
        
        message_str = json.dumps(message)
        disconnected = set()
        sent_count = 0
        
        for client in self.connected_clients.copy():  # Use copy to avoid modification during iteration
            try:
                await client.send(message_str)
                sent_count += 1
            except websockets.exceptions.ConnectionClosed:
                print(f"[BROADCAST] Client disconnected")
                disconnected.add(client)
            except Exception as e:
                print(f"[BROADCAST] Error sending to client: {e}")
                disconnected.add(client)
        
        # Remove disconnected clients
        for client in disconnected:
            self.connected_clients.discard(client)
        
        if sent_count > 0:
            print(f"[BROADCAST] ✅ Successfully sent to {sent_count}/{len(self.connected_clients)} client(s)")
        else:
            print(f"[BROADCAST] ❌ WARNING: Failed to send to any clients! ({len(self.connected_clients)} clients registered)")
            # Try to diagnose the issue
            for i, client in enumerate(self.connected_clients):
                print(f"[BROADCAST] Client #{i}: {client}, State: {getattr(client, 'state', 'N/A')}")
    
    async def handle_message(self, websocket, message: str):
        """Handle incoming messages from clients"""
        try:
            print(f"[WS] Raw message received: {message[:200]}...")  # First 200 chars
            data = json.loads(message)
            print(f"[WS] Parsed message: {data}")
            msg_type = data.get("type")
            print(f"[WS] Message type: {msg_type}")
            
            if msg_type == "set_mode":
                self.current_mode = data.get("mode", "background")
                await self.broadcast({"type": "mode_changed", "mode": self.current_mode})
            
            elif msg_type == "set_context":
                self.current_context = data.get("context", {})
            
            elif msg_type == "set_user":
                self.current_user_id = data.get("user_id", "default")
            
            elif msg_type == "start_recording":
                print(f"[WS] start_recording received! is_streaming={self.eeg_service.is_streaming}")
                # Start EEG streaming if not already started
                if not self.eeg_service.is_streaming:
                    print("[WS] Starting EEG recording...")
                    await websocket.send(json.dumps({
                        "type": "info",
                        "message": "Received start_recording command, initializing..."
                    }))
                    try:
                        # Get connection parameters from message or environment
                        serial_port = data.get("serial_port") or os.getenv("GANGLION_SERIAL_PORT")
                        mac_address = data.get("mac_address") or os.getenv("GANGLION_MAC_ADDRESS")
                        dongle_port = data.get("dongle_port") or os.getenv("GANGLION_DONGLE_PORT")
                        
                        print(f"Connection parameters - MAC: {mac_address}, Serial: {serial_port}, Dongle: {dongle_port}")
                        
                        # Try auto-detection if no parameters provided
                        if not mac_address and not serial_port and not dongle_port:
                            print("No connection parameters provided. Attempting auto-detection...")
                            await websocket.send(json.dumps({
                                "type": "info",
                                "message": "Attempting to auto-detect Ganglion..."
                            }))
                            
                            # Import auto-detection utilities
                            from backend.auto_detect_ganglion import find_ble_dongle_ports
                            
                            # Try auto-detection: scan for dongle ports
                            dongle_ports = find_ble_dongle_ports()
                            print(f"Auto-detection: Found {len(dongle_ports)} potential dongle port(s): {dongle_ports}")
                            
                            if dongle_ports:
                                print(f"Found {len(dongle_ports)} potential dongle port(s), trying auto-detection...")
                                # Try connecting with just dongle port (let BrainFlow scan for MAC)
                                for dongle_port in dongle_ports:
                                    try:
                                        print(f"Trying auto-detect with dongle port: {dongle_port}")
                                        self.eeg_service.connect(dongle_port=dongle_port)
                                        print(f"[OK] Auto-detection successful with {dongle_port}!")
                                        break
                                    except Exception as e:
                                        import traceback
                                        error_details = traceback.format_exc()
                                        print(f"Failed with {dongle_port}: {e}")
                                        print(f"Traceback: {error_details}")
                                        continue
                                else:
                                    # All dongle ports failed
                                    error_msg = (
                                        "Auto-detection failed. Options:\n"
                                        "1. For BLE dongle: Set GANGLION_DONGLE_PORT in .env\n"
                                        "2. Run 'python -m backend.auto_detect_ganglion' to find your dongle port\n"
                                        "3. Make sure Ganglion is powered on and in range"
                                    )
                                    print(f"ERROR: {error_msg}")
                                    await websocket.send(json.dumps({
                                        "type": "error",
                                        "message": error_msg
                                    }))
                                    return
                            else:
                                # No dongle found
                                error_msg = (
                                    "No BLE dongle found. Options:\n"
                                    "1. Plug in your BLE dongle\n"
                                    "2. Set GANGLION_DONGLE_PORT in .env file\n"
                                    "3. Run 'python -m backend.auto_detect_ganglion' to find your dongle port"
                                )
                                print(f"ERROR: {error_msg}")
                                await websocket.send(json.dumps({
                                    "type": "error",
                                    "message": error_msg
                                }))
                                return
                        # For BLE dongle: try with just dongle port (auto-detect MAC)
                        elif dongle_port:
                            print(f"Connecting to Ganglion via BLE dongle (auto-detect MAC): Dongle={dongle_port}")
                            if mac_address:
                                print(f"  Using provided MAC: {mac_address}")
                                self.eeg_service.connect(mac_address=mac_address, dongle_port=dongle_port)
                            else:
                                print(f"  Auto-detecting Ganglion MAC address...")
                                self.eeg_service.connect(dongle_port=dongle_port)
                        # For BLE dongle with MAC: need both MAC address and dongle port
                        elif mac_address and dongle_port:
                            print(f"Connecting to Ganglion via BLE dongle: MAC={mac_address}, Dongle={dongle_port}")
                            self.eeg_service.connect(mac_address=mac_address, dongle_port=dongle_port)
                        # For direct Bluetooth: just MAC address
                        elif mac_address:
                            print(f"Connecting to Ganglion via Bluetooth: {mac_address}")
                            self.eeg_service.connect(mac_address=mac_address)
                        # For USB: serial port
                        elif serial_port:
                            print(f"Connecting to Ganglion via USB: {serial_port}")
                            self.eeg_service.connect(serial_port=serial_port)
                        
                        print("Starting EEG stream...")
                        self.eeg_service.start_streaming(self.on_eeg_data)
                        
                        # Give the board a moment to start collecting data
                        print("[DEBUG] Waiting 2 seconds for board to accumulate initial data...")
                        await asyncio.sleep(2)
                        
                        # Start the stream loop as a background task
                        self.stream_task = asyncio.create_task(self.eeg_service.stream_loop())
                        print("EEG recording started successfully!")
                        print(f"[DEBUG] Stream task created: {self.stream_task}, is_streaming={self.eeg_service.is_streaming}")
                        print(f"[DEBUG] Board ID: {self.eeg_service.board_id}, Board: {self.eeg_service.board}")
                        
                        await websocket.send(json.dumps({
                            "type": "recording_started",
                            "message": "Recording started successfully"
                        }))
                        await self.broadcast({"type": "recording_started"})
                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()
                        error_msg = f"Failed to start EEG recording: {str(e)}\n\nMake sure:\n1. Ganglion is powered on\n2. Ganglion is paired (System Settings → Bluetooth)\n3. Connection details are set in .env file\n\nRun 'python -m backend.auto_detect_ganglion' to find your dongle port."
                        print(f"ERROR: {error_msg}")
                        print(f"Exception details: {type(e).__name__}: {e}")
                        print(f"Full traceback:\n{error_details}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": error_msg,
                            "details": str(e)
                        }))
                else:
                    print("EEG already streaming, ignoring start_recording request")
                    await websocket.send(json.dumps({
                        "type": "info",
                        "message": "Recording already in progress"
                    }))
            
            elif msg_type == "stop_recording":
                if self.eeg_service.is_streaming:
                    self.eeg_service.stop_streaming()
                    # Cancel the stream task if it exists
                    if self.stream_task:
                        self.stream_task.cancel()
                        try:
                            await self.stream_task
                        except asyncio.CancelledError:
                            pass
                        self.stream_task = None
                    self.eeg_service.disconnect()
                    await self.broadcast({"type": "recording_stopped"})
        
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON: {str(e)}"
            print(f"[WS] JSON decode error: {error_msg}")
            print(f"[WS] Message was: {message[:200]}")
            await websocket.send(json.dumps({"type": "error", "message": error_msg}))
        except Exception as e:
            import traceback
            error_msg = f"Error handling message: {str(e)}"
            print(f"[WS] Exception in handle_message: {error_msg}")
            print(f"[WS] Traceback:\n{traceback.format_exc()}")
            await websocket.send(json.dumps({"type": "error", "message": error_msg}))
    
    async def on_eeg_data(self, bandpowers: dict):
        """Callback when new EEG data is available"""
        # Save to database
        db = SessionLocal()
        try:
            event = Event(
                timestamp=datetime.now(timezone.utc),
                mode=self.current_mode,
                focus_score=bandpowers["focus_score"],
                load_score=bandpowers["load_score"],
                anomaly_score=bandpowers["anomaly_score"],
                context=self.current_context,
                user_id=self.current_user_id
            )
            db.add(event)
            db.commit()
            
            # Optionally sync to Firebase
            try:
                firebase_service = FirebaseService.get_instance()
                if firebase_service.is_available():
                    firebase_data = {
                        "mode": self.current_mode,
                        "focus_score": bandpowers["focus_score"],
                        "load_score": bandpowers["load_score"],
                        "anomaly_score": bandpowers["anomaly_score"],
                        "context": self.current_context,
                        "user_id": self.current_user_id,
                        "timestamp": event.timestamp
                    }
                    firebase_service.insert_event(firebase_data)
            except Exception as e:
                print(f"Warning: Failed to sync event to Firebase: {e}")
        except Exception as e:
            print(f"Error saving event: {e}")
            db.rollback()
        finally:
            db.close()
        
        # Broadcast to clients
        try:
            message = {
                "type": "eeg_data",
                "data": bandpowers,
                "mode": self.current_mode,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            print(f"[DEBUG] Broadcasting EEG data: {len(self.connected_clients)} client(s) connected")
            print(f"[DEBUG] Data: focus={bandpowers.get('focus_score', 'N/A'):.2f}, load={bandpowers.get('load_score', 'N/A'):.2f}, anomaly={bandpowers.get('anomaly_score', 'N/A'):.2f}")
            await self.broadcast(message)
        except Exception as e:
            import traceback
            print(f"[ERROR] Failed to broadcast EEG data: {e}")
            print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
    
    async def handle_client(self, websocket):
        """Handle a client connection"""
        await self.register_client(websocket)
        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister_client(websocket)
    
    def process_request(self, protocol, request):
        """Custom request processor to handle Connection header issues"""
        # In websockets 15.x, request is a Request object
        # Access headers via request.headers
        connection = request.headers.get("Connection", "")
        if connection and "upgrade" not in connection.lower():
            # Replace Connection header to include Upgrade
            request.headers["Connection"] = "Upgrade"
        return None  # Continue with normal processing
    
    async def start(self):
        """Start the WebSocket server"""
        print(f"Starting WebSocket server on ws://{self.host}:{self.port}")
        async with websockets.serve(
            self.handle_client, 
            self.host, 
            self.port,
            process_request=self.process_request,
        ):
            await asyncio.Future()  # Run forever

if __name__ == "__main__":
    server = WebSocketServer()
    asyncio.run(server.start())

