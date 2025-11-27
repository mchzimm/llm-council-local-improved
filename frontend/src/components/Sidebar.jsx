import { useState, useEffect } from 'react';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  currentConversationId,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onRestoreConversation,
  newConversationDisabled = false,
  titleGenerationStatus = {},
}) {
  const [isRecycleBinView, setIsRecycleBinView] = useState(false);
  const [deletedConversations, setDeletedConversations] = useState([]);
  const [hoveredDeleteBtn, setHoveredDeleteBtn] = useState(null);

  // Fetch deleted conversations when entering recycle bin view
  useEffect(() => {
    if (isRecycleBinView) {
      fetchDeletedConversations();
    }
  }, [isRecycleBinView]);

  const fetchDeletedConversations = async () => {
    try {
      const response = await fetch('http://localhost:8001/api/conversations/deleted');
      if (response.ok) {
        const deleted = await response.json();
        setDeletedConversations(deleted);
      }
    } catch (error) {
      console.error('Failed to fetch deleted conversations:', error);
    }
  };

  const handleDeleteConversation = async (conversationId, event) => {
    event.stopPropagation();
    try {
      const response = await fetch(`http://localhost:8001/api/conversations/${conversationId}/delete`, {
        method: 'PATCH',
      });
      
      if (response.ok) {
        onDeleteConversation(conversationId);
      } else {
        console.error('Delete failed with status:', response.status);
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleRestoreConversation = async (conversationId, event) => {
    event.stopPropagation();
    try {
      const response = await fetch(`http://localhost:8001/api/conversations/${conversationId}/restore`, {
        method: 'PATCH',
      });
      
      if (response.ok) {
        onRestoreConversation(conversationId);
        // Refresh deleted conversations list
        fetchDeletedConversations();
      } else {
        console.error('Restore failed with status:', response.status);
      }
    } catch (error) {
      console.error('Failed to restore conversation:', error);
    }
  };

  const recycleBinCount = deletedConversations.length;

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1>LLM Council</h1>
        {!isRecycleBinView ? (
          <button 
            className={`new-conversation-btn ${newConversationDisabled ? 'disabled' : ''}`}
            onClick={newConversationDisabled ? undefined : onNewConversation}
            disabled={newConversationDisabled}
          >
            + New Conversation
          </button>
        ) : (
          <button 
            className="back-btn" 
            onClick={() => setIsRecycleBinView(false)}
          >
            ← Back to Conversations
          </button>
        )}
      </div>

      <div className="separator" />

      <div className="conversation-list">
        {!isRecycleBinView ? (
          // Active conversations view
          <>
            {conversations.length === 0 ? (
              <div className="no-conversations">No conversations yet</div>
            ) : (
              conversations.map((conv) => {
                const status = titleGenerationStatus[conv.id];
                const isGeneratingTitle = conv.titleGenerating || (status?.status && 
                  ['generating_immediate', 'thinking_immediate'].includes(status.status));
                
                return (
                  <div
                    key={conv.id}
                    className={`conversation-item ${
                      conv.id === currentConversationId ? 'active' : ''
                    } ${isGeneratingTitle ? 'generating-title' : ''}`}
                    onClick={() => onSelectConversation(conv.id)}
                    title={conv.title || 'New Conversation'}
                  >
                    <div className="conversation-content">
                      <div className="conversation-title">
                        {isGeneratingTitle && (
                          <span className="title-generation-indicator">⏳ </span>
                        )}
                        {isGeneratingTitle ? 'Generating title...' : (conv.title || 'New Conversation')}
                      </div>
                      <div className="conversation-meta">
                        {conv.message_count} messages
                      </div>
                      {status?.status === 'thinking_immediate' && status.data?.thinking && (
                        <div className="thinking-progress">
                          <details>
                            <summary>Thinking...</summary>
                            <div className="thinking-content">
                              {status.data.thinking}
                            </div>
                          </details>
                        </div>
                      )}
                    </div>
                    <button 
                      className={`delete-btn ${hoveredDeleteBtn === conv.id ? 'hovered' : ''}`}
                      onMouseEnter={() => setHoveredDeleteBtn(conv.id)}
                      onMouseLeave={() => setHoveredDeleteBtn(null)}
                      onClick={(e) => handleDeleteConversation(conv.id, e)}
                      title="Move to recycle bin"
                    >
                      {hoveredDeleteBtn === conv.id ? '❌' : '✖️'}
                    </button>
                  </div>
                );
              })
            )}
          </>
        ) : (
          // Recycle bin view
          <>
            <div className="section-header">
              <h3>Deleted Conversations</h3>
            </div>
            {deletedConversations.length === 0 ? (
              <div className="empty-bin-message">Recycle bin is empty</div>
            ) : (
              deletedConversations.map((conv) => (
                <div
                  key={conv.id}
                  className="conversation-item deleted"
                >
                  <div className="conversation-content">
                    <div className="conversation-title">
                      {conv.title || 'New Conversation'}
                    </div>
                    <div className="conversation-meta">
                      {conv.message_count} messages • Deleted
                    </div>
                  </div>
                  <button 
                    className="restore-btn"
                    onClick={(e) => handleRestoreConversation(conv.id, e)}
                    title="Restore conversation"
                  >
                    ⟲
                  </button>
                </div>
              ))
            )}
          </>
        )}
      </div>

      {!isRecycleBinView && (
        <>
          <div className="separator" />
          <button 
            className="recycle-bin-btn" 
            onClick={() => setIsRecycleBinView(true)}
          >
            <span className="bin-icon">🗑️</span>
            <span className="bin-label">Recycle Bin</span>
            {recycleBinCount > 0 && (
              <span className="bin-count">{recycleBinCount}</span>
            )}
          </button>
          <div className="separator" />
        </>
      )}
    </div>
  );
}
