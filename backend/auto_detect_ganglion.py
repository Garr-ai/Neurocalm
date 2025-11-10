"""
Auto-detect Ganglion board and BLE dongle
Similar to OpenBCI GUI's auto-detection
"""
import os
import glob
import platform
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

def find_ble_dongle_ports():
    """Find BLE dongle serial ports
    
    On macOS, OpenBCI devices should use /dev/cu.* ports, not /dev/tty.*
    """
    ports = []
    
    # Check both tty and cu ports (prefer cu for OpenBCI)
    patterns = [
        "/dev/cu.usbserial-*",  # Prefer cu ports
        "/dev/cu.usbmodem-*",
        "/dev/cu.USB-Serial-*",
        "/dev/cu.BLED*",
        "/dev/cu.SLAB_USBtoUART*",
        "/dev/tty.usbserial-*",  # Fallback to tty
        "/dev/tty.usbmodem-*",
        "/dev/tty.USB-Serial-*",
        "/dev/tty.BLED*",
        "/dev/tty.SLAB_USBtoUART*",
    ]
    
    cu_ports = []  # Prefer cu ports
    tty_ports = []
    
    for pattern in patterns:
        found = glob.glob(pattern)
        for port in found:
            # Skip common non-BLE ports
            if 'Bluetooth' not in port and 'debug' not in port.lower():
                if '/dev/cu.' in port:
                    cu_ports.append(port)
                else:
                    tty_ports.append(port)
    
    # Windows patterns
    if platform.system() == "Windows":
        try:
            import serial.tools.list_ports
            com_ports = serial.tools.list_ports.comports()
            for port in com_ports:
                if 'USB' in port.description or 'Serial' in port.description:
                    ports.append(port.device)
        except ImportError:
            pass  # pyserial not installed, skip Windows port detection
    
    # Return cu ports first, then tty ports, then Windows ports
    return cu_ports + tty_ports + ports

def try_connect_ganglion(mac_address=None, dongle_port=None):
    """Try to connect to Ganglion with given parameters"""
    try:
        params = BrainFlowInputParams()
        if mac_address:
            params.mac_address = mac_address
        if dongle_port:
            params.serial_port = dongle_port
        
        board = BoardShim(BoardIds.GANGLION_BOARD, params)
        board.prepare_session()
        board.release_session()
        return True
    except Exception as e:
        return False

def auto_detect_ganglion():
    """Auto-detect Ganglion connection"""
    print("Scanning for BLE dongle...")
    
    # Find BLE dongle ports
    dongle_ports = find_ble_dongle_ports()
    
    if not dongle_ports:
        print("No BLE dongle found. Checking USB ports...")
        # Try all USB ports (macOS/Linux only)
        if platform.system() != "Windows":
            all_usb = glob.glob("/dev/tty.*")
            dongle_ports = [p for p in all_usb if 'usb' in p.lower() or 'serial' in p.lower()]
    
    print(f"Found {len(dongle_ports)} potential dongle port(s):")
    for port in dongle_ports:
        print(f"  - {port}")
    
    # Try each dongle port without MAC address (let BrainFlow scan)
    for dongle_port in dongle_ports:
        print(f"\nTrying dongle port: {dongle_port}")
        print("  (Letting BrainFlow auto-detect Ganglion MAC address...)")
        print("  This may take 10-15 seconds...")
        
        try:
            params = BrainFlowInputParams()
            params.serial_port = dongle_port
            # Don't specify MAC - let BrainFlow scan for it
            
            board = BoardShim(BoardIds.GANGLION_BOARD, params)
            board.prepare_session()
            print(f"  ✅ Successfully connected via {dongle_port}!")
            print(f"  ✅ Ganglion auto-detected!")
            
            # Get the MAC address if possible
            board.release_session()
            
            return {
                "dongle_port": dongle_port,
                "mac_address": None,  # Auto-detected
                "method": "auto-detect"
            }
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "discovery" in error_msg.lower():
                print(f"  ⚠️  Timeout - Ganglion might not be powered on or in range")
            else:
                print(f"  ❌ Failed: {error_msg}")
            continue
    
    return None

def main():
    """Main auto-detection function"""
    print("=" * 60)
    print("Ganglion Auto-Detection")
    print("=" * 60)
    print()
    print("Make sure:")
    print("  1. Ganglion is powered on (LED blinking)")
    print("  2. BLE dongle is plugged in")
    print()
    
    result = auto_detect_ganglion()
    
    if result:
        print("\n" + "=" * 60)
        print("✅ Auto-detection successful!")
        print("=" * 60)
        print()
        print("Add to your .env file:")
        print(f"GANGLION_DONGLE_PORT={result['dongle_port']}")
        if result['mac_address']:
            print(f"GANGLION_MAC_ADDRESS={result['mac_address']}")
        else:
            print("# MAC address will be auto-detected")
        print()
    else:
        print("\n" + "=" * 60)
        print("❌ Auto-detection failed")
        print("=" * 60)
        print()
        print("Options:")
        print("  1. Make sure Ganglion is powered on")
        print("  2. Make sure BLE dongle is plugged in")
        print("  3. Try manually:")
        if platform.system() != "Windows":
            print("     - Find dongle port: ls /dev/tty.usb*")
        else:
            print("     - Check Device Manager for COM ports")
        print("     - Find Ganglion MAC: Use OpenBCI GUI or nRF Connect app")
        print("     - Add to .env file:")
        print("       GANGLION_DONGLE_PORT=/dev/tty.usbserial-XXXXX")
        print("       GANGLION_MAC_ADDRESS=00:A0:C9:14:C8:29")
        print()

if __name__ == "__main__":
    main()

