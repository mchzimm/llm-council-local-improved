import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  // Replace each "Response X" with the actual model name
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings, streaming, roundInfo }) {
  const [activeTab, setActiveTab] = useState(0);

  // Get models from either completed rankings or streaming state
  const models = rankings?.length > 0 
    ? rankings.map(r => r.model)
    : streaming ? Object.keys(streaming) : [];

  if (models.length === 0) {
    return null;
  }

  const currentModel = models[activeTab];
  const completedRanking = rankings?.find(r => r.model === currentModel);
  const streamingData = streaming?.[currentModel];
  
  // Use completed ranking if available, otherwise show streaming content
  const displayContent = completedRanking?.ranking || streamingData?.content || '';
  const thinkingContent = streamingData?.thinking || '';
  const isStreaming = streamingData?.isStreaming && !completedRanking;
  const parsedRanking = completedRanking?.parsed_ranking;
  const tokensPerSecond = streamingData?.tokensPerSecond;
  const thinkingSeconds = streamingData?.thinkingSeconds;
  const elapsedSeconds = streamingData?.elapsedSeconds;

  // Format timing as "thinking/total"
  const formatTiming = (thinking, elapsed) => {
    if (elapsed === undefined) return null;
    const t = thinking !== undefined ? thinking : elapsed;
    return `${t}s/${elapsed}s`;
  };

  return (
    <div className="stage stage2">
      <div className="stage-header">
        <h3 className="stage-title">Stage 2: Peer Rankings</h3>
        {roundInfo && roundInfo.maxRounds > 1 && (
          <span className="round-indicator">
            Round {roundInfo.current} / {roundInfo.maxRounds}
            {roundInfo.isRefinement && ' (Refinement)'}
          </span>
        )}
      </div>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each model evaluated all responses (anonymized as Response A, B, C, etc.) and provided rankings.
        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
      </p>

      <div className="tabs">
        {models.map((model, index) => {
          const modelStreaming = streaming?.[model];
          const modelComplete = rankings?.find(r => r.model === model);
          const modelTiming = modelStreaming?.elapsedSeconds !== undefined 
            ? `${modelStreaming?.thinkingSeconds ?? modelStreaming?.elapsedSeconds}s/${modelStreaming?.elapsedSeconds}s`
            : null;
          
          return (
            <button
              key={index}
              className={`tab ${activeTab === index ? 'active' : ''} ${modelStreaming?.isStreaming && !modelComplete ? 'streaming' : ''}`}
              onClick={() => setActiveTab(index)}
            >
              {model.split('/')[1] || model}
              {modelStreaming?.isStreaming && !modelComplete && modelTiming && <span className="timing-indicator">{modelTiming}</span>}
              {modelStreaming?.isStreaming && !modelComplete && <span className="streaming-indicator">●</span>}
            </button>
          );
        })}
      </div>

      <div className="tab-content">
        <div className="ranking-model">
          {currentModel}
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
        
        <div className="ranking-content markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(displayContent, labelToModel)}
          </ReactMarkdown>
          {isStreaming && <span className="cursor-blink">▌</span>}
        </div>

        {parsedRanking && parsedRanking.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {parsedRanking.map((label, i) => (
                <li key={i}>
                  {labelToModel && labelToModel[label]
                    ? labelToModel[label].split('/')[1] || labelToModel[label]
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => (
              <div key={index} className="aggregate-item">
                <span className="rank-position">#{index + 1}</span>
                <span className="rank-model">
                  {agg.model.split('/')[1] || agg.model}
                </span>
                <span className="rank-score">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="rank-count">
                  ({agg.rankings_count} votes)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
