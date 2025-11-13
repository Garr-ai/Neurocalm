"""
Simulate raw OpenBCI EEG data using BrainFlow's synthetic board.
Outputs data in the exact format that OpenBCI Ganglion hardware outputs.
OpenBCI Ganglion format: CSV with Sample Index, Channel 1-4 (µV), optional accelerometer
"""
import sys
import time
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
import numpy as np

def simulate_raw_eeg():
    """Simulate raw EEG data from OpenBCI in native format"""
    print("=" * 60)
    print("OpenBCI Ganglion Raw Data Simulator")
    print("=" * 60)
    print()
    print("Simulating OpenBCI Ganglion output format...")
    print("Format: Sample Index, Channel 1 (µV), Channel 2 (µV), Channel 3 (µV), Channel 4 (µV)")
    print("Press Ctrl+C to stop")
    print()
    
    # Use synthetic board for simulation (matches Ganglion specs)
    board_id = BoardIds.SYNTHETIC_BOARD
    params = BrainFlowInputParams()
    
    try:
        # Initialize board
        board = BoardShim(board_id, params)
        
        # Get board specifications
        sampling_rate = BoardShim.get_sampling_rate(board_id)
        eeg_channels = BoardShim.get_eeg_channels(board_id)
        num_channels = BoardShim.get_num_rows(board_id)
        
        print(f"Sampling Rate: {sampling_rate} Hz")
        print(f"EEG Channels: {len(eeg_channels)}")
        print(f"Channel Indices: {eeg_channels.tolist() if hasattr(eeg_channels, 'tolist') else list(eeg_channels)}")
        print()
        
        # Prepare session
        board.prepare_session()
        print("[OK] Board session prepared")
        
        # Start streaming
        board.start_stream()
        print("[OK] Streaming started")
        print()
        
        # Print OpenBCI-style CSV header (matches OpenBCI GUI/Serial format)
        # OpenBCI Ganglion outputs: Sample Index, Ch1, Ch2, Ch3, Ch4
        header_parts = ["Sample Index"]
        for i in range(min(4, len(eeg_channels))):  # Ganglion has 4 EEG channels
            header_parts.append(f"Channel {i+1} (µV)")
        
        print(",".join(header_parts))
        print("-" * 80)
        print()
        
        # Wait a moment for initial data to accumulate
        time.sleep(0.5)
        
        sample_count = 0
        
        try:
            while True:
                # Get board data - this clears the buffer, so we get all accumulated samples
                data = board.get_board_data()
                
                if data is not None and len(data.shape) == 2:
                    num_samples = data.shape[1]
                    
                    if num_samples > 0:
                        # Output each sample in OpenBCI format
                        # OpenBCI outputs samples sequentially, one per line
                        for sample_idx in range(num_samples):
                            sample_count += 1
                            
                            # Format: Sample Index, Channel1, Channel2, Channel3, Channel4
                            # This matches OpenBCI Ganglion's native CSV output format
                            row_parts = [str(sample_count)]
                            
                            # Add EEG channel values (in microvolts, 6 decimal places)
                            # OpenBCI Ganglion has 4 EEG channels
                            for i in range(min(4, len(eeg_channels))):
                                channel_idx = eeg_channels[i]
                                if channel_idx < data.shape[0]:
                                    # Get value for this sample
                                    value = data[channel_idx, sample_idx]
                                    # Format with 6 decimal places (OpenBCI precision)
                                    row_parts.append(f"{value:.6f}")
                            
                            # Print the row (matches OpenBCI serial/CSV output)
                            print(",".join(row_parts))
                        
                        # After processing all samples, wait for new data to accumulate
                        # Sleep for about 0.1 seconds to let samples accumulate
                        # At 250 Hz, that's about 25 samples
                        time.sleep(0.1)
                    else:
                        # No samples yet, wait a bit
                        time.sleep(0.1)
                else:
                    # No data yet, wait a bit
                    time.sleep(0.1)
                
        except KeyboardInterrupt:
            print()
            print("\n[STOPPED] Stopping stream...")
        
        # Stop streaming
        board.stop_stream()
        print("[OK] Streaming stopped")
        
        # Release session
        board.release_session()
        print("[OK] Session released")
        print()
        print(f"Total samples output: {sample_count}")
        print(f"Output rate: {sampling_rate} Hz (matches OpenBCI Ganglion)")
        print("Simulation completed")
        
    except Exception as e:
        print(f"[ERROR] Failed to simulate EEG data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    simulate_raw_eeg()
