import React, { useState } from 'react';

function App() {
    const [count, setCount] = useState(0);

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            fontFamily: 'system-ui, sans-serif',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: 'white'
        }}>
            <h1 style={{ fontSize: '3rem', marginBottom: '2rem' }}>Counter App</h1>

            <div style={{
                background: 'rgba(255,255,255,0.1)',
                borderRadius: '20px',
                padding: '2rem 4rem',
                backdropFilter: 'blur(10px)'
            }}>
                <p style={{ fontSize: '5rem', margin: '1rem 0', textAlign: 'center' }}>{count}</p>

                <div style={{ display: 'flex', gap: '1rem' }}>
                    <button
                        onClick={() => setCount(c => c - 1)}
                        style={{
                            padding: '1rem 2rem',
                            fontSize: '1.5rem',
                            border: 'none',
                            borderRadius: '10px',
                            background: '#ef4444',
                            color: 'white',
                            cursor: 'pointer'
                        }}
                    >
                        - Decrement
                    </button>
                    <button
                        onClick={() => setCount(0)}
                        style={{
                            padding: '1rem 2rem',
                            fontSize: '1.5rem',
                            border: 'none',
                            borderRadius: '10px',
                            background: '#6b7280',
                            color: 'white',
                            cursor: 'pointer'
                        }}
                    >
                        Reset
                    </button>
                    <button
                        onClick={() => setCount(c => c + 1)}
                        style={{
                            padding: '1rem 2rem',
                            fontSize: '1.5rem',
                            border: 'none',
                            borderRadius: '10px',
                            background: '#22c55e',
                            color: 'white',
                            cursor: 'pointer'
                        }}
                    >
                        + Increment
                    </button>
                </div>
            </div>
        </div>
    );
}

export default App;
