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
  
  // Pinned conversations (stored in localStorage)
  const [pinnedIds, setPinnedIds] = useState(() => {
    const saved = localStorage.getItem('llm-council-pinned');
    return saved ? JSON.parse(saved) : [];
  });
  
  // Conversation Filter System (CFS) state
  const [showCfsOverlay, setShowCfsOverlay] = useState(false);
  const [activeFilterGroup, setActiveFilterGroup] = useState('user'); // Active group name - default to 'user'
  const cfsOverlayRef = useRef(null);
  const [isDeletingDuplicates, setIsDeletingDuplicates] = useState(false);
  
  // CFS custom groups (stored in localStorage)
  const [cfsGroups, setCfsGroups] = useState(() => {
    const saved = localStorage.getItem('llm-council-cfs-groups');
    return saved ? JSON.parse(saved) : [
      { name: 'all', label: 'All', rules: [], isDefault: true },
      { name: 'user', label: 'User', rules: [{ type: 'exclude', tags: ['#auto', '#test'], logic: 'AND' }], isDefault: true },
      { name: 'test', label: 'Test', rules: [{ type: 'include', tags: ['#auto', '#test'], logic: 'AND' }], isDefault: true },
    ];
  });
  const [editingGroup, setEditingGroup] = useState(null);
  const [newGroupName, setNewGroupName] = useState('');
  const [newTagInput, setNewTagInput] = useState('');
  
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

  // Save CFS groups to localStorage when changed
  useEffect(() => {
    localStorage.setItem('llm-council-cfs-groups', JSON.stringify(cfsGroups));
  }, [cfsGroups]);

  // CFS group management functions
  const addGroup = () => {
    if (!newGroupName.trim()) return;
    const groupName = newGroupName.trim().toLowerCase().replace(/\s+/g, '_');
    if (cfsGroups.some(g => g.name === groupName)) {
      alert('A group with this name already exists');
      return;
    }
    setCfsGroups([...cfsGroups, { 
      name: groupName, 
      label: newGroupName.trim(), 
      rules: [], 
      isDefault: false 
    }]);
    setNewGroupName('');
  };

  const removeGroup = (groupName) => {
    const group = cfsGroups.find(g => g.name === groupName);
    if (group?.isDefault) {
      alert('Cannot remove default groups');
      return;
    }
    setCfsGroups(cfsGroups.filter(g => g.name !== groupName));
    if (activeFilterGroup === groupName) {
      setActiveFilterGroup('all');
    }
  };

  const addRule = (groupName, ruleType) => {
    setCfsGroups(cfsGroups.map(g => {
      if (g.name === groupName) {
        return {
          ...g,
          rules: [...g.rules, { type: ruleType, tags: [], logic: 'AND' }]
        };
      }
      return g;
    }));
  };

  const removeRule = (groupName, ruleIndex) => {
    setCfsGroups(cfsGroups.map(g => {
      if (g.name === groupName) {
        return {
          ...g,
          rules: g.rules.filter((_, i) => i !== ruleIndex)
        };
      }
      return g;
    }));
  };

  const addTagToRule = (groupName, ruleIndex, tag) => {
    if (!tag.trim()) return;
    const normalizedTag = tag.startsWith('#') ? tag.toLowerCase() : `#${tag.toLowerCase()}`;
    setCfsGroups(cfsGroups.map(g => {
      if (g.name === groupName) {
        return {
          ...g,
          rules: g.rules.map((rule, i) => {
            if (i === ruleIndex && !rule.tags.includes(normalizedTag)) {
              return { ...rule, tags: [...rule.tags, normalizedTag] };
            }
            return rule;
          })
        };
      }
      return g;
    }));
  };

  const removeTagFromRule = (groupName, ruleIndex, tag) => {
    setCfsGroups(cfsGroups.map(g => {
      if (g.name === groupName) {
        return {
          ...g,
          rules: g.rules.map((rule, i) => {
            if (i === ruleIndex) {
              return { ...rule, tags: rule.tags.filter(t => t !== tag) };
            }
            return rule;
          })
        };
      }
      return g;
    }));
  };

  const toggleRuleLogic = (groupName, ruleIndex) => {
    setCfsGroups(cfsGroups.map(g => {
      if (g.name === groupName) {
        return {
          ...g,
          rules: g.rules.map((rule, i) => {
            if (i === ruleIndex) {
              return { ...rule, logic: rule.logic === 'AND' ? 'OR' : 'AND' };
            }
            return rule;
          })
        };
      }
      return g;
    }));
  };

  // Check if conversation matches current filter using rules-based system
  const conversationMatchesFilter = (conv) => {
    const group = cfsGroups.find(g => g.name === activeFilterGroup);
    if (!group || group.rules.length === 0) return true; // 'all' or empty rules = show everything
    
    // Get tags from metadata (populated by backend)
    const convTags = new Set((conv.tags || []).map(t => t.toLowerCase()));
    
    // Apply all rules - all rules must pass (AND between rules)
    for (const rule of group.rules) {
      if (rule.tags.length === 0) continue; // Empty rule = skip
      
      const matchFunction = rule.logic === 'AND'
        ? rule.tags.every(t => convTags.has(t))  // All tags must match
        : rule.tags.some(t => convTags.has(t));   // Any tag must match
      
      if (rule.type === 'include' && !matchFunction) {
        return false; // Must include but doesn't match
      }
      if (rule.type === 'exclude' && matchFunction) {
        return false; // Must exclude but matches
      }
    }
    
    return true;
  };

  // Toggle pin status for a conversation
  const togglePin = (conversationId, event) => {
    event.stopPropagation();
    setPinnedIds(prev => {
      const newPinned = prev.includes(conversationId)
        ? prev.filter(id => id !== conversationId)
        : [...prev, conversationId];
      localStorage.setItem('llm-council-pinned', JSON.stringify(newPinned));
      return newPinned;
    });
  };

  // Filter conversations to exclude duplicates and apply CFS filter
  const filteredConversations = conversations
    .filter(conv => !duplicateIds.has(conv.id))
    .filter(conversationMatchesFilter);

  // Sort: pinned first, then by date (most recent first)
  const sortedConversations = [...filteredConversations].sort((a, b) => {
    const aPinned = pinnedIds.includes(a.id);
    const bPinned = pinnedIds.includes(b.id);
    if (aPinned && !bPinned) return -1;
    if (!aPinned && bPinned) return 1;
    // Both pinned or both unpinned - maintain original order (by date)
    return 0;
  });

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
      <div className="cfs-container">
        <div className="cfs-tabs">
          {cfsGroups.map(group => (
            <button 
              key={group.name}
              className={`cfs-tab ${activeFilterGroup === group.name ? 'active' : ''}`}
              onClick={() => setActiveFilterGroup(group.name)}
              title={group.rules.length > 0 ? `Rules: ${group.rules.map(r => `${r.type} ${r.tags.join(` ${r.logic} `)}`).join('; ')}` : 'No rules - show all'}
            >
              {group.label}
            </button>
          ))}
          <button 
            className="cfs-config-btn"
            onClick={() => setShowCfsOverlay(!showCfsOverlay)}
            title="Configure filter groups"
          >
            ⚙️
          </button>
        </div>
        
        {/* CFS Configuration Overlay */}
        {showCfsOverlay && (
          <div className="cfs-overlay" ref={cfsOverlayRef}>
            <div className="cfs-overlay-header">
              <span>Filter Groups</span>
              <button className="cfs-close-btn" onClick={() => setShowCfsOverlay(false)}>✕</button>
            </div>
            
            {/* Add new group */}
            <div className="cfs-add-group">
              <input 
                type="text"
                placeholder="New group name..."
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addGroup()}
              />
              <button onClick={addGroup} title="Add group">+</button>
            </div>
            
            {/* Group list */}
            <div className="cfs-group-list">
              {cfsGroups.map(group => (
                <div key={group.name} className="cfs-group-item">
                  <div className="cfs-group-header">
                    <span className="cfs-group-name">{group.label}</span>
                    {group.isDefault && <span className="cfs-default-badge">default</span>}
                    {!group.isDefault && (
                      <button 
                        className="cfs-remove-group-btn"
                        onClick={() => removeGroup(group.name)}
                        title="Remove group"
                      >−</button>
                    )}
                    <button 
                      className="cfs-edit-rules-btn"
                      onClick={() => setEditingGroup(editingGroup === group.name ? null : group.name)}
                      title="Edit rules"
                    >
                      {editingGroup === group.name ? '▲' : '▼'}
                    </button>
                  </div>
                  
                  {/* Rules editor (expanded) */}
                  {editingGroup === group.name && (
                    <div className="cfs-rules-editor">
                      {group.rules.length === 0 && (
                        <div className="cfs-no-rules">No rules (shows all conversations)</div>
                      )}
                      
                      {group.rules.map((rule, ruleIndex) => (
                        <div key={ruleIndex} className={`cfs-rule ${rule.type}`}>
                          <div className="cfs-rule-header">
                            <span className={`cfs-rule-type ${rule.type}`}>
                              {rule.type === 'include' ? '✓ Include' : '✗ Exclude'}
                            </span>
                            <button 
                              className={`cfs-logic-toggle ${rule.logic.toLowerCase()}`}
                              onClick={() => toggleRuleLogic(group.name, ruleIndex)}
                              title={`Click to switch to ${rule.logic === 'AND' ? 'OR' : 'AND'}`}
                            >
                              {rule.logic}
                            </button>
                            <button 
                              className="cfs-remove-rule-btn"
                              onClick={() => removeRule(group.name, ruleIndex)}
                              title="Remove rule"
                            >✕</button>
                          </div>
                          
                          <div className="cfs-rule-tags">
                            {rule.tags.map(tag => (
                              <span key={tag} className="cfs-tag">
                                {tag}
                                <button onClick={() => removeTagFromRule(group.name, ruleIndex, tag)}>×</button>
                              </span>
                            ))}
                            <input 
                              type="text"
                              className="cfs-tag-input"
                              placeholder="+ tag"
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' && e.target.value) {
                                  addTagToRule(group.name, ruleIndex, e.target.value);
                                  e.target.value = '';
                                }
                              }}
                            />
                          </div>
                        </div>
                      ))}
                      
                      {/* Add rule buttons */}
                      <div className="cfs-add-rules">
                        <button 
                          className="cfs-add-rule-btn include"
                          onClick={() => addRule(group.name, 'include')}
                        >+ Include Rule</button>
                        <button 
                          className="cfs-add-rule-btn exclude"
                          onClick={() => addRule(group.name, 'exclude')}
                        >+ Exclude Rule</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="conversation-list">
        {!isRecycleBinView ? (
          // Active conversations view (excluding duplicates which are shown separately)
          <>
            {sortedConversations.length === 0 ? (
              <div className="no-conversations">No conversations yet</div>
            ) : (
              sortedConversations.map((conv) => {
                const status = titleGenerationStatus[conv.id];
                const isGeneratingTitle = conv.titleGenerating || (status?.status && 
                  ['generating_immediate', 'thinking_immediate'].includes(status.status));
                const isPinned = pinnedIds.includes(conv.id);
                
                return (
                  <div
                    key={conv.id}
                    className={`conversation-item ${
                      conv.id === currentConversationId ? 'active' : ''
                    } ${isGeneratingTitle ? 'generating-title' : ''} ${isPinned ? 'pinned' : ''}`}
                    onClick={() => onSelectConversation(conv.id)}
                    title={conv.title || 'New Conversation'}
                  >
                    <div className="conversation-content">
                      <div className="conversation-title">
                        {isPinned && <span className="pin-indicator">📌 </span>}
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
                      className={`pin-btn ${isPinned ? 'pinned' : ''}`}
                      onClick={(e) => togglePin(conv.id, e)}
                      title={isPinned ? 'Unpin conversation' : 'Pin conversation'}
                    >
                      {isPinned ? '📌' : '📍'}
                    </button>
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
