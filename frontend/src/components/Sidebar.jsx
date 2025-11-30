import { useState, useEffect, useRef } from 'react';
import { api } from '../api';
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
  const [duplicateInfo, setDuplicateInfo] = useState(null);
  
  // Conversation Filter System (CFS) state
  const [showCfsOverlay, setShowCfsOverlay] = useState(false);
  const [activeFilterGroup, setActiveFilterGroup] = useState('all'); // 'all', 'user', 'test'
  const cfsOverlayRef = useRef(null);
  const [isDeletingDuplicates, setIsDeletingDuplicates] = useState(false);
  
  // MCP status state
  const [mcpStatus, setMcpStatus] = useState(null);
  const [showMcpOverlay, setShowMcpOverlay] = useState(false);
  const [hoveredServer, setHoveredServer] = useState(null);
  const overlayRef = useRef(null);
  const serverOverlayRef = useRef(null);
  const overlayCloseTimerRef = useRef(null);

  // Track if cursor is within any overlay group element
  const isInOverlayGroupRef = useRef(false);
  const hoverCheckTimerRef = useRef(null);

  // Overlay group hover handlers - 2s delay before closing
  const handleOverlayGroupEnter = () => {
    isInOverlayGroupRef.current = true;
    if (overlayCloseTimerRef.current) {
      clearTimeout(overlayCloseTimerRef.current);
      overlayCloseTimerRef.current = null;
    }
    if (hoverCheckTimerRef.current) {
      clearTimeout(hoverCheckTimerRef.current);
      hoverCheckTimerRef.current = null;
    }
    setShowMcpOverlay(true);
  };

  const handleOverlayGroupLeave = () => {
    isInOverlayGroupRef.current = false;
    // Small delay to check if cursor moved to another element in the group
    hoverCheckTimerRef.current = setTimeout(() => {
      if (!isInOverlayGroupRef.current) {
        // Cursor is truly outside all overlay group elements, start close timer
        overlayCloseTimerRef.current = setTimeout(() => {
          if (!isInOverlayGroupRef.current) {
            setShowMcpOverlay(false);
            setHoveredServer(null);
          }
        }, 2000);
      }
    }, 50); // 50ms grace period for cursor transition between elements
  };

  // Clean up overlay close timer on unmount
  useEffect(() => {
    return () => {
      if (overlayCloseTimerRef.current) {
        clearTimeout(overlayCloseTimerRef.current);
      }
      if (hoverCheckTimerRef.current) {
        clearTimeout(hoverCheckTimerRef.current);
      }
    };
  }, []);

  // Fetch MCP status on mount and periodically
  useEffect(() => {
    const fetchMcpStatus = async () => {
      try {
        const status = await api.getMcpStatus();
        setMcpStatus(status);
      } catch (error) {
        console.error('Failed to fetch MCP status:', error);
      }
    };
    
    fetchMcpStatus();
    const interval = setInterval(fetchMcpStatus, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  // Fetch deleted conversations when entering recycle bin view
  useEffect(() => {
    if (isRecycleBinView) {
      fetchDeletedConversations();
    }
  }, [isRecycleBinView]);

  // Fetch duplicate info on mount and when conversations change
  useEffect(() => {
    fetchDuplicateInfo();
  }, [conversations]);

  const fetchDuplicateInfo = async () => {
    try {
      const response = await fetch('http://localhost:8001/api/conversations/duplicates');
      if (response.ok) {
        const info = await response.json();
        setDuplicateInfo(info);
      }
    } catch (error) {
      console.error('Failed to fetch duplicate info:', error);
    }
  };

  const handleDeleteDuplicates = async () => {
    if (isDeletingDuplicates) return;
    
    const totalDuplicates = duplicateInfo?.groups?.reduce(
      (sum, g) => sum + g.conversations.length - 1, 0
    ) || 0;
    
    if (!confirm(`This will move ${totalDuplicates} duplicate conversation(s) to the recycle bin, keeping the newest copy of each. Continue?`)) {
      return;
    }
    
    setIsDeletingDuplicates(true);
    try {
      const response = await fetch('http://localhost:8001/api/conversations/duplicates/delete?keep_newest=true', {
        method: 'POST',
      });
      if (response.ok) {
        const result = await response.json();
        alert(`Deleted ${result.conversations_deleted} duplicate(s), kept ${result.conversations_kept} unique conversation(s).`);
        // Refresh conversations list
        window.location.reload();
      } else {
        alert('Failed to delete duplicates');
      }
    } catch (error) {
      console.error('Failed to delete duplicates:', error);
      alert('Error deleting duplicates');
    } finally {
      setIsDeletingDuplicates(false);
    }
  };

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

  // Get IDs of duplicate conversations (not the first/newest in each group)
  const duplicateIds = new Set();
  if (duplicateInfo?.groups) {
    duplicateInfo.groups.forEach(group => {
      // Skip first conversation (newest), mark rest as duplicates
      group.conversations.slice(1).forEach(conv => {
        duplicateIds.add(conv.id);
      });
    });
  }

  // Extract tags from conversation (looks for <!-- tags: #tag1 #tag2 | ... --> pattern)
  const getConversationTags = (conv) => {
    const tags = new Set();
    if (conv.messages) {
      for (const msg of conv.messages) {
        if (msg.content) {
          const match = msg.content.match(/<!--\s*tags:\s*([^|]+)/i);
          if (match) {
            const tagStr = match[1];
            const foundTags = tagStr.match(/#\w+/g);
            if (foundTags) {
              foundTags.forEach(t => tags.add(t.toLowerCase()));
            }
          }
        }
      }
    }
    return tags;
  };

  // Check if conversation matches current filter
  const conversationMatchesFilter = (conv) => {
    if (activeFilterGroup === 'all') return true;
    
    const tags = getConversationTags(conv);
    
    if (activeFilterGroup === 'user') {
      // User group: exclude conversations with #auto or #test tags
      return !tags.has('#auto') && !tags.has('#test');
    }
    
    if (activeFilterGroup === 'test') {
      // Test group: include only conversations with both #auto AND #test
      return tags.has('#auto') && tags.has('#test');
    }
    
    return true;
  };

  // Filter conversations to exclude duplicates and apply CFS filter
  const filteredConversations = conversations
    .filter(conv => !duplicateIds.has(conv.id))
    .filter(conversationMatchesFilter);

  // Get tools for a specific server
  const getServerTools = (serverName) => {
    if (!mcpStatus?.tool_details) return [];
    return mcpStatus.tool_details.filter(t => t.server === serverName);
  };

  // Calculate metrics
  const totalServers = mcpStatus?.server_details?.length || 0;
  const availableServers = mcpStatus?.server_details?.filter(s => s.status === 'available').length || 0;
  const totalTools = mcpStatus?.tool_details?.length || 0;
  const activeTools = Object.keys(mcpStatus?.tools_in_use || {}).length;

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div 
          className="title-area"
          onMouseEnter={handleOverlayGroupEnter}
          onMouseLeave={handleOverlayGroupLeave}
        >
          <h1>LLM Council</h1>
          {mcpStatus?.enabled && (
            <span className="mcp-badge">MCP</span>
          )}
          
          {/* MCP Server Status Overlay */}
          {showMcpOverlay && mcpStatus && (
            <div 
              className="mcp-overlay" 
              ref={overlayRef}
              onMouseEnter={handleOverlayGroupEnter}
              onMouseLeave={handleOverlayGroupLeave}
            >
              <div className="mcp-overlay-header">MCP Servers</div>
              <div className="mcp-server-list">
                {mcpStatus.server_details?.map((server) => (
                  <div 
                    key={server.name}
                    className="mcp-server-item"
                    onMouseEnter={() => setHoveredServer(server.name)}
                  >
                    <span className={`status-indicator status-${server.status}`} />
                    <span className="server-name">{server.name}</span>
                    <span className="server-port">:{server.port}</span>
                    
                    {/* Tool Overlay for this server */}
                    {hoveredServer === server.name && (
                      <div 
                        className="mcp-tools-overlay" 
                        ref={serverOverlayRef}
                        onMouseEnter={handleOverlayGroupEnter}
                        onMouseLeave={handleOverlayGroupLeave}
                      >
                        <div className="mcp-overlay-header">{server.name} Tools</div>
                        <div className="mcp-tool-list">
                          {getServerTools(server.name).map((tool) => (
                            <div 
                              key={tool.name}
                              className={`mcp-tool-item ${tool.in_use ? 'in-use' : ''}`}
                            >
                              <span className="tool-name">{tool.name.split('.')[1]}</span>
                            </div>
                          ))}
                        </div>
                        <div className="mcp-overlay-metrics">
                          {getServerTools(server.name).length} tools
                          {server.busy_tools > 0 && ` • ${server.busy_tools} active`}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="mcp-overlay-metrics">
                {availableServers}/{totalServers} servers available • {totalTools} tools
                {activeTools > 0 && ` • ${activeTools} active`}
              </div>
            </div>
          )}
        </div>
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

      {/* Conversation Filter System (CFS) */}
      <div className="cfs-tabs">
        <button 
          className={`cfs-tab ${activeFilterGroup === 'all' ? 'active' : ''}`}
          onClick={() => setActiveFilterGroup('all')}
          title="Show all conversations"
        >
          All
        </button>
        <button 
          className={`cfs-tab ${activeFilterGroup === 'user' ? 'active' : ''}`}
          onClick={() => setActiveFilterGroup('user')}
          title="Show user conversations (exclude #auto #test)"
        >
          User
        </button>
        <button 
          className={`cfs-tab ${activeFilterGroup === 'test' ? 'active' : ''}`}
          onClick={() => setActiveFilterGroup('test')}
          title="Show test conversations (#auto AND #test)"
        >
          Test
        </button>
      </div>

      <div className="conversation-list">
        {!isRecycleBinView ? (
          // Active conversations view (excluding duplicates which are shown separately)
          <>
            {filteredConversations.length === 0 ? (
              <div className="no-conversations">No conversations yet</div>
            ) : (
              filteredConversations.map((conv) => {
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
          {duplicateInfo && duplicateInfo.duplicate_groups > 0 && (
            <>
              <details className="duplicates-section">
                <summary className="duplicates-header">
                  <span className="duplicates-icon">📋</span>
                  <span className="duplicates-label">Duplicates</span>
                  <span className="duplicates-count">
                    {duplicateInfo.groups?.reduce((sum, g) => sum + g.conversations.length - 1, 0) || 0}
                  </span>
                </summary>
                <div className="duplicates-list">
                  {duplicateInfo.groups?.map((group) => (
                    <div key={group.signature} className="duplicate-group">
                      <div className="duplicate-group-header">
                        {group.query_count} query(ies): "{group.first_query.substring(0, 40)}..."
                      </div>
                      {group.conversations.slice(1).map((conv, idx) => (
                        <div 
                          key={conv.id} 
                          className="conversation-item duplicate-item"
                          onClick={() => onSelectConversation(conv.id)}
                        >
                          <span className="duplicate-marker">⤷</span>
                          <span className="conversation-title">{conv.title}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </details>
              <button 
                className="duplicate-cleanup-btn" 
                onClick={handleDeleteDuplicates}
                disabled={isDeletingDuplicates}
                title={`Found ${duplicateInfo.duplicate_groups} group(s) of duplicate conversations`}
              >
                <span className="cleanup-icon">🧹</span>
                <span className="cleanup-label">
                  {isDeletingDuplicates ? 'Cleaning...' : 'Clean Duplicates'}
                </span>
                <span className="duplicate-count">
                  {duplicateInfo.groups?.reduce((sum, g) => sum + g.conversations.length - 1, 0) || 0}
                </span>
              </button>
            </>
          )}
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
