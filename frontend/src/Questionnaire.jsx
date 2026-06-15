import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const MAX_QUESTIONS = 10;

function BotBubble({ text }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', maxWidth: '75%' }}>
      <div style={{
        width: '2rem', height: '2rem', borderRadius: '50%', flexShrink: 0,
        background: 'var(--accent-gradient)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.85rem', fontWeight: 700, color: '#fff',
      }}>R</div>
      <div style={{
        background: 'rgba(59, 130, 246, 0.15)',
        border: '1px solid rgba(59, 130, 246, 0.25)',
        borderRadius: '0 12px 12px 12px',
        padding: '0.75rem 1rem',
        color: 'var(--text-primary)',
        fontSize: '0.95rem',
        lineHeight: 1.5,
      }}>
        {text}
      </div>
    </div>
  );
}

function UserBubble({ text }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div style={{
        background: 'rgba(139, 92, 246, 0.2)',
        border: '1px solid rgba(139, 92, 246, 0.3)',
        borderRadius: '12px 0 12px 12px',
        padding: '0.75rem 1rem',
        color: 'var(--text-primary)',
        fontSize: '0.95rem',
        lineHeight: 1.5,
        maxWidth: '70%',
      }}>
        {text}
      </div>
    </div>
  );
}

function Questionnaire() {
  const location = useLocation();
  const navigate = useNavigate();

  const { answers: initialAnswers, address } = location.state || {};

  const [answers, setAnswers] = useState(initialAnswers || {});
  const [messages, setMessages] = useState([]);
  const [currentFieldKey, setCurrentFieldKey] = useState(null);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState('loading'); // 'loading' | 'awaiting_input' | 'submitting' | 'generating_plan' | 'done' | 'error'
  const [errorMsg, setErrorMsg] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!initialAnswers) { navigate('/'); return; }
    fetchNextQuestion(initialAnswers);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, status]);

  async function fetchNextQuestion(currentAnswers) {
    setStatus('loading');
    try {
      const res = await fetch('/api/questionnaire/next', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers: currentAnswers }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();

      if (data.complete) {
        await finalisePlan(currentAnswers);
      } else {
        setCurrentFieldKey(data.field_key);
        setMessages((prev) => [...prev, { role: 'bot', text: data.question }]);
        setStatus('awaiting_input');
      }
    } catch (err) {
      setErrorMsg(err.message || 'Something went wrong. Please try again.');
      setStatus('error');
    }
  }

  async function finalisePlan(currentAnswers) {
    setStatus('generating_plan');
    setMessages((prev) => [
      ...prev,
      { role: 'bot', text: "Perfect — I have everything I need. Generating your personalised retrofit plan now…" },
    ]);
    try {
      const res = await fetch('/api/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, answers: currentAnswers }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const { plan } = await res.json();
      navigate('/dashboard', { state: { plan, address } });
    } catch (err) {
      setErrorMsg(err.message || 'Failed to generate plan. Please try again.');
      setStatus('error');
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || !currentFieldKey) return;

    const updatedAnswers = {
      ...answers,
      [currentFieldKey]: trimmed,
      _questions_asked: (answers._questions_asked || 0) + 1,
    };

    setMessages((prev) => [...prev, { role: 'user', text: trimmed }]);
    setAnswers(updatedAnswers);
    setInput('');
    setCurrentFieldKey(null);

    if ((updatedAnswers._questions_asked || 0) >= MAX_QUESTIONS) {
      await finalisePlan(updatedAnswers);
    } else {
      await fetchNextQuestion(updatedAnswers);
    }
  };

  const questionsAsked = answers._questions_asked || 0;

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      background: 'radial-gradient(circle at 50% -20%, #1e293b, #0f172a)',
    }}>
      {/* Header */}
      <header style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '1rem 2rem',
        borderBottom: '1px solid var(--card-border)',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(12px)',
      }}>
        <h2 style={{ margin: 0, fontSize: '1.25rem' }}>
          <span className="text-gradient">RetroFi ATL</span>
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {questionsAsked > 0 && (
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Question {questionsAsked} / {MAX_QUESTIONS}
            </span>
          )}
          <button
            onClick={() => navigate('/')}
            style={{
              background: 'transparent', border: '1px solid var(--card-border)',
              color: 'var(--text-secondary)', padding: '0.4rem 0.9rem',
              borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem',
            }}
          >
            Start over
          </button>
        </div>
      </header>

      {/* Progress bar */}
      {questionsAsked > 0 && (
        <div style={{ height: '3px', background: 'rgba(255,255,255,0.05)' }}>
          <div style={{
            height: '100%',
            width: `${(questionsAsked / MAX_QUESTIONS) * 100}%`,
            background: 'var(--accent-gradient)',
            transition: 'width 0.4s ease',
          }} />
        </div>
      )}

      {/* Chat area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '2rem', maxWidth: '720px', width: '100%', margin: '0 auto' }}>
        {/* Greeting */}
        {messages.length === 0 && status === 'loading' && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', marginTop: '4rem' }}>
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>
              <span className="text-gradient">Preparing your questions…</span>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {messages.map((msg, i) =>
            msg.role === 'bot'
              ? <BotBubble key={i} text={msg.text} />
              : <UserBubble key={i} text={msg.text} />
          )}

          {/* Typing indicator */}
          {status === 'loading' && messages.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{
                width: '2rem', height: '2rem', borderRadius: '50%', flexShrink: 0,
                background: 'var(--accent-gradient)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.85rem', fontWeight: 700, color: '#fff',
              }}>R</div>
              <div style={{
                background: 'rgba(59, 130, 246, 0.1)',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                borderRadius: '0 12px 12px 12px',
                padding: '0.75rem 1.25rem',
                display: 'flex', gap: '4px', alignItems: 'center',
              }}>
                {[0, 1, 2].map((i) => (
                  <span key={i} style={{
                    width: '6px', height: '6px', background: 'var(--accent-primary)',
                    borderRadius: '50%', display: 'inline-block',
                    animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}

          {status === 'generating_plan' && (
            <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '2rem 0' }}>
              Building your retrofit plan with Claude AI…
            </div>
          )}

          {status === 'error' && (
            <div style={{
              background: 'rgba(248, 113, 113, 0.1)', border: '1px solid rgba(248, 113, 113, 0.3)',
              borderRadius: '12px', padding: '1rem 1.25rem', color: '#f87171',
            }}>
              {errorMsg}
              <button
                onClick={() => fetchNextQuestion(answers)}
                style={{
                  display: 'block', marginTop: '0.75rem',
                  background: 'transparent', border: '1px solid #f87171',
                  color: '#f87171', padding: '0.4rem 1rem',
                  borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem',
                }}
              >
                Retry
              </button>
            </div>
          )}
        </div>

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      {status === 'awaiting_input' && (
        <div style={{
          borderTop: '1px solid var(--card-border)',
          background: 'rgba(15, 23, 42, 0.9)',
          backdropFilter: 'blur(12px)',
          padding: '1rem 2rem',
        }}>
          <form
            onSubmit={handleSubmit}
            style={{ display: 'flex', gap: '0.75rem', maxWidth: '720px', margin: '0 auto' }}
          >
            <input
              type="text"
              className="input-premium"
              placeholder="Type your answer…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              autoFocus
              style={{ flex: 1 }}
            />
            <button
              type="submit"
              className="btn-primary"
              style={{ padding: '0.75rem 1.5rem', whiteSpace: 'nowrap' }}
              disabled={!input.trim()}
            >
              Send →
            </button>
          </form>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
      `}</style>
    </div>
  );
}

export default Questionnaire;
