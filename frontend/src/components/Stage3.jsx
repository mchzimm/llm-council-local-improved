import ReactMarkdown from 'react-markdown';
import './Stage3.css';

export default function Stage3({ finalResponse, streaming }) {
  // Use completed response if available, otherwise show streaming content
  const displayContent = finalResponse?.response || streaming?.content || '';
  const thinkingContent = streaming?.thinking || '';
  const isStreaming = streaming?.isStreaming && !finalResponse?.response;
  const modelName = finalResponse?.model || '';
  const tokensPerSecond = streaming?.tokensPerSecond;
  const thinkingSeconds = streaming?.thinkingSeconds;
  const elapsedSeconds = streaming?.elapsedSeconds;

  // Format timing as "thinking/total"
  const formatTiming = (thinking, elapsed) => {
    if (elapsed === undefined) return null;
    const t = thinking !== undefined ? thinking : elapsed;
    return `${t}s/${elapsed}s`;
  };

  if (!displayContent && !isStreaming) {
    return null;
  }

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Presenter: {modelName ? (modelName.split('/')[1] || modelName) : 'Formatting...'}
          {isStreaming && tokensPerSecond !== undefined && <span className="tps-badge">{tokensPerSecond.toFixed(1)} tok/s</span>}
          {isStreaming && formatTiming(thinkingSeconds, elapsedSeconds) && <span className="timing-badge">{formatTiming(thinkingSeconds, elapsedSeconds)}</span>}
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
