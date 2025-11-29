import { useState } from 'react';
import './ToolSteps.css';

/**
 * ToolSteps - Collapsible component for displaying multi-step tool call sequences.
 * 
 * Shows tool calls in a collapsible accordion with:
 * - Summary header showing tool count and total execution time
 * - Expandable detail view for each tool call
 * - Input/output display for each step
 * - Hover overlay with detailed stats for each step
 * 
 * Props:
 * - toolSteps: Array of tool step objects with: tool, input, output, executionTime, status, startTime
 * - currentStep: Currently executing step (optional, for live updates)
 */
export default function ToolSteps({ toolSteps = [], currentStep = null }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState({});
  const [hoveredStep, setHoveredStep] = useState(null);

  // Combine completed steps with current step
  const allSteps = currentStep 
    ? [...toolSteps.filter(s => s.tool !== currentStep.tool), currentStep]
    : toolSteps;

  if (allSteps.length === 0) {
    return null;
  }

  // Calculate total execution time
  const totalTime = allSteps.reduce((sum, step) => {
    return sum + (step.executionTime || 0);
  }, 0);

  // Count completed and in-progress
  const completedCount = allSteps.filter(s => s.status === 'complete').length;
  const inProgressCount = allSteps.filter(s => s.status === 'running').length;
  const totalCount = allSteps.length;

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  const toggleStepExpanded = (index) => {
    setExpandedSteps(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  // Format tool output for display
  const formatOutput = (output) => {
    if (!output) return 'No output';
    
    if (typeof output === 'string') {
      return output.length > 500 ? output.substring(0, 500) + '...' : output;
    }
    
    // Handle MCP response format
    if (output.content && Array.isArray(output.content)) {
      const text = output.content[0]?.text;
      if (text) {
        return text.length > 500 ? text.substring(0, 500) + '...' : text;
      }
    }
    
    const jsonStr = JSON.stringify(output, null, 2);
    return jsonStr.length > 500 ? jsonStr.substring(0, 500) + '...' : jsonStr;
  };

  return (
    <div className={`tool-steps ${isExpanded ? 'expanded' : 'collapsed'}`}>
      {/* Header - always visible */}
      <div className="tool-steps-header" onClick={toggleExpanded}>
        <div className="tool-steps-summary">
          <span className="tool-steps-icon">{isExpanded ? '▼' : '▶'}</span>
          <span className="tool-steps-label">🔧 Tool Steps</span>
          <span className="tool-steps-count">
            {inProgressCount > 0 ? (
              <span className="in-progress">
                <span className="mini-spinner"></span>
                {completedCount}/{totalCount}
              </span>
            ) : (
              <span className="completed">{completedCount}/{totalCount} complete</span>
            )}
          </span>
          {totalTime > 0 && (
            <span className="tool-steps-time">{totalTime.toFixed(2)}s total</span>
          )}
        </div>
        {!isExpanded && allSteps.length > 0 && (
          <div className="tool-steps-preview">
            {allSteps.map(s => s.tool.split('.').pop()).join(' → ')}
          </div>
        )}
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="tool-steps-content">
          {allSteps.map((step, index) => (
            <div 
              key={`${step.tool}-${index}`}
              className={`tool-step ${step.status || 'complete'}`}
              onMouseEnter={() => setHoveredStep(index)}
              onMouseLeave={() => setHoveredStep(null)}
            >
              <div 
                className="tool-step-header"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleStepExpanded(index);
                }}
              >
                <span className="step-expand-icon">
                  {expandedSteps[index] ? '▼' : '▶'}
                </span>
                <span className="step-number">{index + 1}</span>
                <span className="step-status-icon">
                  {step.status === 'running' ? (
                    <span className="step-spinner"></span>
                  ) : step.status === 'error' ? (
                    '❌'
                  ) : (
                    '✅'
                  )}
                </span>
                <span className="step-tool-name">{step.tool}</span>
                {step.executionTime !== undefined && (
                  <span className="step-time">{step.executionTime.toFixed(2)}s</span>
                )}
              </div>

              {expandedSteps[index] && (
                <div className="tool-step-details">
                  <div className="step-io">
                    <div className="step-io-label">Input:</div>
                    <code className="step-io-value">
                      {JSON.stringify(step.input || {}, null, 2)}
                    </code>
                  </div>
                  {step.output && (
                    <div className="step-io">
                      <div className="step-io-label">Output:</div>
                      <code className="step-io-value">
                        {formatOutput(step.output)}
                      </code>
                    </div>
                  )}
                  {step.error && (
                    <div className="step-io step-error">
                      <div className="step-io-label">Error:</div>
                      <code className="step-io-value">{step.error}</code>
                    </div>
                  )}
                </div>
              )}

              {/* Hover stats overlay */}
              {hoveredStep === index && (
                <div className="tool-step-stats-overlay">
                  <div className="step-stats-title">📊 Tool Call Details</div>
                  <div className="step-stats-row">
                    <span className="step-stats-label">Server</span>
                    <span className="step-stats-value">{step.tool.split('.')[0] || 'unknown'}</span>
                  </div>
                  <div className="step-stats-row">
                    <span className="step-stats-label">Tool</span>
                    <span className="step-stats-value">{step.tool.split('.').slice(1).join('.') || step.tool}</span>
                  </div>
                  <div className="step-stats-row">
                    <span className="step-stats-label">Execution Time</span>
                    <span className="step-stats-value">{step.executionTime !== undefined ? `${step.executionTime.toFixed(2)}s` : 'N/A'}</span>
                  </div>
                  <div className="step-stats-row">
                    <span className="step-stats-label">Status</span>
                    <span className={`step-stats-value ${step.status === 'error' ? 'error' : 'success'}`}>
                      {step.status === 'error' ? '✗ Failed' : step.status === 'running' ? '⏳ Running' : '✓ Success'}
                    </span>
                  </div>
                  <div className="step-stats-output">
                    <div className="step-stats-output-label">Output Preview:</div>
                    <div className="step-stats-output-value">{formatOutput(step.output)}</div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
