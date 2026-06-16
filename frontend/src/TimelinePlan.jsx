import { useState } from 'react';

const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

// Distinct, glowing hues that read well on the dark glass theme.
const UPGRADE_COLORS = {
  heat_pump: '#fb923c',              // orange
  heat_pump_water_heater: '#38bdf8', // sky
  attic_insulation: '#facc15',       // amber
  air_sealing: '#2dd4bf',            // teal
  duct_sealing: '#a78bfa',           // violet
  solar: '#fde047',                  // yellow
  electrical_panel: '#f472b6',       // pink
  battery_storage: '#818cf8',        // indigo
};
const DEFAULT_COLOR = '#22c55e';
const colorFor = (key) => UPGRADE_COLORS[key] || DEFAULT_COLOR;

const SKIP_REASONS = {
  over_budget: 'Exceeds your annual budget',
  dependency_unmet: 'Needs an earlier upgrade first',
  dominated: 'Lower priority for your goals',
};

const FOCUS_LABELS = {
  balanced: 'Balanced plan',
  cost: 'Cost-focused plan',
  carbon: 'Carbon-focused plan',
};

function TimelinePlan({ timeline, optionByKey, onSelectUpgrade }) {
  const years = timeline.years || [];
  const details = timeline.upgrade_details || [];
  const detailByKey = Object.fromEntries(details.map((d) => [d.upgrade_key, d]));

  const scheduledKeys = details.filter((d) => d.scheduled_year != null).map((d) => d.upgrade_key);
  const skipped = details.filter((d) => d.scheduled_year == null);

  // Track width reference: the annual budget the user set. Each year's blocks fill
  // toward this ceiling, so the chart literally shows budget consumption per year.
  const cohortCost = (year) =>
    year.upgrades.reduce((sum, key) => sum + (optionByKey[key]?.net_cost ?? 0), 0);
  const reference =
    timeline.budget_per_year ||
    Math.max(1, ...years.map(cohortCost));

  const totalOutOfPocket = years.reduce((sum, y) => sum + (y.outlay ?? 0), 0);
  const totalIncentives = years.reduce((sum, y) => sum + (y.incentives_captured ?? 0), 0);
  const annualSavingsUnlocked = scheduledKeys.reduce(
    (sum, key) => sum + (optionByKey[key]?.annual_savings ?? 0),
    0,
  );

  return (
    <section style={{ marginBottom: '3rem' }} className="animate-fade-in">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
        <h3 style={{ margin: 0 }}>Your Multi-Year Plan</h3>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <Chip>{FOCUS_LABELS[timeline.focus] || 'Plan'}</Chip>
          {timeline.budget_per_year != null && (
            <Chip>{currency.format(timeline.budget_per_year)}/yr budget</Chip>
          )}
        </div>
      </div>

      {/* Key insight banner */}
      {timeline.key_insight && (
        <div className="glass-panel" style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start', padding: '1rem 1.25rem', marginBottom: '1.5rem', borderLeft: '4px solid var(--accent-primary)', background: 'rgba(34, 197, 94, 0.06)' }}>
          <span style={{ fontSize: '1.25rem', lineHeight: 1 }} role="img" aria-label="insight">💡</span>
          <p style={{ margin: 0, color: 'var(--text-primary)', fontSize: '0.95rem', lineHeight: 1.6 }}>
            {timeline.key_insight}
          </p>
        </div>
      )}

      {/* Summary metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <Metric label="Out of pocket" value={currency.format(totalOutOfPocket)} />
        <Metric label="Incentives captured" value={currency.format(totalIncentives)} accent="var(--success)" />
        <Metric label="Annual savings unlocked" value={`${currency.format(annualSavingsUnlocked)}/yr`} accent="var(--success)" />
        <Metric label="CO₂ avoided" value={`${(timeline.total_carbon_avoided_tons ?? 0).toFixed(1)} tons`} />
      </div>

      {/* Swimlane */}
      <div className="glass-panel" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          {years.map((year, idx) => (
            <YearRow
              key={year.year}
              year={year}
              index={idx}
              reference={reference}
              optionByKey={optionByKey}
              detailByKey={detailByKey}
              onSelectUpgrade={onSelectUpgrade}
            />
          ))}
        </div>
        {/* Budget reference caption */}
        {timeline.budget_per_year != null && (
          <p style={{ margin: '1rem 0 0', fontSize: '0.78rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
            Each bar fills toward your {currency.format(timeline.budget_per_year)}/yr budget →
          </p>
        )}
      </div>

      {/* Legend */}
      {scheduledKeys.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem 1.25rem', marginBottom: skipped.length ? '1.5rem' : 0 }}>
          {scheduledKeys.map((key) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: colorFor(key), boxShadow: `0 0 8px ${colorFor(key)}66`, flexShrink: 0 }} />
              {optionByKey[key]?.name || key}
            </div>
          ))}
        </div>
      )}

      {/* Skipped upgrades */}
      {skipped.length > 0 && (
        <div>
          <p style={{ fontSize: '0.8rem', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
            Not scheduled within your budget
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
            {skipped.map((d) => {
              const option = optionByKey[d.upgrade_key];
              return (
                <button
                  key={d.upgrade_key}
                  type="button"
                  onClick={() => option && onSelectUpgrade(option)}
                  style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '0.15rem', padding: '0.55rem 0.9rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--card-border)', cursor: option ? 'pointer' : 'default', textAlign: 'left' }}
                >
                  <span style={{ color: 'var(--text-primary)', fontSize: '0.88rem', fontWeight: 600 }}>
                    {option?.name || d.upgrade_key}
                  </span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.74rem' }}>
                    {SKIP_REASONS[d.skipped_reason] || 'Not selected'}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function YearRow({ year, index, reference, optionByKey, detailByKey, onSelectUpgrade }) {
  const hasWork = year.upgrades.length > 0;
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', gap: '1rem' }}>
      {/* Year label */}
      <div style={{ flexShrink: 0, width: '64px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '1rem', lineHeight: 1.1 }}>{year.year}</span>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', letterSpacing: '0.03em' }}>Year {index + 1}</span>
      </div>

      {/* Track */}
      <div style={{ flex: 1, minWidth: 0, position: 'relative', display: 'flex', gap: '6px', alignItems: 'stretch', background: 'rgba(255,255,255,0.03)', border: '1px dashed var(--card-border)', borderRadius: '12px', padding: '6px', minHeight: '60px' }}>
        {hasWork ? (
          year.upgrades.map((key) => (
            <TimelineBlock
              key={key}
              option={optionByKey[key]}
              detail={detailByKey[key]}
              upgradeKey={key}
              reference={reference}
              onSelect={onSelectUpgrade}
            />
          ))
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)', fontSize: '0.8rem', opacity: 0.6 }}>
            No upgrades scheduled
          </div>
        )}
      </div>

      {/* Year totals */}
      <div style={{ flexShrink: 0, width: '110px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'flex-end', gap: '0.15rem' }}>
        {year.outlay > 0 && (
          <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', fontWeight: 600 }}>
            −{currency.format(year.outlay)}
          </span>
        )}
        {year.incentives_captured > 0 && (
          <span style={{ fontSize: '0.78rem', color: 'var(--success)' }}>
            +{currency.format(year.incentives_captured)} back
          </span>
        )}
      </div>
    </div>
  );
}

function TimelineBlock({ option, detail, upgradeKey, reference, onSelect }) {
  const [hover, setHover] = useState(false);
  if (!option) return null;

  const color = colorFor(upgradeKey);
  // Bar width = this upgrade's share of the year's budget, measured in UPFRONT cash
  // (gross − point-of-sale rebates) — the same basis the budget constraint uses.
  const upfront = detail?.upfront_outlay ?? option.net_cost;
  const widthPct = Math.max(8, Math.min(100, (upfront / reference) * 100));
  const lowConfidence = detail && detail.incentive_confidence != null && detail.incentive_confidence < 0.75;

  return (
    <div
      onClick={() => onSelect(option)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        flexBasis: `${widthPct}%`,
        flexGrow: 0,
        flexShrink: 1,
        minWidth: 0,
        position: 'relative',
        cursor: 'pointer',
        borderRadius: '9px',
        padding: '0.5rem 0.6rem',
        background: `linear-gradient(135deg, ${color}33, ${color}1a)`,
        border: `1px solid ${color}`,
        boxShadow: hover ? `0 6px 18px ${color}55` : `0 0 0 ${color}00`,
        transform: hover ? 'translateY(-2px)' : 'none',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        overflow: 'hidden',
      }}
    >
      <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {option.name}
      </span>
      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
        {currency.format(upfront)} upfront
      </span>

      {/* Hover tooltip */}
      {hover && (
        <div
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 8px)',
            left: 0,
            zIndex: 30,
            width: '230px',
            maxWidth: '70vw',
            padding: '0.85rem 1rem',
            borderRadius: '12px',
            background: 'rgba(7, 24, 16, 0.97)',
            border: `1px solid ${color}`,
            boxShadow: '0 12px 30px rgba(0,0,0,0.5)',
            pointerEvents: 'none',
          }}
        >
          <p style={{ margin: '0 0 0.5rem', fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
            {option.name}
          </p>
          <TooltipRow label="Upfront cash" value={currency.format(upfront)} />
          {detail && detail.incentive_value > 0 && (
            <TooltipRow label="Incentives back" value={`${currency.format(detail.incentive_value)}`} accent="var(--success)" />
          )}
          <TooltipRow label="Net after incentives" value={currency.format(option.net_cost)} />
          <TooltipRow label="Saves" value={`${currency.format(option.annual_savings)}/yr`} accent="var(--success)" />
          {option.payback_years != null && (
            <TooltipRow label="Payback" value={`${option.payback_years} yrs`} />
          )}
          {lowConfidence && (
            <p style={{ margin: '0.5rem 0 0', fontSize: '0.72rem', color: '#fbbf24', lineHeight: 1.4 }}>
              ⚠ Incentive needs eligibility verification
            </p>
          )}
          <p style={{ margin: '0.5rem 0 0', fontSize: '0.7rem', color: 'var(--accent-primary)' }}>
            Click for full details →
          </p>
        </div>
      )}
    </div>
  );
}

function TooltipRow({ label, value, accent = 'var(--text-primary)' }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', fontSize: '0.8rem', marginTop: '0.2rem' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ color: accent, fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function Metric({ label, value, accent = 'var(--text-primary)' }) {
  return (
    <div className="glass-panel" style={{ padding: '1.1rem 1.25rem', textAlign: 'center' }}>
      <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: '0.78rem', letterSpacing: '0.02em' }}>{label}</p>
      <p style={{ margin: '0.35rem 0 0', fontSize: '1.4rem', fontWeight: 700, color: accent }}>{value}</p>
    </div>
  );
}

function Chip({ children }) {
  return (
    <span style={{ padding: '0.35rem 0.85rem', borderRadius: '999px', background: 'var(--card-bg)', border: '1px solid var(--card-border)', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
      {children}
    </span>
  );
}

export default TimelinePlan;
