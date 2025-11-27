import ReactMarkdown from 'react-markdown';
import './Stage3.css';

export default function Stage3({ finalResponse, streaming }) {
  // Use completed response if available, otherwise show streaming content
  const displayContent = finalResponse?.response || streaming?.content || '';
  const thinkingContent = streaming?.thinking || '';
  const isStreaming = streaming?.isStreaming && !finalResponse?.response;
  const modelName = finalResponse?.model || '';

  if (!displayContent && !isStreaming) {
    return null;
  }

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Chairman: {modelName ? (modelName.split('/')[1] || modelName) : 'Synthesizing...'}
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
        
        <div className="final-text markdown-content">
          <ReactMarkdown>{displayContent}</ReactMarkdown>
          {isStreaming && <span className="cursor-blink">▌</span>}
        </div>
      </div>
    </div>
  );
}
