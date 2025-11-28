import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  onSendMessage,
  onRedoMessage,
  onEditMessage,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const [editingIndex, setEditingIndex] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      if (editingIndex !== null) {
        // Editing existing message
        onEditMessage(editingIndex, input);
        setEditingIndex(null);
      } else {
        onSendMessage(input);
      }
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleRedo = (messageIndex) => {
    if (!isLoading && onRedoMessage) {
      onRedoMessage(messageIndex);
    }
  };

  const handleEdit = (messageIndex, content) => {
    if (!isLoading) {
      setEditingIndex(messageIndex);
      setInput(content);
    }
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setInput('');
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-header">
                    <div className="message-label">You</div>
                    <div className="message-actions">
                      <button
                        className="action-btn redo-btn"
                        onClick={() => handleRedo(index)}
                        disabled={isLoading}
                        title="Re-run council with this message"
                      >
                        ↻
                      </button>
                      <button
                        className="action-btn edit-btn"
                        onClick={() => handleEdit(index, msg.content)}
                        disabled={isLoading}
                        title="Edit and resubmit message"
                      >
                        ✎
                      </button>
                    </div>
                  </div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">
                    LLM Council
                    {msg.classification && (
                      <span className={`classification-badge ${msg.classification.type || 'unknown'}`}>
                        {msg.classification.status === 'classifying' ? '🔍 Classifying...' : 
                         msg.responseType === 'direct' ? '⚡ Direct' : '🤔 Deliberation'}
                      </span>
                    )}
                  </div>

                  {/* Classification indicator while classifying */}
                  {msg.classification?.status === 'classifying' && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Analyzing message type...</span>
                    </div>
                  )}

                  {/* Tool result card - shown for both direct and deliberation responses */}
                  {/* Check both toolResult (streaming) and tool_result (stored) */}
                  {(msg.toolResult || msg.tool_result) && (
                    <div className="tool-result-card">
                      <div className="tool-result-header">
                        <span className="tool-icon">🔧</span>
                        <span className="tool-name">MCP Tool: {(msg.toolResult || msg.tool_result).tool || `${(msg.toolResult || msg.tool_result).server}.${(msg.toolResult || msg.tool_result).tool}`}</span>
                      </div>
                      <div className="tool-result-body">
                        <div className="tool-io">
                          <span className="tool-label">Input:</span>
                          <code className="tool-value">{JSON.stringify((msg.toolResult || msg.tool_result).input)}</code>
                        </div>
                        <div className="tool-io">
                          <span className="tool-label">Output:</span>
                          <code className="tool-value">{typeof (msg.toolResult || msg.tool_result).output === 'string' ? (msg.toolResult || msg.tool_result).output : JSON.stringify((msg.toolResult || msg.tool_result).output)}</code>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* For direct responses, skip Stage 1 and Stage 2 */}
                  {msg.responseType !== 'direct' && (
                    <>
                      {/* Stage 1 */}
                      {msg.loading?.stage1 && !msg.stage1 && !Object.keys(msg.streaming?.stage1 || {}).length && (
                        <div className="stage-loading">
                          <div className="spinner"></div>
                          <span>Running Stage 1: Collecting individual responses...</span>
                        </div>
                      )}
                      {(msg.stage1 || Object.keys(msg.streaming?.stage1 || {}).length > 0) && (
                        <Stage1 
                          responses={msg.stage1} 
                          streaming={msg.streaming?.stage1}
                        />
                      )}

                      {/* Stage 2 */}
                      {msg.loading?.stage2 && !msg.stage2 && !Object.keys(msg.streaming?.stage2 || {}).length && (
                        <div className="stage-loading">
                          <div className="spinner"></div>
                          <span>Running Stage 2: Peer rankings...</span>
                        </div>
                      )}
                      {(msg.stage2 || Object.keys(msg.streaming?.stage2 || {}).length > 0) && (
                        <Stage2
                          rankings={msg.stage2}
                          labelToModel={msg.metadata?.label_to_model}
                          aggregateRankings={msg.metadata?.aggregate_rankings}
                          streaming={msg.streaming?.stage2}
                          roundInfo={msg.roundInfo}
                        />
                      )}
                    </>
                  )}

                  {/* Stage 3 / Direct Response */}
                  {msg.loading?.stage3 && !msg.stage3 && !msg.streaming?.stage3?.content && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>{msg.responseType === 'direct' ? 'Generating direct response...' : 'Running Stage 3: Final synthesis...'}</span>
                    </div>
                  )}
                  {(msg.stage3 || msg.streaming?.stage3?.content) && (
                    <Stage3 
                      finalResponse={msg.stage3} 
                      streaming={msg.streaming?.stage3}
                      isDirect={msg.responseType === 'direct'}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Consulting the council...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Show input form when:
          1. Conversation is empty (initial state), OR
          2. Last message is complete (has stage3 and not loading), OR
          3. Editing a message */}
      {(editingIndex !== null || 
        conversation.messages.length === 0 || 
        (conversation.messages.length > 0 && 
         !isLoading &&
         conversation.messages[conversation.messages.length - 1]?.role === 'assistant' &&
         conversation.messages[conversation.messages.length - 1]?.stage3)) && (
        <form className={`input-form ${editingIndex !== null ? 'editing' : ''}`} onSubmit={handleSubmit}>
          {editingIndex !== null && (
            <div className="editing-indicator">
              <span>Editing message...</span>
              <button type="button" className="cancel-edit-btn" onClick={cancelEdit}>Cancel</button>
            </div>
          )}
          <textarea
            className="message-input"
            placeholder={editingIndex !== null
              ? "Edit your message... (Shift+Enter for new line, Enter to submit)"
              : conversation.messages.length === 0 
                ? "Ask your question... (Shift+Enter for new line, Enter to send)"
                : "Ask a follow-up question... (Shift+Enter for new line, Enter to send)"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <button
            type="submit"
            className="send-button"
            disabled={!input.trim() || isLoading}
          >
            {editingIndex !== null ? 'Update' : 'Send'}
          </button>
        </form>
      )}
    </div>
  );
}
