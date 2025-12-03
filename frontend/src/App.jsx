import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [initError, setInitError] = useState(null);
  const [titleGenerationStatus, setTitleGenerationStatus] = useState({}); // conversation_id -> status
  const [memoryNames, setMemoryNames] = useState({ user_name: null, ai_name: null, loaded: false });

  // Load conversations on mount and restore last viewed conversation
  useEffect(() => {
    const initializeApp = async () => {
      console.log('[App] Starting initialization...');
      try {
        setInitError(null);
        console.log('[App] Loading conversations...');
        const convs = await loadConversations(true);  // throwOnError=true during init
        console.log('[App] Loaded', convs?.length || 0, 'conversations');
        
        // Load names from memory (background, non-blocking)
        api.getMemoryNames().then(names => {
          console.log('[App] Loaded memory names:', names);
          setMemoryNames(names);
        }).catch(err => {
          console.warn('[App] Failed to load memory names:', err);
        });
        
        // Restore last viewed conversation from localStorage
        const lastConversationId = localStorage.getItem('lastConversationId');
        if (lastConversationId && convs?.some(c => c.id === lastConversationId)) {
          console.log('[App] Restoring conversation:', lastConversationId);
          setCurrentConversationId(lastConversationId);
          // Load the conversation before showing the app
          try {
            const conv = await api.getConversation(lastConversationId);
            setCurrentConversation(conv);
            console.log('[App] Conversation restored');
          } catch (error) {
            console.error('[App] Failed to restore conversation:', error);
            localStorage.removeItem('lastConversationId');
          }
        } else if (lastConversationId) {
          // Conversation was deleted, clear stale reference
          console.log('[App] Clearing stale lastConversationId');
          localStorage.removeItem('lastConversationId');
        }
        console.log('[App] Initialization complete, setting isInitializing=false');
      } catch (error) {
        console.error('[App] Failed to initialize app:', error);
        setInitError(error.message || 'Failed to connect to backend');
      } finally {
        setIsInitializing(false);
      }
    };
    initializeApp();
  }, []);

  // Load conversation details when selected
  useEffect(() => {
    if (currentConversationId) {
      loadConversation(currentConversationId);
    }
  }, [currentConversationId]);

  // WebSocket connection for real-time title updates
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:8001/ws/title-updates`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
      console.log('WebSocket connected for title updates');
    };
    
    ws.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);
        
        if (update.type === 'title_progress') {
          const { conversation_id, status, title, thinking, ...rest } = update;
          
          // Update title generation status
          setTitleGenerationStatus(prev => ({
            ...prev,
            [conversation_id]: {
              status,
              data: { title, thinking, ...rest },
              timestamp: update.timestamp
            }
          }));
          
          // Update conversation title if completed
          if (status === 'complete_immediate' && title) {
            setConversations(prev => prev.map(conv => 
              conv.id === conversation_id 
                ? { ...conv, title: title }
                : conv
            ));
            
            // Update current conversation if it matches
            if (currentConversationId === conversation_id && currentConversation) {
              setCurrentConversation(prev => ({
                ...prev,
                title: title
              }));
            }
          }
          
          // Show progress indicators
          if (status === 'generating_immediate' || status === 'thinking_immediate') {
            setConversations(prev => prev.map(conv => 
              conv.id === conversation_id 
                ? { ...conv, titleGenerating: true }
                : conv
            ));
          }
          
          // Remove progress indicators when complete
          if (status === 'complete_immediate' || status === 'error_immediate') {
            setConversations(prev => prev.map(conv => 
              conv.id === conversation_id 
                ? { ...conv, titleGenerating: false }
                : conv
            ));
          }
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
      console.log('WebSocket connection closed');
    };
    
    // Cleanup on component unmount
    return () => {
      ws.close();
    };
  }, [currentConversationId, currentConversation]);

  const loadConversations = async (throwOnError = false) => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
      return convs;
    } catch (error) {
      console.error('Failed to load conversations:', error);
      if (throwOnError) {
        throw error;
      }
      return [];
    }
  };

  const loadConversation = async (id) => {
    try {
      const conv = await api.getConversation(id);
      setCurrentConversation(conv);
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await api.createConversation();
      // Refresh conversations list to maintain proper sorting order
      await loadConversations();
      setCurrentConversationId(newConv.id);
      // Persist to localStorage for restore on refresh
      localStorage.setItem('lastConversationId', newConv.id);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleDeleteConversation = (conversationId) => {
    // Remove from conversations list
    setConversations(prev => prev.filter(conv => conv.id !== conversationId));
    
    // If the deleted conversation was active, clear the selection
    if (currentConversationId === conversationId) {
      setCurrentConversationId(null);
      setCurrentConversation(null);
      // Clear from localStorage
      localStorage.removeItem('lastConversationId');
    }
  };

  const handleRestoreConversation = (conversationId) => {
    // Refresh the conversations list to include restored conversation
    loadConversations();
  };

  const handleSelectConversation = (id) => {
    setCurrentConversationId(id);
    // Persist to localStorage for restore on refresh
    if (id) {
      localStorage.setItem('lastConversationId', id);
    }
  };

  // Check if new conversation button should be disabled
  const isNewConversationDisabled = () => {
    return currentConversation && !currentConversation.messages?.length;
  };

  const handleSendMessage = async (content) => {
    if (!currentConversationId) return;

    setIsLoading(true);
    try {
      // Optimistically add user message to UI
      const userMessage = { role: 'user', content };
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...(prev?.messages || []), userMessage],
      }));

      // Create a partial assistant message that will be updated progressively
      // Now includes streaming state for token-level updates
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        classification: { status: 'classifying' },  // Start with classifying status
        loading: {
          stage1: false,
          stage2: false,
          stage3: false,
        },
        streaming: {
          stage1: {},  // model -> { content, thinking, isStreaming }
          stage2: {},
          stage3: { content: '', thinking: '', isStreaming: false },
        },
      };

      // Add the partial assistant message
      setCurrentConversation((prev) => ({
        ...prev,
        messages: [...(prev?.messages || []), assistantMessage],
      }));

      // Send message with token-level streaming
      await api.sendMessageStreamTokens(currentConversationId, content, (eventType, event) => {
        switch (eventType) {
          case 'classification_start':
            // Classification started
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.classification = { status: 'classifying' };
              return { ...prev, messages };
            });
            break;

          case 'classification_complete':
            // Classification complete - store result with status
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.classification = { ...event.classification, status: 'complete' };
              return { ...prev, messages };
            });
            break;

          case 'memory_check_start':
            // Memory check started
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.memoryStatus = { status: 'searching', query: event.query };
              return { ...prev, messages };
            });
            break;

          case 'memory_search_complete':
            // Memory search returned results
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.memoryStatus = {
                ...lastMsg.memoryStatus,
                status: 'found',
                count: event.count,
                memories: event.memories
              };
              return { ...prev, messages };
            });
            break;

          case 'memory_confidence_calculated':
            // Memory confidence score calculated
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.memoryStatus = {
                ...lastMsg.memoryStatus,
                confidence: event.confidence,
                threshold: event.threshold,
                willUse: event.confidence >= event.threshold
              };
              return { ...prev, messages };
            });
            break;

          case 'memory_response_generated':
            // Memory-based response used
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.memoryStatus = {
                ...lastMsg.memoryStatus,
                status: 'used',
                response: event.response
              };
              lastMsg.responseType = 'memory';
              return { ...prev, messages };
            });
            break;

          case 'memory_response_complete':
            // Memory response complete - set the response data like direct_response_complete
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = event.data;
              lastMsg.loading.stage3 = false;
              // Update classification status to complete
              if (lastMsg.classification) {
                lastMsg.classification.status = 'complete';
              }
              return { ...prev, messages };
            });
            break;

          case 'memory_check_complete':
            // Memory check finished (may or may not have been used)
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg.memoryStatus && lastMsg.memoryStatus.status !== 'used') {
                lastMsg.memoryStatus.status = event.used ? 'used' : 'not_used';
              }
              return { ...prev, messages };
            });
            break;

          case 'direct_response_start':
            // Direct response path (no deliberation)
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.responseType = 'direct';
              lastMsg.loading.stage3 = true;  // Use stage3 loading for direct response
              return { ...prev, messages };
            });
            break;

          case 'direct_response_token':
            // Streaming token from direct response
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                content: event.content,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'direct_response_thinking':
            // Thinking from direct response
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                thinking: event.thinking,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'direct_response_complete':
            // Direct response complete
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = event.data;
              lastMsg.loading.stage3 = false;
              // Update classification status to complete
              if (lastMsg.classification) {
                lastMsg.classification.status = 'complete';
              }
              if (lastMsg.streaming?.stage3) {
                lastMsg.streaming.stage3.isStreaming = false;
                lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
                lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
                lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
              }
              return { ...prev, messages };
            });
            break;

          case 'formatter_start':
            // Formatter model starting to improve response
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.formatterActive = true;
              return { ...prev, messages };
            });
            break;

          case 'formatter_token':
            // Streaming token from formatter
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                content: event.content,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
                isFormatter: true,
              };
              return { ...prev, messages };
            });
            break;

          case 'formatter_thinking':
            // Thinking from formatter
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                thinking: event.thinking,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
                isFormatter: true,
              };
              return { ...prev, messages };
            });
            break;

          case 'formatter_complete':
            // Formatter complete - update final response
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = { ...lastMsg.stage3, response: event.response, model: event.model };
              lastMsg.formatterActive = false;
              lastMsg.loading.stage3 = false;
              if (lastMsg.classification) {
                lastMsg.classification.status = 'complete';
              }
              if (lastMsg.streaming?.stage3) {
                lastMsg.streaming.stage3.isStreaming = false;
                lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
                lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
                lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
              }
              return { ...prev, messages };
            });
            break;

          case 'deliberation_start':
            // Full deliberation path
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.responseType = 'deliberation';
              return { ...prev, messages };
            });
            break;

          case 'tool_call_start':
            // Tool call starting - add to tool steps array
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.toolSteps) lastMsg.toolSteps = [];
              // Check if this call_id already exists (prevent duplicates)
              if (event.call_id && lastMsg.toolSteps.some(s => s.call_id === event.call_id)) {
                return prev; // Skip duplicate
              }
              // Add new step in 'running' state
              lastMsg.toolSteps = [
                ...lastMsg.toolSteps,
                {
                  tool: event.tool,
                  input: event.arguments,
                  status: 'running',
                  startTime: Date.now(),
                  call_id: event.call_id,
                },
              ];
              return { ...prev, messages };
            });
            break;

          case 'tool_call_complete':
            // Tool call completed - update step with output
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg.toolSteps && lastMsg.toolSteps.length > 0) {
                // Find the step by call_id if available, otherwise fall back to tool name match
                const stepIndex = event.call_id
                  ? lastMsg.toolSteps.findIndex((s) => s.call_id === event.call_id)
                  : lastMsg.toolSteps.findIndex((s) => s.tool === event.tool && s.status === 'running');
                if (stepIndex !== -1) {
                  const step = lastMsg.toolSteps[stepIndex];
                  const endTime = Date.now();
                  lastMsg.toolSteps[stepIndex] = {
                    ...step,
                    status: event.result?.success !== false ? 'complete' : 'error',
                    output: event.result?.output,
                    error: event.result?.error,
                    executionTime: (endTime - step.startTime) / 1000,
                  };
                }
              }
              return { ...prev, messages };
            });
            break;

          case 'tool_result':
            // MCP tool was used, store the result (for backward compatibility)
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.toolResult = {
                tool: event.tool,
                input: event.input,
                output: event.output,
                executionTime: event.execution_time_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage1_start':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage1 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage1_token':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage1[event.model] = {
                ...(lastMsg.streaming.stage1[event.model] || {}),
                content: event.content,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage1_thinking':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage1[event.model] = {
                ...(lastMsg.streaming.stage1[event.model] || {}),
                thinking: event.thinking,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage1_model_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg.streaming?.stage1?.[event.model]) {
                lastMsg.streaming.stage1[event.model].isStreaming = false;
                lastMsg.streaming.stage1[event.model].tokensPerSecond = event.tokens_per_second;
                lastMsg.streaming.stage1[event.model].thinkingSeconds = event.thinking_seconds;
                lastMsg.streaming.stage1[event.model].elapsedSeconds = event.elapsed_seconds;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage1_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage1 = event.data;
              lastMsg.loading.stage1 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage2_start':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage2 = true;
              return { ...prev, messages };
            });
            break;

          case 'round_start':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.roundInfo) lastMsg.roundInfo = {};
              lastMsg.roundInfo = {
                current: event.round,
                maxRounds: event.max_rounds,
                isRefinement: event.is_refinement,
              };
              return { ...prev, messages };
            });
            break;

          case 'round_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg.roundInfo) {
                lastMsg.roundInfo.lowRatedResponses = event.low_rated_responses;
                lastMsg.roundInfo.triggeredNext = event.triggered_next;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage2_token':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage2[event.model] = {
                ...(lastMsg.streaming.stage2[event.model] || {}),
                content: event.content,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage2_thinking':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage2[event.model] = {
                ...(lastMsg.streaming.stage2[event.model] || {}),
                thinking: event.thinking,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage2_model_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (lastMsg.streaming?.stage2?.[event.model]) {
                lastMsg.streaming.stage2[event.model].isStreaming = false;
                lastMsg.streaming.stage2[event.model].tokensPerSecond = event.tokens_per_second;
                lastMsg.streaming.stage2[event.model].thinkingSeconds = event.thinking_seconds;
                lastMsg.streaming.stage2[event.model].elapsedSeconds = event.elapsed_seconds;
              }
              return { ...prev, messages };
            });
            break;

          case 'stage2_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage2 = event.data;
              lastMsg.metadata = event.metadata;
              lastMsg.loading.stage2 = false;
              return { ...prev, messages };
            });
            break;

          case 'stage3_start':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.loading.stage3 = true;
              return { ...prev, messages };
            });
            break;

          case 'stage3_token':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                content: event.content,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage3_thinking':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
              lastMsg.streaming.stage3 = {
                ...(lastMsg.streaming.stage3 || {}),
                thinking: event.thinking,
                isStreaming: true,
                tokensPerSecond: event.tokens_per_second,
                thinkingSeconds: event.thinking_seconds,
                elapsedSeconds: event.elapsed_seconds,
              };
              return { ...prev, messages };
            });
            break;

          case 'stage3_complete':
            setCurrentConversation((prev) => {
              const messages = [...(prev?.messages || [])];
              const lastMsg = messages[messages.length - 1];
              lastMsg.stage3 = event.data;
              lastMsg.loading.stage3 = false;
              // Update classification status to complete
              if (lastMsg.classification) {
                lastMsg.classification.status = 'complete';
              }
              if (lastMsg.streaming?.stage3) {
                lastMsg.streaming.stage3.isStreaming = false;
                lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
                lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
                lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
              }
              return { ...prev, messages };
            });
            break;

          case 'title_complete':
            // Update conversation title in list
            console.log('[App] title_complete event received:', { title: event.title, conversationId: currentConversationId });
            if (event.title) {
              setConversations(prev => prev.map(conv => 
                conv.id === currentConversationId 
                  ? { ...conv, title: event.title }
                  : conv
              ));
            }
            break;

          case 'complete':
            // Stream complete - update message count locally instead of reloading
            // This preserves the title_complete update that already happened
            setConversations(prev => prev.map(conv => 
              conv.id === currentConversationId 
                ? { ...conv, message_count: (conv.message_count || 0) + 2 } // +2 for user + assistant
                : conv
            ));
            setIsLoading(false);
            break;

          case 'error':
            console.error('Stream error:', event.message);
            setIsLoading(false);
            break;

          default:
            // Silently ignore unknown event types
            break;
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      // Remove optimistic messages on error
      setCurrentConversation((prev) => ({
        ...prev,
        messages: prev.messages.slice(0, -2),
      }));
      setIsLoading(false);
    }
  };

  const handleRedoMessage = async (messageIndex) => {
    if (!currentConversationId || isLoading) return;
    
    // Get the user message at the given index
    const userMessage = currentConversation.messages[messageIndex];
    if (!userMessage || userMessage.role !== 'user') return;
    
    // Remove the assistant response that follows (messageIndex + 1), keep user message
    setCurrentConversation((prev) => ({
      ...prev,
      messages: prev.messages.slice(0, messageIndex + 1),
    }));
    
    // Re-run the council without adding a new user message
    // truncateAt=messageIndex tells backend to keep messages up to this index (inclusive)
    // skipUserMessage=true tells backend not to add a new user message
    setIsLoading(true);
    try {
      await runCouncilForMessage(userMessage.content, { truncateAt: messageIndex, skipUserMessage: true });
    } catch (error) {
      console.error('Failed to redo message:', error);
      setIsLoading(false);
    }
  };

  const runCouncilForMessage = async (content, options = {}) => {
    const { truncateAt = null, skipUserMessage = false, regenerateTitle = false } = options;
    
    // Create a partial assistant message that will be updated progressively
    const assistantMessage = {
      role: 'assistant',
      stage1: null,
      stage2: null,
      stage3: null,
      metadata: null,
      classification: { status: 'classifying' },  // Start with classifying status
      loading: {
        stage1: false,
        stage2: false,
        stage3: false,
      },
      streaming: {
        stage1: {},
        stage2: {},
        stage3: { content: '', thinking: '', isStreaming: false },
      },
    };

    // Add the partial assistant message
    setCurrentConversation((prev) => ({
      ...prev,
      messages: [...(prev?.messages || []), assistantMessage],
    }));

    // Send message with token-level streaming
    // Pass truncateAt, skipUserMessage, and regenerateTitle for re-run/edit scenarios
    await api.sendMessageStreamTokens(currentConversationId, content, (eventType, event) => {
      switch (eventType) {
        case 'classification_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.classification = { status: 'classifying' };
            return { ...prev, messages };
          });
          break;

        case 'classification_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.classification = { ...event.classification, status: 'complete' };
            return { ...prev, messages };
          });
          break;

        case 'memory_check_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.memoryStatus = { status: 'searching', query: event.query };
            return { ...prev, messages };
          });
          break;

        case 'memory_search_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.memoryStatus = {
              ...lastMsg.memoryStatus,
              status: 'found',
              count: event.count,
              memories: event.memories
            };
            return { ...prev, messages };
          });
          break;

        case 'memory_confidence_calculated':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.memoryStatus = {
              ...lastMsg.memoryStatus,
              confidence: event.confidence,
              threshold: event.threshold,
              willUse: event.confidence >= event.threshold
            };
            return { ...prev, messages };
          });
          break;

        case 'memory_response_generated':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.memoryStatus = {
              ...lastMsg.memoryStatus,
              status: 'used',
              response: event.response
            };
            lastMsg.responseType = 'memory';
            return { ...prev, messages };
          });
          break;

        case 'memory_response_complete':
          // Memory response complete - set the response data like direct_response_complete
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage3 = event.data;
            lastMsg.loading.stage3 = false;
            // Update classification status to complete
            if (lastMsg.classification) {
              lastMsg.classification.status = 'complete';
            }
            return { ...prev, messages };
          });
          break;

        case 'memory_check_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (lastMsg.memoryStatus && lastMsg.memoryStatus.status !== 'used') {
              lastMsg.memoryStatus.status = event.used ? 'used' : 'not_used';
            }
            return { ...prev, messages };
          });
          break;

        case 'title_complete':
          // Update conversation title in list (for reruns with generic titles)
          console.log('[App runCouncil] title_complete event received:', { title: event.title, conversationId: currentConversationId });
          if (event.title) {
            setConversations(prev => prev.map(conv => 
              conv.id === currentConversationId 
                ? { ...conv, title: event.title }
                : conv
            ));
          }
          break;

        case 'direct_response_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.responseType = 'direct';
            lastMsg.loading.stage3 = true;
            return { ...prev, messages };
          });
          break;

        case 'direct_response_token':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...(lastMsg.streaming.stage3 || {}),
              content: event.content,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'direct_response_thinking':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...(lastMsg.streaming.stage3 || {}),
              thinking: event.thinking,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'direct_response_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage3 = event.data;
            lastMsg.loading.stage3 = false;
            // Update classification status to complete
            if (lastMsg.classification) {
              lastMsg.classification.status = 'complete';
            }
            if (lastMsg.streaming?.stage3) {
              lastMsg.streaming.stage3.isStreaming = false;
              lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
              lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
              lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
            }
            return { ...prev, messages };
          });
          break;

        case 'formatter_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.formatterActive = true;
            return { ...prev, messages };
          });
          break;

        case 'formatter_token':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...(lastMsg.streaming.stage3 || {}),
              content: event.content,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
              isFormatter: true,
            };
            return { ...prev, messages };
          });
          break;

        case 'formatter_thinking':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...(lastMsg.streaming.stage3 || {}),
              thinking: event.thinking,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
              isFormatter: true,
            };
            return { ...prev, messages };
          });
          break;

        case 'formatter_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage3 = { ...lastMsg.stage3, response: event.response, model: event.model };
            lastMsg.formatterActive = false;
            lastMsg.loading.stage3 = false;
            if (lastMsg.classification) {
              lastMsg.classification.status = 'complete';
            }
            if (lastMsg.streaming?.stage3) {
              lastMsg.streaming.stage3.isStreaming = false;
              lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
              lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
              lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
            }
            return { ...prev, messages };
          });
          break;

        case 'deliberation_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.responseType = 'deliberation';
            return { ...prev, messages };
          });
          break;

        case 'tool_call_start':
          // Tool call starting - add to tool steps array
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.toolSteps) lastMsg.toolSteps = [];
            // Check if this call_id already exists (prevent duplicates)
            if (event.call_id && lastMsg.toolSteps.some(s => s.call_id === event.call_id)) {
              return prev; // Skip duplicate
            }
            lastMsg.toolSteps = [
              ...lastMsg.toolSteps,
              {
                tool: event.tool,
                input: event.arguments,
                status: 'running',
                startTime: Date.now(),
                call_id: event.call_id,
              },
            ];
            return { ...prev, messages };
          });
          break;

        case 'tool_call_complete':
          // Tool call completed - update step with output
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (lastMsg.toolSteps && lastMsg.toolSteps.length > 0) {
              // Find the step by call_id if available, otherwise fall back to tool name match
              const stepIndex = event.call_id
                ? lastMsg.toolSteps.findIndex((s) => s.call_id === event.call_id)
                : lastMsg.toolSteps.findIndex((s) => s.tool === event.tool && s.status === 'running');
              if (stepIndex !== -1) {
                const step = lastMsg.toolSteps[stepIndex];
                const endTime = Date.now();
                lastMsg.toolSteps[stepIndex] = {
                  ...step,
                  status: event.result?.success !== false ? 'complete' : 'error',
                  output: event.result?.output,
                  error: event.result?.error,
                  executionTime: (endTime - step.startTime) / 1000,
                };
              }
            }
            return { ...prev, messages };
          });
          break;

        case 'tool_result':
          // MCP tool was used, store the result (for backward compatibility)
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.toolResult = {
              tool: event.tool,
              input: event.input,
              output: event.output,
              executionTime: event.execution_time_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage1_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.loading.stage1 = true;
            return { ...prev, messages };
          });
          break;

        case 'stage1_token':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage1[event.model] = {
              ...(lastMsg.streaming.stage1[event.model] || {}),
              content: event.content,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage1_thinking':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage1[event.model] = {
              ...(lastMsg.streaming.stage1[event.model] || {}),
              thinking: event.thinking,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage1_model_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (lastMsg.streaming?.stage1?.[event.model]) {
              lastMsg.streaming.stage1[event.model].isStreaming = false;
              lastMsg.streaming.stage1[event.model].tokensPerSecond = event.tokens_per_second;
              lastMsg.streaming.stage1[event.model].thinkingSeconds = event.thinking_seconds;
              lastMsg.streaming.stage1[event.model].elapsedSeconds = event.elapsed_seconds;
            }
            return { ...prev, messages };
          });
          break;

        case 'stage1_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage1 = event.data;
            lastMsg.loading.stage1 = false;
            return { ...prev, messages };
          });
          break;

        case 'stage2_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.loading.stage2 = true;
            return { ...prev, messages };
          });
          break;

        case 'stage2_token':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage2[event.model] = {
              ...(lastMsg.streaming.stage2[event.model] || {}),
              content: event.content,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage2_thinking':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage2[event.model] = {
              ...(lastMsg.streaming.stage2[event.model] || {}),
              thinking: event.thinking,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage2_model_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (lastMsg.streaming?.stage2?.[event.model]) {
              lastMsg.streaming.stage2[event.model].isStreaming = false;
              lastMsg.streaming.stage2[event.model].tokensPerSecond = event.tokens_per_second;
              lastMsg.streaming.stage2[event.model].thinkingSeconds = event.thinking_seconds;
              lastMsg.streaming.stage2[event.model].elapsedSeconds = event.elapsed_seconds;
            }
            return { ...prev, messages };
          });
          break;

        case 'stage2_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage2 = event.data;
            lastMsg.metadata = event.metadata;
            lastMsg.loading.stage2 = false;
            return { ...prev, messages };
          });
          break;

        case 'stage3_start':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.loading.stage3 = true;
            return { ...prev, messages };
          });
          break;

        case 'stage3_token':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...lastMsg.streaming.stage3,
              content: event.content,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage3_thinking':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            if (!lastMsg.streaming) lastMsg.streaming = { stage1: {}, stage2: {}, stage3: {} };
            lastMsg.streaming.stage3 = {
              ...lastMsg.streaming.stage3,
              thinking: event.thinking,
              isStreaming: true,
              tokensPerSecond: event.tokens_per_second,
              thinkingSeconds: event.thinking_seconds,
              elapsedSeconds: event.elapsed_seconds,
            };
            return { ...prev, messages };
          });
          break;

        case 'stage3_complete':
          setCurrentConversation((prev) => {
            const messages = [...(prev?.messages || [])];
            const lastMsg = messages[messages.length - 1];
            lastMsg.stage3 = { model: event.model, response: event.response };
            lastMsg.loading.stage3 = false;
            // Update classification status to complete
            if (lastMsg.classification) {
              lastMsg.classification.status = 'complete';
            }
            if (lastMsg.streaming?.stage3) {
              lastMsg.streaming.stage3.isStreaming = false;
              lastMsg.streaming.stage3.tokensPerSecond = event.tokens_per_second;
              lastMsg.streaming.stage3.thinkingSeconds = event.thinking_seconds;
              lastMsg.streaming.stage3.elapsedSeconds = event.elapsed_seconds;
            }
            return { ...prev, messages };
          });
          break;

        case 'complete':
          setIsLoading(false);
          break;

        case 'error':
          console.error('Streaming error:', event.error);
          setIsLoading(false);
          break;
      }
    }, truncateAt, skipUserMessage, regenerateTitle);
  };

  const handleEditMessage = async (messageIndex, newContent) => {
    if (!currentConversationId || isLoading) return;
    
    // Check if editing the first user message - should regenerate title
    const isFirstUserMessage = messageIndex === 0;
    
    // Update the message content and remove subsequent messages
    setCurrentConversation((prev) => {
      const messages = prev.messages.slice(0, messageIndex);
      messages.push({ role: 'user', content: newContent });
      return { ...prev, messages };
    });
    
    // Re-run the council with the edited message
    // truncateAt=messageIndex-1 tells backend to remove the old user message and everything after
    // Then backend will add the new user message
    // regenerateTitle=true when editing first message
    setIsLoading(true);
    try {
      await runCouncilForMessage(newContent, { 
        truncateAt: messageIndex - 1,
        regenerateTitle: isFirstUserMessage
      });
    } catch (error) {
      console.error('Failed to edit message:', error);
      setIsLoading(false);
    }
  };

  // Debug log current state
  console.log('[App] Render state:', { isInitializing, hasError: !!initError, conversationsCount: conversations?.length, currentConversationId });

  // Show loading screen while initializing
  if (isInitializing) {
    return (
      <div className="app app-loading">
        <div className="init-loading">
          <div className="init-spinner"></div>
          <p>Loading LLM Council...</p>
        </div>
      </div>
    );
  }

  // Show error screen if initialization failed
  if (initError) {
    return (
      <div className="app app-loading">
        <div className="init-loading init-error">
          <div className="error-icon">⚠️</div>
          <h2>Connection Error</h2>
          <p>{initError}</p>
          <button 
            className="retry-btn"
            onClick={() => {
              setIsInitializing(true);
              setInitError(null);
              // Re-run initialization
              const initializeApp = async () => {
                try {
                  await loadConversations(true);  // throwOnError=true to trigger error screen
                } catch (error) {
                  setInitError(error.message || 'Failed to connect to backend');
                } finally {
                  setIsInitializing(false);
                }
              };
              initializeApp();
            }}
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        currentConversationId={currentConversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        onRestoreConversation={handleRestoreConversation}
        newConversationDisabled={isNewConversationDisabled()}
        titleGenerationStatus={titleGenerationStatus}
      />
      <ChatInterface
        conversation={currentConversation}
        conversationId={currentConversationId}
        onSendMessage={handleSendMessage}
        onRedoMessage={handleRedoMessage}
        onEditMessage={handleEditMessage}
        isLoading={isLoading}
        memoryNames={memoryNames}
      />
    </div>
  );
}

export default App;
