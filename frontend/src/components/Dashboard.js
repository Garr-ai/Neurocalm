import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './Dashboard.css';

const Dashboard = ({ currentUser }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [currentMode, setCurrentMode] = useState('background');
  const [eegData, setEegData] = useState([]);
  const [ws, setWs] = useState(null);
  const [scores, setScores] = useState({
    focus: 0,
    load: 0,
    anomaly: 0
  });
  const [status, setStatus] = useState('Disconnected');
  const [error, setError] = useState(null);

  useEffect(() => {
    // Connect to WebSocket
    const websocket = new WebSocket('ws://localhost:8765');
    
    websocket.onopen = () => {
      console.log('✅ WebSocket CONNECTED');
      setWs(websocket);
      setStatus('Connected');
      setError(null);
      // Reset recording state - will be updated by state_sync message
      setIsRecording(false);
    };

    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('=== MESSAGE RECEIVED ===', message.type, message);
        
        if (message.type === 'eeg_data') {
          console.log('✅ EEG DATA RECEIVED!', message.data);
          
          // Validate data structure
          if (!message.data || typeof message.data.focus_score === 'undefined') {
            console.error('Invalid EEG data structure:', message);
            return;
          }
          
          const newData = {
            time: new Date(message.timestamp).toLocaleTimeString(),
            focus: message.data.focus_score,
            load: message.data.load_score,
            anomaly: message.data.anomaly_score
          };
          
          console.log('Updating scores and chart data:', newData);
          
          setScores({
            focus: message.data.focus_score,
            load: message.data.load_score,
            anomaly: message.data.anomaly_score
          });
          
          setEegData(prev => {
            const updated = [...prev.slice(-59), newData]; // Keep last 60 points
            console.log('EEG data array length:', updated.length);
            return updated;
          });
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
          setCurrentMode(message.mode || 'background');
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
      setError('Failed to connect to WebSocket server');
      setStatus('Connection Error');
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
      setWs(null);
      setStatus('Disconnected');
    };

    return () => {
      websocket.close();
    };
  }, []);

  const startRecording = () => {
    console.log('=== START RECORDING CLICKED ===');
    console.log('WebSocket object:', ws);
    console.log('WebSocket readyState:', ws?.readyState);
    console.log('WebSocket OPEN constant:', WebSocket.OPEN);
    
    if (!ws) {
      const errorMsg = 'WebSocket is null. Please refresh the page.';
      console.error(errorMsg);
      setError(errorMsg);
      setStatus('Not Connected');
      return;
    }
    
    if (ws.readyState !== WebSocket.OPEN) {
      const states = {
        0: 'CONNECTING',
        1: 'OPEN',
        2: 'CLOSING',
        3: 'CLOSED'
      };
      const errorMsg = `WebSocket not open. Current state: ${states[ws.readyState] || ws.readyState}. Please refresh the page.`;
      console.error(errorMsg);
      setError(errorMsg);
      setStatus('Not Connected');
      return;
    }
    
    console.log('WebSocket is OPEN, sending start_recording message...');
    try {
      const message = { type: 'start_recording' };
      console.log('Sending message:', message);
      ws.send(JSON.stringify(message));
      setStatus('Connecting to Ganglion...');
      setError(null);
      console.log('✅ start_recording message sent successfully');
    } catch (error) {
      console.error('❌ Error sending start_recording message:', error);
      setError(`Failed to send start recording command: ${error.message}`);
      setStatus('Error');
    }
  };

  const stopRecording = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      console.log('Sending stop_recording message...');
      ws.send(JSON.stringify({ type: 'stop_recording' }));
      setStatus('Stopping...');
    }
  };

  const changeMode = (mode) => {
    setCurrentMode(mode);
    if (ws) {
      ws.send(JSON.stringify({ type: 'set_mode', mode }));
    }
  };

  const tabs = [
    { id: 'meeting', label: 'Meetings' },
    { id: 'study', label: 'Studying' },
    { id: 'lecture', label: 'Lectures' },
    { id: 'background', label: 'Health Journal' }
  ];

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
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!ws || ws.readyState !== WebSocket.OPEN}
          >
            {isRecording ? 'Stop Recording' : 'Start Recording'}
          </button>
        </div>
      </div>

      <div className="mode-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`mode-tab ${currentMode === tab.id ? 'active' : ''}`}
            onClick={() => changeMode(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="scores-grid">
        <div className="score-card">
          <div className="score-label">Focus Score</div>
          <div className="score-value">{scores.focus.toFixed(1)}</div>
        </div>
        <div className="score-card">
          <div className="score-label">Load Score</div>
          <div className="score-value">{scores.load.toFixed(1)}</div>
        </div>
        <div className="score-card">
          <div className="score-label">Anomaly Score</div>
          <div className="score-value">{scores.anomaly.toFixed(1)}</div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">Real-time EEG Data</h3>
        {eegData.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
            Waiting for EEG data... {isRecording ? '(Recording in progress)' : '(Click Start Recording)'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={eegData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 12 }}
                interval="preserveStartEnd"
              />
              <YAxis 
                domain={[0, 'auto']}
                tick={{ fontSize: 12 }}
                label={{ value: 'Score', angle: -90, position: 'insideLeft' }}
                allowDataOverflow={false}
              />
              <Tooltip 
                formatter={(value) => value.toFixed(2)}
                labelStyle={{ color: '#333' }}
              />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="focus" 
                stroke="#667eea" 
                name="Focus" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="load" 
                stroke="#f093fb" 
                name="Load" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line 
                type="monotone" 
                dataKey="anomaly" 
                stroke="#4facfe" 
                name="Anomaly" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};

export default Dashboard;

