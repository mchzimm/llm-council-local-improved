import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage1.css';

export default function Stage1({ responses, streaming }) {
  const [activeTab, setActiveTab] = useState(0);

  // Get models from either completed responses or streaming state
  const models = responses?.length > 0 
    ? responses.map(r => r.model)
    : streaming ? Object.keys(streaming) : [];

  if (models.length === 0) {
    return null;
  }

  const currentModel = models[activeTab];
  const completedResponse = responses?.find(r => r.model === currentModel);
  const streamingData = streaming?.[currentModel];
  
  // Use completed response if available, otherwise show streaming content
  const displayContent = completedResponse?.response || streamingData?.content || '';
  const thinkingContent = streamingData?.thinking || '';
  const isStreaming = streamingData?.isStreaming && !completedResponse;

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div className="tabs">
        {models.map((model, index) => {
          const modelStreaming = streaming?.[model];
          const modelComplete = responses?.find(r => r.model === model);
          const hasContent = modelComplete || modelStreaming?.content;
          
          return (
            <button
              key={index}
              className={`tab ${activeTab === index ? 'active' : ''} ${modelStreaming?.isStreaming && !modelComplete ? 'streaming' : ''}`}
              onClick={() => setActiveTab(index)}
            >
              {model.split('/')[1] || model}
              {modelStreaming?.isStreaming && !modelComplete && <span className="streaming-indicator">●</span>}
            </button>
          );
        })}
      </div>

      <div className="tab-content">
        <div className="model-name">
          {currentModel}
          {isStreaming && <span className="streaming-badge">Streaming...</span>}
        </div>
        
        {thinkingContent && (
          <details className="thinking-section" open={isStreaming}>
            <summary>Thinking</summary>
            <div className="thinking-content">
              {thinkingContent}
            </div>
          </details>
        )}
        
        <div className="response-text markdown-content">
          <ReactMarkdown>{displayContent}</ReactMarkdown>
          {isStreaming && <span className="cursor-blink">▌</span>}
        </div>
      </div>
    </div>
  );
}
