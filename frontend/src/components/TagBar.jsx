import { useState } from 'react';
import { api } from '../api';
import './TagBar.css';

/**
 * TagBar component for displaying and managing message tags.
 * Shows below the blue line of user/AI messages.
 */
export default function TagBar({
  conversationId,
  messageIndex,
  role,  // 'user' or 'assistant'
  messageContent,
  aiResponse,  // Only provided for user messages
  existingTags = [],
  onTagsUpdated,
}) {
  const [isAddingTag, setIsAddingTag] = useState(false);
  const [newTag, setNewTag] = useState('');
  const [isCheckingTags, setIsCheckingTags] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Extract tags from content if not provided
  const currentTags = existingTags.length > 0 
    ? existingTags 
    : extractTags(messageContent);

  function extractTags(content) {
    if (!content) return [];
    const match = content.match(/<!--\s*tags:\s*([^|]+)/i);
    if (match) {
      return match[1].match(/#\w+/g) || [];
    }
    return [];
  }

  const handleAddTag = async () => {
    if (!newTag.trim()) return;
    
    const tag = newTag.startsWith('#') ? newTag.toLowerCase() : `#${newTag.toLowerCase()}`;
    
    try {
      await api.addMessageTags(conversationId, messageIndex, [tag]);
      if (onTagsUpdated) {
        onTagsUpdated([...currentTags, tag]);
      }
      setNewTag('');
      setIsAddingTag(false);
    } catch (error) {
      console.error('Failed to add tag:', error);
    }
  };

  const handleCheckMissingTags = async () => {
    setIsCheckingTags(true);
    try {
      // For user messages, use aiResponse; for AI messages, use messageContent
      const userMsg = role === 'user' ? messageContent : '';
      const aiMsg = role === 'user' ? aiResponse : messageContent;
      
      const result = await api.checkMissingTags(userMsg, aiMsg, currentTags);
      
      if (result.has_suggestions) {
        setSuggestions(result.suggestions);
        setShowSuggestions(true);
      } else {
        // Show a brief "no suggestions" message
        setSuggestions(['✓ No missing tags']);
        setShowSuggestions(true);
        setTimeout(() => {
          setShowSuggestions(false);
          setSuggestions([]);
        }, 2000);
      }
    } catch (error) {
      console.error('Failed to check tags:', error);
    } finally {
      setIsCheckingTags(false);
    }
  };

  const handleAddSuggestion = async (tag) => {
    try {
      await api.addMessageTags(conversationId, messageIndex, [tag]);
      if (onTagsUpdated) {
        onTagsUpdated([...currentTags, tag]);
      }
      // Remove from suggestions
      setSuggestions(prev => prev.filter(t => t !== tag));
      if (suggestions.length <= 1) {
        setShowSuggestions(false);
      }
    } catch (error) {
      console.error('Failed to add suggested tag:', error);
    }
  };

  return (
    <div className={`tag-bar ${role}`}>
      {/* Existing tags */}
      <div className="tag-list">
        {currentTags.map((tag, idx) => (
          <span key={idx} className="tag">
            {tag}
          </span>
        ))}
      </div>

      {/* Add tag button/input */}
      {isAddingTag ? (
        <div className="tag-input-container">
          <input
            type="text"
            className="tag-input"
            placeholder="#tag"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAddTag();
              if (e.key === 'Escape') setIsAddingTag(false);
            }}
            autoFocus
          />
          <button className="tag-confirm-btn" onClick={handleAddTag}>✓</button>
          <button className="tag-cancel-btn" onClick={() => setIsAddingTag(false)}>✕</button>
        </div>
      ) : (
        <button 
          className="add-tag-btn" 
          onClick={() => setIsAddingTag(true)}
          title="Add tag"
        >
          +
        </button>
      )}

      {/* AI check for missing tags */}
      <button
        className={`check-tags-btn ${isCheckingTags ? 'checking' : ''}`}
        onClick={handleCheckMissingTags}
        disabled={isCheckingTags}
        title="AI: Check for missing tags"
      >
        {isCheckingTags ? '⏳' : '✨'}
      </button>

      {/* Tag suggestions */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="tag-suggestions">
          {suggestions[0] === '✓ No missing tags' ? (
            <span className="no-suggestions">{suggestions[0]}</span>
          ) : (
            <>
              <span className="suggestions-label">Suggested:</span>
              {suggestions.map((tag, idx) => (
                <button
                  key={idx}
                  className="suggestion-tag"
                  onClick={() => handleAddSuggestion(tag)}
                  title="Click to add"
                >
                  {tag}
                </button>
              ))}
              <button 
                className="close-suggestions"
                onClick={() => setShowSuggestions(false)}
              >
                ✕
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
