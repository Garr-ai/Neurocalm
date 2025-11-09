"""
WebSocket server for real-time EEG data streaming
"""
import asyncio
import websockets
import json
import sys
import os
from typing import Set
from datetime import datetime
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
        print(f"Client connected. Total clients: {len(self.connected_clients)}")
    
    async def unregister_client(self, websocket):
        """Unregister a client"""
        self.connected_clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(self.connected_clients)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if self.connected_clients:
            message_str = json.dumps(message)
            disconnected = set()
            for client in self.connected_clients:
                try:
                    await client.send(message_str)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
            
            # Remove disconnected clients
            for client in disconnected:
                self.connected_clients.discard(client)
    
    async def handle_message(self, websocket, message: str):
        """Handle incoming messages from clients"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "set_mode":
                self.current_mode = data.get("mode", "background")
                await self.broadcast({"type": "mode_changed", "mode": self.current_mode})
            
            elif msg_type == "set_context":
                self.current_context = data.get("context", {})
            
            elif msg_type == "set_user":
                self.current_user_id = data.get("user_id", "default")
            
            elif msg_type == "start_recording":
                # Start EEG streaming if not already started
                if not self.eeg_service.is_streaming:
                    print("Starting EEG recording...")
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
                            
                            # Try auto-detection: scan for dongle ports and try connecting
                            import glob
                            dongle_ports = []
                            # Check both cu and tty ports (prefer cu for OpenBCI on macOS)
                            patterns = [
                                "/dev/cu.usbserial*",  # Prefer cu ports (no dash - matches usbserial-XXX and usbserialXXX)
                                "/dev/cu.usbmodem*",   # Matches usbmodem11, usbmodem-XXX, etc.
                                "/dev/cu.USB-Serial*",
                                "/dev/cu.*",  # Catch-all for cu ports (will filter out non-BLE)
                                "/dev/tty.usbserial*",  # Fallback to tty
                                "/dev/tty.usbmodem*",
                                "/dev/tty.USB-Serial*",
                            ]
                            cu_ports = []
                            tty_ports = []
                            for pattern in patterns:
                                try:
                                    found = glob.glob(pattern)
                                    print(f"  Checking pattern {pattern}: found {len(found)} ports")
                                    for port in found:
                                        # Skip common non-BLE ports
                                        skip = False
                                        skip_terms = ['Bluetooth', 'debug', 'Bluetooth-Incoming']
                                        for term in skip_terms:
                                            if term.lower() in port.lower():
                                                skip = True
                                                break
                                        
                                        if not skip:
                                            if '/dev/cu.' in port:
                                                if port not in cu_ports:
                                                    cu_ports.append(port)
                                            elif '/dev/tty.' in port:
                                                if port not in tty_ports:
                                                    tty_ports.append(port)
                                except Exception as e:
                                    print(f"  Error checking pattern {pattern}: {e}")
                            
                            # Prefer cu ports (recommended for OpenBCI on macOS)
                            dongle_ports = cu_ports + tty_ports
                            print(f"Auto-detection: Found {len(dongle_ports)} potential dongle port(s): {dongle_ports}")
                            
                            if dongle_ports:
                                print(f"Found {len(dongle_ports)} potential dongle port(s), trying auto-detection...")
                                # Try connecting with just dongle port (let BrainFlow scan for MAC)
                                for dongle_port in dongle_ports:
                                    try:
                                        print(f"Trying auto-detect with dongle port: {dongle_port}")
                                        self.eeg_service.connect(dongle_port=dongle_port)
                                        print(f"✅ Auto-detection successful with {dongle_port}!")
                                        break
                                    except Exception as e:
                                        print(f"Failed with {dongle_port}: {e}")
                                        continue
                                else:
                                    # All dongle ports failed
                                    error_msg = (
                                        "Auto-detection failed. Please provide connection details:\n"
                                        "1. For BLE dongle: Set GANGLION_DONGLE_PORT in .env\n"
                                        "2. Run 'python -m backend.auto_detect_ganglion' to find your dongle port"
                                    )
                                    print(f"ERROR: {error_msg}")
                                    await websocket.send(json.dumps({
                                        "type": "error",
                                        "message": error_msg
                                    }))
                                    return
                            else:
                                error_msg = (
                                    "No BLE dongle found. Please:\n"
                                    "1. Plug in your BLE dongle\n"
                                    "2. Set GANGLION_DONGLE_PORT in .env\n"
                                    "3. Or run 'python -m backend.auto_detect_ganglion'"
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
                        # Start the stream loop as a background task
                        self.stream_task = asyncio.create_task(self.eeg_service.stream_loop())
                        print("EEG recording started successfully!")
                        await self.broadcast({"type": "recording_started"})
                    except Exception as e:
                        error_msg = f"Failed to start EEG: {str(e)}\n\nMake sure:\n1. Ganglion is powered on\n2. Ganglion is paired (System Settings → Bluetooth)\n3. Connection details are set in .env file\n\nRun 'python find_ganglion.py' to find your MAC address."
                        print(f"ERROR: {error_msg}")
                        print(f"Exception details: {type(e).__name__}: {e}")
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": error_msg
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
        
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
        except Exception as e:
            await websocket.send(json.dumps({"type": "error", "message": str(e)}))
    
    async def on_eeg_data(self, bandpowers: dict):
        """Callback when new EEG data is available"""
        # Save to database
        db = SessionLocal()
        try:
            event = Event(
                timestamp=datetime.utcnow(),
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
        await self.broadcast({
            "type": "eeg_data",
            "data": bandpowers,
            "mode": self.current_mode,
            "timestamp": datetime.utcnow().isoformat()
        })
    
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

