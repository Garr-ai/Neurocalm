"""
EEG Service using BrainFlow to read from OpenBCI
"""
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
from brainflow.data_filter import DataFilter, FilterTypes, AggOperations
import numpy as np
import asyncio
from typing import Optional, Callable

class EEGService:
    """Service to handle EEG data collection from OpenBCI"""
    
    def __init__(self, board_id: int = BoardIds.SYNTHETIC_BOARD):
        """
        Initialize EEG service
        For OpenBCI Ganglion, use BoardIds.GANGLION_BOARD
        For OpenBCI Cyton, use BoardIds.CYTON_BOARD
        For testing/simulation, use BoardIds.SYNTHETIC_BOARD
        """
        self.board_id = board_id
        self.board = None
        self.is_streaming = False
        self.data_callback: Optional[Callable] = None
        self.mental_state_mode = "normal"  # Options: "calm", "stressed", "normal"
        self._update_counter = 0  # Counter to ensure values change each call
        
    def connect(self, serial_port: Optional[str] = None, mac_address: Optional[str] = None, dongle_port: Optional[str] = None):
        """Connect to the board
        
        For Ganglion board:
        - Bluetooth (direct): Provide mac_address (e.g., "00:A0:C9:14:C8:29")
        - Bluetooth via BLE dongle: Provide mac_address AND dongle_port
        - USB: Provide serial_port (e.g., "/dev/ttyUSB0" on Linux, "/dev/tty.usbserial-*" on macOS)
        
        For BLE dongle (BLED112):
        - dongle_port: Serial port of the BLE dongle (e.g., "/dev/tty.usbserial-XXXXX")
        - mac_address: MAC address of the Ganglion board itself
        """
        params = BrainFlowInputParams()
        if serial_port:
            params.serial_port = serial_port
        if mac_address:
            params.mac_address = mac_address
        if dongle_port:
            # For BLE dongle, the dongle port is specified as serial_port
            # and the Ganglion MAC is specified as mac_address
            params.serial_port = dongle_port
        
        self.board = BoardShim(self.board_id, params)
        self.board.prepare_session()
        
    def disconnect(self):
        """Disconnect from the board"""
        if self.board:
            self.board.release_session()
            self.board = None
            self.is_streaming = False
    
    def start_streaming(self, callback: Callable):
        """Start streaming EEG data"""
        if not self.board:
            raise RuntimeError("Board not connected. Call connect() first.")
        
        if self.is_streaming:
            print("[WARNING] Board is already streaming, stopping first...")
            self.stop_streaming()
        
        self.data_callback = callback
        try:
            self.board.start_stream()
            self.is_streaming = True
        except Exception as e:
            print(f"[ERROR] Failed to start stream: {e}")
            self.is_streaming = False
            raise
    
    def stop_streaming(self):
        """Stop streaming EEG data"""
        if self.board and self.is_streaming:
            self.board.stop_stream()
            self.is_streaming = False
    
    def get_raw_channels(self) -> Optional[dict]:
        """
        Get raw channel data from all EEG channels
        Returns: { channel_1, channel_2, channel_3, channel_4 } in microvolts
        
        For synthetic board: Adjusts raw voltages based on mental_state_mode to make them realistic
        For real hardware: Returns actual measured voltages
        """
        if not self.board or not self.is_streaming:
            return None
        
        try:
            board_data = self.board.get_board_data()
        except Exception as e:
            print(f"[RAW] Error getting board data: {e}")
            return None
        
        if board_data is None or len(board_data.shape) < 2:
            return None
        
        num_samples = board_data.shape[1]
        if num_samples == 0:
            return None
        
        # Get EEG channels
        eeg_channels = BoardShim.get_eeg_channels(self.board_id)
        if len(eeg_channels) == 0:
            return None
        
        # Get the last sample from each channel (most recent value)
        channel_values = {}
        import time
        base_time = time.time()
        
        for i in range(min(4, len(eeg_channels))):
            channel_idx = eeg_channels[i]
            if channel_idx < board_data.shape[0]:
                # Get base value from board data
                base_value = float(board_data[channel_idx, -1])
                
                # For synthetic board, apply mode-based adjustments to make voltages realistic
                # This simulates how different mental states would affect the raw EEG signal
                if self.board_id == BoardIds.SYNTHETIC_BOARD:
                    # Add mode-specific characteristics to the raw voltages
                    # Each mode has different frequency characteristics that affect voltage patterns
                    
                    if self.mental_state_mode == "calm":
                        # Calm state: More alpha-like patterns (8-13 Hz = slower oscillations)
                        # Alpha waves are larger amplitude (10-50 µV) and slower
                        # Add slower, larger amplitude variations
                        alpha_pattern = 15.0 * np.sin(base_time * 10.0)  # ~10 Hz (alpha range)
                        channel_offset = (i + 1) * 5.0  # Different baseline per channel
                        adjusted_value = base_value * 0.7 + alpha_pattern + channel_offset + np.random.uniform(-5, 5)
                        # Calm state: voltages tend to be more stable, less chaotic
                        adjusted_value = np.clip(adjusted_value, -50, 80)  # Realistic calm range
                        
                    elif self.mental_state_mode == "stressed":
                        # Stressed state: More beta/gamma-like patterns (13-30+ Hz = faster oscillations)
                        # Beta/gamma waves are smaller amplitude but faster
                        # Add faster, higher frequency variations
                        beta_pattern = 8.0 * np.sin(base_time * 20.0)  # ~20 Hz (beta range)
                        gamma_pattern = 5.0 * np.sin(base_time * 40.0)  # ~40 Hz (gamma range)
                        channel_offset = (i + 1) * 3.0  # Different baseline per channel
                        adjusted_value = base_value * 1.2 + beta_pattern + gamma_pattern + channel_offset + np.random.uniform(-8, 8)
                        # Stressed state: voltages are more variable, higher frequency content
                        adjusted_value = np.clip(adjusted_value, -60, 90)  # Slightly wider range for stress
                        
                    else:  # normal
                        # Normal state: Balanced mix of frequencies
                        # Mix of alpha, beta, and some gamma
                        alpha_component = 10.0 * np.sin(base_time * 10.0)  # Alpha
                        beta_component = 6.0 * np.sin(base_time * 20.0)  # Beta
                        theta_component = 8.0 * np.sin(base_time * 6.0)  # Theta
                        channel_offset = (i + 1) * 4.0  # Different baseline per channel
                        adjusted_value = base_value + alpha_component * 0.5 + beta_component * 0.5 + theta_component * 0.3 + channel_offset + np.random.uniform(-6, 6)
                        # Normal state: Moderate variation
                        adjusted_value = np.clip(adjusted_value, -55, 85)  # Balanced range
                    
                    channel_values[f"channel_{i+1}"] = float(adjusted_value)
                else:
                    # For real hardware, return actual measured values
                    channel_values[f"channel_{i+1}"] = base_value
        
        return channel_values if channel_values else None
    
    def set_mental_state_mode(self, mode: str):
        """Set the mental state mode for synthetic data generation
        Options: "calm", "stressed", "normal"
        """
        if mode in ["calm", "stressed", "normal"]:
            self.mental_state_mode = mode
            print(f"[EEG] Mental state mode set to: {mode}")
        else:
            print(f"[WARNING] Invalid mental state mode: {mode}. Using 'normal'")
            self.mental_state_mode = "normal"
    
    def get_bandpowers(self, window_seconds: int = 1) -> dict:
        """
        Calculate band powers from recent EEG data
        Returns: { alpha, beta, theta, gamma, calm_score, stressed_score, normal_score }
        """
        # Increment counter ONCE at the start to ensure values change every call
        if self.board_id == BoardIds.SYNTHETIC_BOARD:
            self._update_counter += 1
        
        if not self.board or not self.is_streaming:
            if not self.board:
                print(f"[BANDPOWERS] No board connected")
            if not self.is_streaming:
                print(f"[BANDPOWERS] Not streaming (is_streaming={self.is_streaming})")
            return None
        
        # Get board data
        try:
            board_data = self.board.get_board_data()
        except Exception as e:
            print(f"[BANDPOWERS] Error getting board data: {e}")
            return None
        
        # Check data shape
        if len(board_data.shape) < 2:
            print(f"[BANDPOWERS] Invalid data shape: {board_data.shape}")
            return None
        
        num_samples = board_data.shape[1]
        # Minimum samples needed for reliable FFT analysis
        # For synthetic board, use fewer samples to get faster updates
        min_samples = 25 if self.board_id == BoardIds.SYNTHETIC_BOARD else 50
        
        if num_samples < min_samples:
            # For synthetic board, return dummy values that match the mode if we don't have enough samples yet
            # BUT use counter to ensure values fluctuate
            if self.board_id == BoardIds.SYNTHETIC_BOARD:
                import time
                counter = self._update_counter  # Counter already incremented at function start
                base_time = time.time()
                
                # Return mode-appropriate values WITH variation
                if self.mental_state_mode == "calm":
                    # Calm mode: Realistic ranges based on EEG research
                    # Calm states: High alpha (40%), low beta+gamma (35%)
                    calm_var = 5.0 * np.sin(counter * 0.3) + np.random.uniform(-3, 3)
                    stressed_var = 3.0 * np.cos(counter * 0.4) + np.random.uniform(-2, 2)
                    normal_var = 4.0 * np.sin(counter * 0.35) + np.random.uniform(-2, 2)
                    return {
                        "calm_score": round(np.clip(75.0 + calm_var, 65, 85), 1),  # High calm (realistic for meditative states)
                        "stressed_score": round(np.clip(17.0 + stressed_var, 10, 25), 1),  # Low stress
                        "normal_score": round(np.clip(52.0 + normal_var, 45, 60), 1),  # Moderate normal
                        "mental_state_mode": "calm",
                        "alpha": 40.0,  # High alpha (calm state characteristic)
                        "beta": 20.0,   # Low beta
                        "theta": 25.0,  # Moderate theta
                        "gamma": 15.0   # Low gamma
                    }
                elif self.mental_state_mode == "stressed":
                    # Stressed mode: Realistic ranges based on EEG research
                    # Stressed states: High beta+gamma (70%), low alpha (15%)
                    calm_var = 5.0 * np.sin(counter * 0.5) + np.random.uniform(-4, 4)
                    stressed_var = 6.0 * np.cos(counter * 0.6) + np.random.uniform(-5, 5)
                    normal_var = 4.0 * np.sin(counter * 0.45) + np.random.uniform(-3, 3)
                    return {
                        "calm_score": round(np.clip(22.0 + calm_var, 15, 30), 1),  # Low calm
                        "stressed_score": round(np.clip(77.0 + stressed_var, 70, 85), 1),  # High stress (realistic for alert/stressed states)
                        "normal_score": round(np.clip(37.0 + normal_var, 30, 45), 1),  # Low normal
                        "mental_state_mode": "stressed",
                        "alpha": 15.0,  # Low alpha (stressed state characteristic)
                        "beta": 35.0,   # High beta
                        "theta": 15.0,  # Low theta
                        "gamma": 35.0   # High gamma
                    }
                else:  # normal
                    # Normal mode: Realistic ranges based on EEG research
                    # Normal/baseline states: Balanced bands (25% each approximately)
                    calm_var = 6.0 * np.sin(counter * 0.4) + 4.0 * np.cos(counter * 0.6) + np.random.uniform(-6, 6)
                    stressed_var = 6.0 * np.cos(counter * 0.45) + 4.0 * np.sin(counter * 0.65) + np.random.uniform(-6, 6)
                    normal_var = 5.0 * np.sin(counter * 0.42) + 4.0 * np.cos(counter * 0.58) + np.random.uniform(-6, 6)
                    return {
                        "calm_score": round(np.clip(47.0 + calm_var, 40, 55), 1),  # Moderate calm (balanced state)
                        "stressed_score": round(np.clip(47.0 + stressed_var, 40, 55), 1),  # Moderate stress (balanced state)
                        "normal_score": round(np.clip(77.0 + normal_var, 70, 85), 1),  # High normal (balanced = normal)
                        "mental_state_mode": "normal",
                        "alpha": 25.0,  # Balanced alpha
                        "beta": 27.0,   # Balanced beta
                        "theta": 25.0,  # Balanced theta
                        "gamma": 23.0   # Balanced gamma
                    }
            return None
        
        # Get EEG channels and sampling rate
        eeg_channels = BoardShim.get_eeg_channels(self.board_id)
        sampling_rate = BoardShim.get_sampling_rate(self.board_id)
        
        if len(eeg_channels) == 0:
            print(f"[WARNING] No EEG channels found for board_id={self.board_id}")
            return None
        
        # For synthetic board, generate mode-specific voltage patterns for FFT analysis
        # For real hardware, use actual measured data
        try:
            if self.board_id == BoardIds.SYNTHETIC_BOARD:
                # Generate mode-specific voltage patterns that match frequency characteristics
                # This ensures the FFT analysis reflects the mental state mode
                import time
                current_time = time.time()
                num_samples_needed = int(sampling_rate * window_seconds)
                if num_samples_needed > num_samples:
                    num_samples_needed = num_samples
                if num_samples_needed < 10:
                    num_samples_needed = 10
                
                # Generate time points for signal generation
                time_points = np.linspace(current_time - window_seconds, current_time, num_samples_needed)
                
                if self.mental_state_mode == "calm":
                    # Calm: Dominant alpha waves (8-13 Hz), larger amplitude
                    # Alpha is ~10 Hz, amplitude 15-30 µV
                    eeg_data = (
                        25.0 * np.sin(2 * np.pi * 10.0 * time_points) +  # Alpha (10 Hz) - dominant
                        8.0 * np.sin(2 * np.pi * 20.0 * time_points) +   # Some beta (20 Hz) - low
                        12.0 * np.sin(2 * np.pi * 6.0 * time_points) +   # Some theta (6 Hz)
                        5.0 * np.sin(2 * np.pi * 35.0 * time_points) +   # Minimal gamma (35 Hz) - low
                        np.random.uniform(-5, 5, num_samples_needed)      # Noise
                    )
                elif self.mental_state_mode == "stressed":
                    # Stressed: Dominant beta/gamma waves (13-30+ Hz), smaller amplitude but faster
                    # Beta is ~20 Hz, gamma is ~40 Hz, amplitude 5-15 µV
                    eeg_data = (
                        8.0 * np.sin(2 * np.pi * 10.0 * time_points) +   # Reduced alpha (10 Hz) - low
                        20.0 * np.sin(2 * np.pi * 20.0 * time_points) +  # Beta (20 Hz) - dominant
                        6.0 * np.sin(2 * np.pi * 6.0 * time_points) +    # Reduced theta (6 Hz) - low
                        18.0 * np.sin(2 * np.pi * 40.0 * time_points) +  # Gamma (40 Hz) - dominant
                        np.random.uniform(-8, 8, num_samples_needed)      # More noise (stress)
                    )
                else:  # normal
                    # Normal: Balanced mix of all frequencies
                    # Balanced amplitudes across all bands
                    eeg_data = (
                        15.0 * np.sin(2 * np.pi * 10.0 * time_points) +  # Alpha (10 Hz) - balanced
                        15.0 * np.sin(2 * np.pi * 20.0 * time_points) +  # Beta (20 Hz) - balanced
                        12.0 * np.sin(2 * np.pi * 6.0 * time_points) +   # Theta (6 Hz) - balanced
                        10.0 * np.sin(2 * np.pi * 35.0 * time_points) +  # Gamma (35 Hz) - balanced
                        np.random.uniform(-6, 6, num_samples_needed)      # Moderate noise
                    )
                
                # Use this generated data for FFT analysis
                eeg_data_for_fft = eeg_data
            else:
                # For real hardware, use actual measured data
                eeg_data = board_data[eeg_channels[0]]
                eeg_data_for_fft = eeg_data
                
        except (IndexError, KeyError) as e:
            print(f"[ERROR] Failed to get EEG data from channel {eeg_channels[0]}: {e}")
            print(f"[DEBUG] board_data.shape={board_data.shape}, eeg_channels={eeg_channels}")
            return None
        
        # Calculate band powers using FFT (more reliable than PSD for variable sample sizes)
        try:
            # Ensure data length is even for FFT
            if len(eeg_data_for_fft) % 2 != 0:
                eeg_data_for_fft = eeg_data_for_fft[:-1]
            
            if len(eeg_data_for_fft) < 4:
                raise ValueError("Insufficient data for FFT")
            
            # Use FFT to get frequency domain
            fft_vals = np.fft.rfft(eeg_data_for_fft)
            fft_freq = np.fft.rfftfreq(len(eeg_data_for_fft), 1.0/sampling_rate)
            fft_power = np.abs(fft_vals) ** 2
            
            # Normalize power by length to get power spectral density
            fft_power = fft_power / len(eeg_data_for_fft)
            
            # Extract band powers by integrating power in frequency ranges
            def get_band_power_fft(freqs, power, start_freq, stop_freq):
                mask = (freqs >= start_freq) & (freqs <= stop_freq)
                if np.any(mask):
                    # Integrate power over frequency range
                    return np.trapz(power[mask], freqs[mask])
                return 0.0
            
            alpha = get_band_power_fft(fft_freq, fft_power, 8.0, 13.0)
            beta = get_band_power_fft(fft_freq, fft_power, 13.0, 30.0)
            theta = get_band_power_fft(fft_freq, fft_power, 4.0, 8.0)
            gamma = get_band_power_fft(fft_freq, fft_power, 30.0, 100.0)
            
            # Ensure we have valid values
            if not all(np.isfinite([alpha, beta, theta, gamma])):
                raise ValueError("Invalid band power values")
                
        except Exception as e:
            print(f"[ERROR] Error calculating band powers: {e}")
            # For synthetic board, return mode-based values on error
            if self.board_id == BoardIds.SYNTHETIC_BOARD:
                import time
                base_time = time.time() * 0.5
                if self.mental_state_mode == "calm":
                    alpha, beta, theta, gamma = 50.0, 15.0, 25.0, 10.0
                elif self.mental_state_mode == "stressed":
                    alpha, beta, theta, gamma = 15.0, 45.0, 15.0, 25.0
                else:  # normal
                    alpha, beta, theta, gamma = 30.0, 30.0, 25.0, 15.0
                # Add variation
                alpha += 5 * np.sin(base_time)
                beta += 5 * np.cos(base_time * 0.9)
                theta += 3 * np.sin(base_time * 0.8)
                gamma += 3 * np.cos(base_time * 0.7)
            else:
                # Fallback: return dummy values so data flow continues
                alpha = 1.0
                beta = 1.0
                theta = 1.0
                gamma = 1.0
        
        # Calculate scores based on mental state mode
        total_power = alpha + beta + theta + gamma
        
        # For synthetic board, always ensure we have data
        if self.board_id == BoardIds.SYNTHETIC_BOARD and total_power == 0:
            # Use mode-based default values
            import time
            base_time = time.time() * 0.5
            if self.mental_state_mode == "calm":
                alpha, beta, theta, gamma = 50.0, 15.0, 25.0, 10.0
            elif self.mental_state_mode == "stressed":
                alpha, beta, theta, gamma = 15.0, 45.0, 15.0, 25.0
            else:  # normal
                alpha, beta, theta, gamma = 30.0, 30.0, 25.0, 15.0
            # Add variation
            alpha += 5 * np.sin(base_time)
            beta += 5 * np.cos(base_time * 0.9)
            theta += 3 * np.sin(base_time * 0.8)
            gamma += 3 * np.cos(base_time * 0.7)
            total_power = alpha + beta + theta + gamma
        
        if total_power == 0:
            return None
        
        # Normalize band powers to percentages (0-100)
        alpha_pct = (alpha / (total_power + 1e-10)) * 100
        beta_pct = (beta / (total_power + 1e-10)) * 100
        theta_pct = (theta / (total_power + 1e-10)) * 100
        gamma_pct = (gamma / (total_power + 1e-10)) * 100
        
        # Calculate scores from band powers (same logic for both synthetic and real hardware)
        # The FFT analysis was performed on mode-specific voltage patterns for synthetic board
        # For real hardware, band powers come from actual FFT analysis of measured voltages
        # Based on EEG research:
        # - Calm: Alpha dominant (30-50%), low beta/gamma
        # - Stressed: Beta/gamma dominant (30-50%), alpha suppressed
        # - Normal: Balanced distribution (all bands 20-35%)
        
        # Calm score: Based on alpha dominance relative to other bands
        # Alpha typically 30-50% in calm states, with low beta/gamma
        alpha_ideal = 40.0  # Ideal alpha percentage for calm state
        beta_gamma_combined = beta_pct + gamma_pct
        # Higher alpha and lower beta+gamma = higher calm score
        # Calm score peaks when alpha is high (30-50%) and beta+gamma is low (<30%)
        calm_from_alpha = np.clip((alpha_pct / alpha_ideal) * 50, 0, 50) if alpha_pct > 0 else 0
        calm_from_low_stress = np.clip((1 - (beta_gamma_combined / 50)) * 50, 0, 50) if beta_gamma_combined < 50 else 0
        calm_score = np.clip((calm_from_alpha + calm_from_low_stress) / 2, 0, 100)
        
        # Stressed score: Based on beta+gamma dominance and alpha suppression
        # Beta+gamma typically 30-50% in stressed states, alpha <20%
        beta_gamma_ideal = 40.0  # Ideal beta+gamma percentage for stressed state
        # Higher beta+gamma and lower alpha = higher stressed score
        stress_from_beta_gamma = np.clip((beta_gamma_combined / beta_gamma_ideal) * 50, 0, 50) if beta_gamma_combined > 0 else 0
        stress_from_low_alpha = np.clip((1 - (alpha_pct / 30)) * 50, 0, 50) if alpha_pct < 30 else 0
        stressed_score = np.clip((stress_from_beta_gamma + stress_from_low_alpha) / 2, 0, 100)
        
        # Normal score: Based on balanced distribution of all bands
        # Normal/baseline state has relatively balanced bands (20-35% each)
        # Calculate how close the distribution is to ideal balance (25% each)
        ideal_bands = np.array([25.0, 25.0, 25.0, 25.0])  # Ideal: 25% each
        actual_bands = np.array([alpha_pct, beta_pct, theta_pct, gamma_pct])
        # Calculate distance from ideal (lower distance = more normal)
        band_distances = np.abs(actual_bands - ideal_bands)
        max_distance = 25.0  # Maximum possible distance (0% to 50%)
        normalized_distance = np.mean(band_distances) / max_distance
        # Normal score is inverse of distance (closer to balance = higher score)
        normal_score = np.clip((1 - normalized_distance) * 100, 0, 100)
        
        # Round to 1 decimal place for cleaner display (but ensure values are different)
        calm_score_final = round(float(np.clip(calm_score, 0, 100)), 1)
        stressed_score_final = round(float(np.clip(stressed_score, 0, 100)), 1)
        normal_score_final = round(float(np.clip(normal_score, 0, 100)), 1)
        
        print(f"[SCORES] Counter={self._update_counter}, Mode={self.mental_state_mode}")
        print(f"[SCORES] Calm={calm_score_final:.1f}, Stressed={stressed_score_final:.1f}, Normal={normal_score_final:.1f}")
        print(f"[SCORES] Raw: Calm={calm_score:.2f}, Stressed={stressed_score:.2f}, Normal={normal_score:.2f}")
        
        return {
            "alpha": float(alpha),
            "beta": float(beta),
            "theta": float(theta),
            "gamma": float(gamma),
            "calm_score": calm_score_final,
            "stressed_score": stressed_score_final,
            "normal_score": normal_score_final,
            "mental_state_mode": self.mental_state_mode
        }
    
    async def stream_loop(self):
        """Async loop to continuously stream and process EEG data"""
        consecutive_none_count = 0
        loop_count = 0
        data_sent_count = 0
        print(f"[STREAM] Starting stream loop (board_id={self.board_id}, is_streaming={self.is_streaming}, mode={self.mental_state_mode})")
        
        # Brief initial wait for board to start collecting data
        await asyncio.sleep(0.3)
        
        while self.is_streaming:
            try:
                loop_count += 1
                
                # Get both raw channel data and mental state scores
                raw_channels = self.get_raw_channels()
                mental_state = self.get_bandpowers()
                
                # Combine both datasets - always send raw channels, mental state might be None initially
                if raw_channels and self.data_callback:
                    combined_data = {
                        "raw_channels": raw_channels,
                        "mental_state": mental_state  # Can be None if not enough samples yet (will return dummy values for synthetic board)
                    }
                    
                    consecutive_none_count = 0
                    data_sent_count += 1
                    # Log more frequently to verify scores are changing
                    if data_sent_count <= 5 or data_sent_count % 10 == 0:
                        if mental_state:
                            print(f"[STREAM] Sending data #{data_sent_count} - Mode: {self.mental_state_mode}, Calm: {mental_state.get('calm_score', 0):.1f}, Stressed: {mental_state.get('stressed_score', 0):.1f}, Normal: {mental_state.get('normal_score', 0):.1f}")
                        else:
                            print(f"[STREAM] Sending data #{data_sent_count} (raw only, waiting for mental state)")
                    await self.data_callback(combined_data)
                else:
                    consecutive_none_count += 1
                    # Only log waiting message on first attempt
                    if consecutive_none_count == 1:
                        print(f"[STREAM] Waiting for EEG data...")
                    elif consecutive_none_count == 10:
                        # Check what's happening after a few attempts
                        if self.board:
                            try:
                                data = self.board.get_board_data()
                                num_samples = data.shape[1] if len(data.shape) > 1 else 0
                                print(f"[STREAM] Board data: {num_samples} samples")
                            except Exception as e:
                                print(f"[STREAM] Error checking board data: {e}")
                        consecutive_none_count = 0  # Reset to avoid spam
                
                # Update every 0.2 seconds for faster mental state updates (5 updates per second)
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"[STREAM] Error in stream loop #{loop_count}: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(0.5)
        
        print(f"[STREAM] Stream loop ended (is_streaming={self.is_streaming})")
