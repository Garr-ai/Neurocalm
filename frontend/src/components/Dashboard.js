import React, { useState, useEffect, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './Dashboard.css';

// Encouraging messages array
const ENCOURAGING_MESSAGES = [
  "Great job! You're doing well. Keep breathing and stay calm.",
  "You've got this! Your stress levels are improving.",
  "Excellent! You're feeling more relaxed now.",
  "Wonderful! Take a moment to appreciate your calm state.",
  "You're doing amazing! Your breathing is helping you find peace.",
  "Perfect! You've successfully calmed yourself down.",
  "Fantastic! You're in control and feeling better.",
  "Well done! Your stress has decreased. Keep up the great work!"
];

const Dashboard = ({ currentUser }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [mentalStateMode, setMentalStateMode] = useState('normal'); // calm, stressed, normal
  const [voltageData, setVoltageData] = useState([]);
  const [mentalStateData, setMentalStateData] = useState([]);
  const [ws, setWs] = useState(null);
  const [voltageScores, setVoltageScores] = useState({
    channel1: 0,
    channel2: 0,
    channel3: 0,
    channel4: 0
  });
  const [mentalStateScores, setMentalStateScores] = useState({
    calm: 0,
    stressed: 0,
    normal: 0
  });
  const [status, setStatus] = useState('Disconnected');
  const [error, setError] = useState(null);
  const [showBreathingExercise, setShowBreathingExercise] = useState(false);
  const [isTabFocused, setIsTabFocused] = useState(true);
  const [breathingPhase, setBreathingPhase] = useState('inhale'); // inhale, hold, exhale, pause
  const [breathingCycle, setBreathingCycle] = useState(0);
  const [encouragingMessage, setEncouragingMessage] = useState(null);
  const wasManuallyClosedRef = useRef(false);
  
  // Refs to track reconnection state
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptRef = useRef(0);
  const isConnectingRef = useRef(false);
  const wsRef = useRef(null);
  const reconnectIntervalRef = useRef(null);
  const breathingIntervalRef = useRef(null);
  const autoCloseTimerRef = useRef(null);
  const encouragingMessageTimerRef = useRef(null);
  
  // WebSocket URL
  const WS_URL = 'ws://localhost:8765';
  const RECONNECT_INTERVAL = 3000; // Try to reconnect every 3 seconds
  const MAX_RECONNECT_ATTEMPTS = Infinity; // Keep trying indefinitely

  const connectWebSocket = () => {
    // Don't create multiple connections
    if (isConnectingRef.current || (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING)) {
      console.log('[WS] Connection attempt already in progress, skipping...');
      return;
    }
    
    // Close existing connection if any
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {
        console.log('[WS] Error closing existing connection:', e);
      }
      wsRef.current = null;
    }
    
    isConnectingRef.current = true;
    console.log(`[WS] Attempting to connect to ${WS_URL}... (Attempt ${reconnectAttemptRef.current + 1})`);
    setStatus('Connecting...');
    setError(null);
    
    try {
      const websocket = new WebSocket(WS_URL);
      wsRef.current = websocket;
      
      websocket.onopen = () => {
        console.log('✅ WebSocket CONNECTED');
        isConnectingRef.current = false;
        reconnectAttemptRef.current = 0; // Reset attempts on successful connection
        setWs(websocket);
        setStatus('Connected');
        setError(null);
        // Reset recording state - will be updated by state_sync message
        setIsRecording(false);
        
        // Clear any reconnection timers
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };

      websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('=== MESSAGE RECEIVED ===', message.type, message);
          
          if (message.type === 'eeg_data') {
            // Handle both raw channel data and mental state data
            const rawChannels = message.raw_channels;
            const mentalState = message.mental_state;
            
            if (rawChannels) {
              // Update voltage data
              const voltagePoint = {
                time: new Date(message.timestamp).toLocaleTimeString(),
                channel1: rawChannels.channel_1 || 0,
                channel2: rawChannels.channel_2 || 0,
                channel3: rawChannels.channel_3 || 0,
                channel4: rawChannels.channel_4 || 0
              };
              
              setVoltageScores({
                channel1: voltagePoint.channel1,
                channel2: voltagePoint.channel2,
                channel3: voltagePoint.channel3,
                channel4: voltagePoint.channel4
              });
              
              setVoltageData(prev => {
                const updated = [...prev.slice(-59), voltagePoint]; // Keep last 60 points
                return updated;
              });
            }
            
            // Always process mental state data if present (even if it's null, we might want to show loading state)
            if (mentalState && typeof mentalState === 'object') {
              // Update mental state data
              const mentalStatePoint = {
                time: new Date(message.timestamp).toLocaleTimeString(),
                calm: mentalState.calm_score || 0,
                stressed: mentalState.stressed_score || 0,
                normal: mentalState.normal_score || 0
              };
              
              setMentalStateScores({
                calm: mentalStatePoint.calm,
                stressed: mentalStatePoint.stressed,
                normal: mentalStatePoint.normal
              });
              
              setMentalStateData(prev => {
                const updated = [...prev.slice(-59), mentalStatePoint]; // Keep last 60 points
                return updated;
              });
              
              // Update mental state mode if provided
              if (mentalState.mental_state_mode) {
                setMentalStateMode(mentalState.mental_state_mode);
              }
            }
          } else if (message.type === 'mental_state_changed') {
            setMentalStateMode(message.mode || 'normal');
          } else if (message.type === 'recording_started') {
            setStatus('Recording...');
            setError(null);
            setIsRecording(true);
          } else if (message.type === 'recording_stopped') {
            setStatus('Connected (Stopped)');
            setIsRecording(false);
          } else if (message.type === 'info') {
            // Show info messages (like "Using simulated dongle")
            console.log('Backend info:', message.message);
            setStatus(message.message);
            // Don't clear error if there is one, but update status
          } else if (message.type === 'error') {
            setError(message.message);
            setStatus('Error');
            setIsRecording(false);
            console.error('Backend error:', message.message);
          } else if (message.type === 'state_sync') {
            // Sync with backend state when connecting
            console.log('Syncing state with backend:', message);
            setIsRecording(message.is_recording || false);
            if (message.is_recording) {
              setStatus('Recording...');
            } else {
              setStatus('Connected');
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error, event.data);
        }
      };

      websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        isConnectingRef.current = false;
        // Don't set error state immediately - might be a temporary issue
        // The onclose handler will handle reconnection
      };

      websocket.onclose = (event) => {
        console.log('WebSocket disconnected', event.code, event.reason);
        isConnectingRef.current = false;
        setWs(null);
        wsRef.current = null;
        
        // Only set disconnected status if we're not already reconnecting
        if (!reconnectTimeoutRef.current) {
          setStatus('Disconnected');
          setError('Connection lost. Reconnecting...');
        }
        
        // Attempt to reconnect if we haven't exceeded max attempts
        if (reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptRef.current += 1;
          console.log(`[WS] Scheduling reconnection attempt ${reconnectAttemptRef.current} in ${RECONNECT_INTERVAL}ms...`);
          
          // Clear any existing timeout
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connectWebSocket();
          }, RECONNECT_INTERVAL);
        } else {
          console.error('[WS] Max reconnection attempts reached');
          setError('Failed to connect after multiple attempts. Please refresh the page.');
          setStatus('Connection Failed');
        }
      };
    } catch (error) {
      console.error('[WS] Error creating WebSocket:', error);
      isConnectingRef.current = false;
      setError(`Failed to create WebSocket connection: ${error.message}`);
      setStatus('Connection Error');
      
      // Schedule reconnection
      if (reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttemptRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = null;
          connectWebSocket();
        }, RECONNECT_INTERVAL);
      }
    }
  };

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().then(permission => {
        console.log('Notification permission:', permission);
      });
    }
  }, []);

  // Track tab visibility
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsTabFocused(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    setIsTabFocused(!document.hidden);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  // Auto-close breathing exercise and reduce stress after 15-20 seconds
  useEffect(() => {
    if (showBreathingExercise) {
      // Reset manual close flag when popup opens
      wasManuallyClosedRef.current = false;
      
      // Random time between 15-20 seconds (15000-20000 ms)
      const randomTime = Math.floor(Math.random() * 5000) + 15000;
      
      autoCloseTimerRef.current = setTimeout(() => {
        // Only proceed if popup wasn't manually closed
        if (!wasManuallyClosedRef.current) {
          // Change mental state to calm
          const currentWs = wsRef.current;
          if (currentWs && currentWs.readyState === WebSocket.OPEN) {
            try {
              console.log('Auto-changing mental state mode to: calm');
              currentWs.send(JSON.stringify({ type: 'set_mental_state', mode: 'calm' }));
            } catch (error) {
              console.error('Error sending mental state change:', error);
            }
          }
          
          // Close the popup
          setShowBreathingExercise(false);
          
          // Show encouraging message
          const randomMessage = ENCOURAGING_MESSAGES[Math.floor(Math.random() * ENCOURAGING_MESSAGES.length)];
          setEncouragingMessage(randomMessage);
          
          // Hide encouraging message after 5 seconds
          encouragingMessageTimerRef.current = setTimeout(() => {
            setEncouragingMessage(null);
          }, 5000);
        }
      }, randomTime);

      return () => {
        if (autoCloseTimerRef.current) {
          clearTimeout(autoCloseTimerRef.current);
          autoCloseTimerRef.current = null;
        }
        if (encouragingMessageTimerRef.current) {
          clearTimeout(encouragingMessageTimerRef.current);
          encouragingMessageTimerRef.current = null;
        }
      };
    } else {
      // Clear timers when popup is closed
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current);
        autoCloseTimerRef.current = null;
      }
      if (encouragingMessageTimerRef.current) {
        clearTimeout(encouragingMessageTimerRef.current);
        encouragingMessageTimerRef.current = null;
      }
    }
  }, [showBreathingExercise]);

  // Breathing exercise animation
  useEffect(() => {
    if (showBreathingExercise) {
      const phases = [
        { name: 'inhale', duration: 4000 },
        { name: 'hold', duration: 2000 },
        { name: 'exhale', duration: 4000 },
        { name: 'pause', duration: 2000 }
      ];

      let currentPhaseIndex = 0;
      let cycleCount = 1;

      const advancePhase = () => {
        currentPhaseIndex = (currentPhaseIndex + 1) % phases.length;
        
        if (currentPhaseIndex === 0) {
          // Completed a full cycle (inhale again)
          cycleCount++;
          setBreathingCycle(cycleCount);
        }
        
        setBreathingPhase(phases[currentPhaseIndex].name);
        
        // Schedule next phase change
        if (breathingIntervalRef.current) {
          clearTimeout(breathingIntervalRef.current);
        }
        
        breathingIntervalRef.current = setTimeout(() => {
          advancePhase();
        }, phases[currentPhaseIndex].duration);
      };

      // Start with inhale
      setBreathingPhase('inhale');
      setBreathingCycle(1);
      
      // Start the cycle
      breathingIntervalRef.current = setTimeout(() => {
        advancePhase();
      }, phases[0].duration);

      return () => {
        if (breathingIntervalRef.current) {
          clearTimeout(breathingIntervalRef.current);
          breathingIntervalRef.current = null;
        }
      };
    } else {
      // Reset breathing state when closed
      setBreathingPhase('inhale');
      setBreathingCycle(0);
      if (breathingIntervalRef.current) {
        clearTimeout(breathingIntervalRef.current);
        breathingIntervalRef.current = null;
      }
    }
  }, [showBreathingExercise]);

  // Periodic connection check - verify connection is still alive
  useEffect(() => {
    const checkConnection = () => {
      const currentWs = wsRef.current;
      
      // If we don't have a WebSocket or it's not open, try to connect
      if (!currentWs || currentWs.readyState !== WebSocket.OPEN) {
        // Only reconnect if we're not already connecting
        if (!isConnectingRef.current && !reconnectTimeoutRef.current) {
          console.log('[WS] Connection check failed - WebSocket not open. State:', currentWs ? currentWs.readyState : 'null');
          console.log('[WS] Attempting reconnection...');
          reconnectAttemptRef.current = 0; // Reset attempts for periodic check
          connectWebSocket();
        }
      }
      // Note: If connection is open, the status will be updated by onopen handler
    };
    
    // Check connection every 3 seconds (same as reconnect interval)
    reconnectIntervalRef.current = setInterval(checkConnection, 3000);
    
    // Initial connection
    connectWebSocket();
    
    // Cleanup function
    return () => {
      // Clear interval
      if (reconnectIntervalRef.current) {
        clearInterval(reconnectIntervalRef.current);
        reconnectIntervalRef.current = null;
      }
      
      // Clear reconnect timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      // Close WebSocket
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (e) {
          console.log('[WS] Error closing WebSocket on cleanup:', e);
        }
        wsRef.current = null;
      }
      
      // Clear breathing interval
      if (breathingIntervalRef.current) {
        clearTimeout(breathingIntervalRef.current);
        breathingIntervalRef.current = null;
      }
      
      // Clear auto-close timer
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current);
        autoCloseTimerRef.current = null;
      }
      
      // Clear encouraging message timer
      if (encouragingMessageTimerRef.current) {
        clearTimeout(encouragingMessageTimerRef.current);
        encouragingMessageTimerRef.current = null;
      }
      
      isConnectingRef.current = false;
    };
  }, []); // Empty dependency array - only run on mount/unmount

  const toggleStreaming = () => {
    const currentWs = wsRef.current;
    
    if (!currentWs) {
      const errorMsg = 'WebSocket is not connected. Attempting to connect...';
      console.error(errorMsg);
      setError(errorMsg);
      setStatus('Connecting...');
      connectWebSocket();
      return;
    }
    
    if (currentWs.readyState !== WebSocket.OPEN) {
      const states = {
        0: 'CONNECTING',
        1: 'OPEN',
        2: 'CLOSING',
        3: 'CLOSED'
      };
      const errorMsg = `WebSocket not open. Current state: ${states[currentWs.readyState] || currentWs.readyState}. Attempting to reconnect...`;
      console.error(errorMsg);
      setError(errorMsg);
      setStatus('Connecting...');
      connectWebSocket();
      return;
    }
    
    if (isRecording) {
      // Stop streaming
      console.log('Stopping stream...');
      currentWs.send(JSON.stringify({ type: 'stop_recording' }));
      setStatus('Stopping...');
    } else {
      // Start streaming
      console.log('Starting stream...');
      currentWs.send(JSON.stringify({ type: 'start_recording' }));
      setStatus('Starting...');
      setError(null);
    }
  };

  const showNotification = () => {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification('NeuroCalm - Time for a Calming Exercise', {
        body: 'You\'re feeling stressed. Take a moment to focus on your breathing and find calm.',
        icon: '/favicon.ico',
        tag: 'stress-alert',
        requireInteraction: false
      });
    } else if ('Notification' in window && Notification.permission === 'default') {
      // Request permission if not yet asked
      Notification.requestPermission().then(permission => {
        if (permission === 'granted') {
          new Notification('NeuroCalm - Time for a Calming Exercise', {
            body: 'You\'re feeling stressed. Take a moment to focus on your breathing and find calm.',
            icon: '/favicon.ico',
            tag: 'stress-alert',
            requireInteraction: false
          });
        }
      });
    }
  };

  const changeMentalStateMode = (mode) => {
    const currentWs = wsRef.current;
    
    if (!currentWs || currentWs.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not open, cannot change mental state mode. Attempting to reconnect...');
      setError('WebSocket not connected. Attempting to reconnect...');
      setStatus('Connecting...');
      connectWebSocket();
      return;
    }
    
    try {
      console.log(`Changing mental state mode to: ${mode}`);
      currentWs.send(JSON.stringify({ type: 'set_mental_state', mode }));
      
      // If stressed mode is selected, show notification or popup based on tab focus
      if (mode === 'stressed') {
        if (!isTabFocused) {
          // Tab is not focused - show notification
          showNotification();
        } else {
          // Tab is focused - show breathing exercise popup
          setShowBreathingExercise(true);
        }
      }
      // Don't update state immediately - wait for confirmation from server
    } catch (error) {
      console.error('Error sending mental state change:', error);
      setError(`Failed to change mental state: ${error.message}`);
    }
  };

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h2>Dashboard</h2>
        <div className="recording-controls">
          <div className="status-info">
            <span className={`status-indicator ${status.toLowerCase().replace(/\s+/g, '-')}`}>
              {status}
            </span>
            {error && <span className="error-message">{error}</span>}
          </div>
        <button 
          className={`button ${isRecording ? 'button-danger' : ''}`}
          onClick={toggleStreaming}
          disabled={!ws || ws.readyState !== WebSocket.OPEN}
        >
          {isRecording ? 'Stop' : 'Start'}
        </button>
        </div>
      </div>

      {/* Mental State Mode Selector */}
      <div style={{ margin: '20px 0', padding: '15px', background: '#f5f5f5', borderRadius: '8px' }}>
        <div style={{ marginBottom: '10px', fontWeight: 'bold', color: '#333' }}>
          Simulate Mental State:
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            className={`button ${mentalStateMode === 'calm' ? 'button-primary' : ''}`}
            onClick={() => changeMentalStateMode('calm')}
            disabled={!ws || (ws && ws.readyState !== WebSocket.OPEN)}
            style={{ flex: 1 }}
          >
            Calm
          </button>
          <button
            className={`button ${mentalStateMode === 'normal' ? 'button-primary' : ''}`}
            onClick={() => changeMentalStateMode('normal')}
            disabled={!ws || (ws && ws.readyState !== WebSocket.OPEN)}
            style={{ flex: 1 }}
          >
            Normal
          </button>
          <button
            className={`button ${mentalStateMode === 'stressed' ? 'button-primary' : ''}`}
            onClick={() => changeMentalStateMode('stressed')}
            disabled={!ws || (ws && ws.readyState !== WebSocket.OPEN)}
            style={{ flex: 1 }}
          >
            Stressed
          </button>
        </div>
        <div style={{ marginTop: '10px', fontSize: '14px', color: '#666' }}>
          Current Mode: <strong>{mentalStateMode}</strong>
        </div>
      </div>

      {/* Voltage Scores */}
      <div className="scores-grid">
        <div className="score-card">
          <div className="score-label">Channel 1 (µV)</div>
          <div className="score-value">{voltageScores.channel1.toFixed(2)}</div>
        </div>
        <div className="score-card">
          <div className="score-label">Channel 2 (µV)</div>
          <div className="score-value">{voltageScores.channel2.toFixed(2)}</div>
        </div>
        <div className="score-card">
          <div className="score-label">Channel 3 (µV)</div>
          <div className="score-value">{voltageScores.channel3.toFixed(2)}</div>
        </div>
        <div className="score-card">
          <div className="score-label">Channel 4 (µV)</div>
          <div className="score-value">{voltageScores.channel4.toFixed(2)}</div>
        </div>
      </div>

      {/* Mental State Scores */}
      <div className="scores-grid" style={{ marginTop: '20px' }}>
        <div className="score-card" style={{ background: '#e8f5e9' }}>
          <div className="score-label">Calm Score</div>
          <div className="score-value" style={{ color: '#2e7d32' }}>{mentalStateScores.calm.toFixed(1)}</div>
        </div>
        <div className="score-card" style={{ background: '#fff3e0' }}>
          <div className="score-label">Normal Score</div>
          <div className="score-value" style={{ color: '#f57c00' }}>{mentalStateScores.normal.toFixed(1)}</div>
        </div>
        <div className="score-card" style={{ background: '#ffebee' }}>
          <div className="score-label">Stressed Score</div>
          <div className="score-value" style={{ color: '#c62828' }}>{mentalStateScores.stressed.toFixed(1)}</div>
        </div>
      </div>

      {/* Voltage Graph */}
      <div className="card" style={{ marginTop: '20px' }}>
        <h3 className="card-title">Raw Voltage Data (µV)</h3>
        {voltageData.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
            Waiting for voltage data... {isRecording ? '(Streaming in progress)' : '(Click Start to begin)'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={voltageData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 12 }}
                interval="preserveStartEnd"
              />
              <YAxis 
                domain={['auto', 'auto']}
                tick={{ fontSize: 12 }}
                label={{ value: 'Voltage (µV)', angle: -90, position: 'insideLeft' }}
                allowDataOverflow={false}
              />
              <Tooltip 
                formatter={(value) => `${parseFloat(value).toFixed(2)} µV`}
                labelStyle={{ color: '#333' }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="channel1" 
                stroke="#667eea" 
                name="Channel 1" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="channel2" 
                stroke="#f093fb" 
                name="Channel 2" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="channel3" 
                stroke="#4facfe" 
                name="Channel 3" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="channel4" 
                stroke="#43e97b" 
                name="Channel 4" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Mental State Graph */}
      <div className="card" style={{ marginTop: '20px' }}>
        <h3 className="card-title">Mental State Analysis</h3>
        {mentalStateData.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
            Waiting for mental state data... {isRecording ? '(Streaming in progress)' : '(Click Start to begin)'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={mentalStateData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 12 }}
                interval="preserveStartEnd"
              />
              <YAxis 
                domain={[0, 100]}
                tick={{ fontSize: 12 }}
                label={{ value: 'Score (0-100)', angle: -90, position: 'insideLeft' }}
                allowDataOverflow={false}
              />
              <Tooltip 
                formatter={(value) => `${parseFloat(value).toFixed(1)}`}
                labelStyle={{ color: '#333' }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="calm" 
                stroke="#2e7d32" 
                name="Calm" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="normal" 
                stroke="#f57c00" 
                name="Normal" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="stressed" 
                stroke="#c62828" 
                name="Stressed" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Breathing Exercise Popup */}
      {showBreathingExercise && (
        <div className="breathing-exercise-overlay" onClick={() => {
          wasManuallyClosedRef.current = true;
          setShowBreathingExercise(false);
          setEncouragingMessage(null);
        }}>
          <div className="breathing-exercise-popup" onClick={(e) => e.stopPropagation()}>
            <button 
              className="breathing-exercise-close"
              onClick={() => {
                wasManuallyClosedRef.current = true;
                setShowBreathingExercise(false);
                setEncouragingMessage(null);
              }}
              aria-label="Close"
            >
              ×
            </button>
            <div className="breathing-exercise-content">
              <h3>Calming Breathing Exercise</h3>
              <p className="breathing-instruction">
                {breathingPhase === 'inhale' && 'Breathe in slowly...'}
                {breathingPhase === 'hold' && 'Hold your breath...'}
                {breathingPhase === 'exhale' && 'Breathe out slowly...'}
                {breathingPhase === 'pause' && 'Pause...'}
              </p>
              <div className={`breathing-circle ${breathingPhase}`}>
                <div className="breathing-circle-inner"></div>
              </div>
              <p className="breathing-cycle-info">Cycle {breathingCycle}</p>
              <p className="breathing-tip">
                Focus on your breath. Take your time and find your natural rhythm.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Encouraging Message Toast */}
      {encouragingMessage && (
        <div className="encouraging-message-toast">
          <div className="encouraging-message-content">
            <span className="encouraging-message-icon">✨</span>
            <p>{encouragingMessage}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;

