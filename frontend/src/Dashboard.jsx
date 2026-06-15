import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState(null);
  const location = useLocation();
  const navigate = useNavigate();

  const queryParams = new URLSearchParams(location.search);
  const address = queryParams.get('address');

  useEffect(() => {
    if (!address) {
      navigate('/');
      return;
    }

    // Simulate an API call to the FastAPI backend
    const fetchPlan = async () => {
      setLoading(true);
      // In a real app: const response = await fetch(`/api/generate-plan/?address=${encodeURIComponent(address)}`);
      
      // Mock data for boilerplate visualization
      setTimeout(() => {
        setPlan({
          address: address,
          summary: "Based on our AI analysis, your home is an excellent candidate for a heat pump and upgraded attic insulation. By leveraging IRA incentives, you can cut your upfront costs significantly and achieve payback in just under 6 years.",
          metrics: {
            upfrontCost: 15500,
            annualSavings: 1250,
            carbonAvoided: "4.2 tons",
            paybackYears: 5.8
          },
          upgrades: [
            { id: 1, name: "Air Source Heat Pump", cost: 12000, savings: 800 },
            { id: 2, name: "Attic Insulation (R-49)", cost: 3500, savings: 450 }
          ],
          incentives: [
            { id: 1, name: "Energy Efficient Home Improvement Credit (25C)", amount: 2000, type: "Tax Credit" },
            { id: 2, name: "Local Utility Rebate", amount: 500, type: "Rebate" }
          ]
        });
        setLoading(false);
      }, 1500);
    };

    fetchPlan();
  }, [address, navigate]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <h2 className="text-gradient animate-fade-in">Analyzing {address}...</h2>
      </div>
    );
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }} className="animate-fade-in">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h2><span className="text-gradient">RetroFi ATL</span></h2>
        <button className="btn-primary" onClick={() => navigate('/')} style={{ padding: '0.5rem 1rem' }}>
          New Search
        </button>
      </header>

      <div style={{ marginBottom: '2rem' }}>
        <h1>Retrofit Plan for {plan.address}</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', maxWidth: '800px', marginTop: '1rem' }}>
          {plan.summary}
        </p>
      </div>

      {/* Metrics Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}>
        <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <h4 style={{ color: 'var(--text-secondary)' }}>Net Upfront Cost</h4>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>${plan.metrics.upfrontCost.toLocaleString()}</p>
        </div>
        <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <h4 style={{ color: 'var(--text-secondary)' }}>Annual Savings</h4>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--success)' }}>${plan.metrics.annualSavings.toLocaleString()}</p>
        </div>
        <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <h4 style={{ color: 'var(--text-secondary)' }}>Carbon Avoided / Yr</h4>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--accent-primary)' }}>{plan.metrics.carbonAvoided}</p>
        </div>
        <div className="glass-panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <h4 style={{ color: 'var(--text-secondary)' }}>Est. Payback</h4>
          <p style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>{plan.metrics.paybackYears} Years</p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
        {/* Upgrades */}
        <div>
          <h3 style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
            Recommended Upgrades
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {plan.upgrades.map(upgrade => (
              <div key={upgrade.id} className="glass-panel" style={{ padding: '1.5rem' }}>
                <h4>{upgrade.name}</h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem', color: 'var(--text-secondary)' }}>
                  <span>Cost: ${upgrade.cost.toLocaleString()}</span>
                  <span style={{ color: 'var(--success)' }}>Save: ${upgrade.savings}/yr</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Incentives Stack */}
        <div>
          <h3 style={{ marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
            Eligible Incentives
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {plan.incentives.map(incentive => (
              <div key={incentive.id} className="glass-panel" style={{ padding: '1.5rem', borderLeft: `4px solid var(--accent-primary)` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h4 style={{ margin: 0 }}>{incentive.name}</h4>
                  <span style={{ background: 'rgba(59, 130, 246, 0.2)', color: 'var(--accent-primary)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.8rem', fontWeight: 'bold' }}>
                    {incentive.type}
                  </span>
                </div>
                <p style={{ fontSize: '1.5rem', fontWeight: 'bold', marginTop: '1rem', color: 'var(--success)' }}>
                  ${incentive.amount.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
