import { useState, useEffect, useRef, useMemo } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import ToolSteps from './ToolSteps';
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
  const [showPinnedHeader, setShowPinnedHeader] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const firstUserMessageRef = useRef(null);

  // Find first and last user messages
  const { firstUserMessage, lastUserMessage, firstUserIndex, lastUserIndex } = useMemo(() => {
    if (!conversation?.messages?.length) return {};
    
    const userMessages = conversation.messages
      .map((msg, idx) => ({ msg, idx }))
      .filter(({ msg }) => msg.role === 'user');
    
    if (userMessages.length === 0) return {};
    
    const first = userMessages[0];
    const last = userMessages[userMessages.length - 1];
    
    return {
      firstUserMessage: first.msg,
      lastUserMessage: last.msg,
      firstUserIndex: first.idx,
      lastUserIndex: last.idx,
    };
  }, [conversation?.messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  // Handle scroll to show/hide pinned header
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      if (!firstUserMessageRef.current) {
        setShowPinnedHeader(false);
        return;
      }
      
      const firstMsgRect = firstUserMessageRef.current.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      
      // Show pinned header when first user message scrolls above container top
      setShowPinnedHeader(firstMsgRect.bottom < containerRect.top + 20);
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [firstUserMessage]);

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
      {/* Pinned first user message header */}
      {showPinnedHeader && firstUserMessage && (
        <div className="pinned-user-message">
          <div className="pinned-header-row">
            <div className="pinned-ids">
              <span className="id-badge conversation-id" title="Conversation ID">{conversation.id?.slice(0, 8)}</span>
              <span className="id-separator">|</span>
              <span className="id-badge message-id" title="Message ID">{firstUserIndex}</span>
            </div>
            <div className="pinned-label">📌 Original Question</div>
            <div className="pinned-actions">
              <button
                className="action-btn redo-btn"
                onClick={() => handleRedo(firstUserIndex)}
                disabled={isLoading}
                title="Re-run council with this message"
              >
                <span className="btn-icon">↻</span>
                <span className="btn-text">Re-run</span>
              </button>
              <button
                className="action-btn edit-btn"
                onClick={() => handleEdit(firstUserIndex, firstUserMessage.content)}
                disabled={isLoading}
                title="Edit and resubmit message"
              >
                <span className="btn-icon">✎</span>
                <span className="btn-text">Edit</span>
              </button>
            </div>
          </div>
          <div className="pinned-content">
            {firstUserMessage.content.length > 200 
              ? firstUserMessage.content.substring(0, 200) + '...'
              : firstUserMessage.content}
          </div>
        </div>
      )}

      <div className="messages-container" ref={messagesContainerRef}>
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div 
              key={index} 
              className="message-group"
              ref={index === firstUserIndex ? firstUserMessageRef : null}
            >
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-ids">
                    <span className="id-badge conversation-id" title="Conversation ID">{conversation.id?.slice(0, 8)}</span>
                    <span className="id-separator">|</span>
                    <span className="id-badge message-id" title="Message ID">{index}</span>
                  </div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <MarkdownRenderer>{msg.content}</MarkdownRenderer>
                    </div>
                    <div className="message-actions">
                      <button
                        className="action-btn redo-btn"
                        onClick={() => handleRedo(index)}
                        disabled={isLoading}
                        title="Re-run council with this message"
                      >
                        <span className="btn-icon">↻</span>
                        <span className="btn-text">Re-run</span>
                      </button>
                      <button
                        className="action-btn edit-btn"
                        onClick={() => handleEdit(index, msg.content)}
                        disabled={isLoading}
                        title="Edit and resubmit message"
                      >
                        <span className="btn-icon">✎</span>
                        <span className="btn-text">Edit</span>
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-ids">
                    <span className="id-badge conversation-id" title="Conversation ID">{conversation.id?.slice(0, 8)}</span>
                    <span className="id-separator">|</span>
                    <span className="id-badge message-id" title="Message ID">{index}</span>
                  </div>
                  <div className="message-label">
                    LLM Council
                    {msg.classification && (
                      <span className={`classification-badge ${msg.classification.type || 'unknown'}`}>
                        {msg.classification.status === 'classifying' ? '🔍 Classifying...' : 
                         msg.classification.status === 'complete' ? 
                           (msg.responseType === 'direct' ? '⚡ Direct' : '🤔 Deliberation') :
                           '🔍 Classifying...'}
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

                  {/* Multi-step tool calls - collapsible area */}
                  {(msg.toolSteps && msg.toolSteps.length > 0) && (
                    <ToolSteps 
                      toolSteps={msg.toolSteps}
                    />
                  )}

                  {/* Single tool result card - for backward compatibility when no toolSteps */}
                  {/* Only show if toolResult exists but no toolSteps (legacy format) */}
                  {(msg.toolResult || msg.tool_result) && (!msg.toolSteps || msg.toolSteps.length === 0) && (() => {
                    const toolData = msg.toolResult || msg.tool_result;
                    const toolName = toolData.tool || `${toolData.server}.${toolData.tool}`;
                    const execTime = toolData.executionTime;
                    const input = toolData.input;
                    const output = toolData.output;
                    
                    // Extract output text for display
                    let outputText = '';
                    if (typeof output === 'string') {
                      outputText = output;
                    } else if (output?.content?.[0]?.text) {
                      outputText = output.content[0].text;
                    } else {
                      outputText = JSON.stringify(output, null, 2);
                    }
                    
                    // Truncate long output
                    const truncatedOutput = outputText.length > 500 
                      ? outputText.substring(0, 500) + '...' 
                      : outputText;
                    
                    return (
                      <div className="tool-result-card">
                        <div className="tool-result-header">
                          <span className="tool-icon">🔧</span>
                          <span className="tool-name">MCP Tool: {toolName}</span>
                          {execTime !== undefined && (
                            <span className="tool-time">{execTime}s</span>
                          )}
                        </div>
                        <div className="tool-result-body">
                          <div className="tool-io">
                            <span className="tool-label">Input:</span>
                            <code className="tool-value">{JSON.stringify(input)}</code>
                          </div>
                          <div className="tool-io">
                            <span className="tool-label">Output:</span>
                            <code className="tool-value">{typeof output === 'string' ? output : JSON.stringify(output)}</code>
                          </div>
                        </div>
                        
                        {/* Hover overlay with detailed stats */}
                        <div className="tool-stats-overlay">
                          <div className="tool-stats-title">📊 Tool Call Details</div>
                          <div className="tool-stats-row">
                            <span className="tool-stats-label">Server</span>
                            <span className="tool-stats-value">{toolData.server || 'unknown'}</span>
                          </div>
                          <div className="tool-stats-row">
                            <span className="tool-stats-label">Tool</span>
                            <span className="tool-stats-value">{toolData.tool || toolName}</span>
                          </div>
                          <div className="tool-stats-row">
                            <span className="tool-stats-label">Execution Time</span>
                            <span className="tool-stats-value">{execTime !== undefined ? `${execTime}s` : 'N/A'}</span>
                          </div>
                          <div className="tool-stats-row">
                            <span className="tool-stats-label">Status</span>
                            <span className={`tool-stats-value ${toolData.success !== false ? 'success' : 'error'}`}>
                              {toolData.success !== false ? '✓ Success' : '✗ Failed'}
                            </span>
                          </div>
                          <div className="tool-stats-output">
                            <div className="tool-stats-output-label">Full Output:</div>
                            <div className="tool-stats-output-value">{truncatedOutput}</div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}

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
