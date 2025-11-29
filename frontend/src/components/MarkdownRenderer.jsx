import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useState, useEffect, useRef, useCallback } from 'react';
import './MarkdownRenderer.css';

// Image component with error handling and hover preview
function SmartImage({ src, alt, ...props }) {
  const [imageStatus, setImageStatus] = useState('loading'); // 'loading' | 'loaded' | 'error'
  const [showPreview, setShowPreview] = useState(false);
  const [previewPosition, setPreviewPosition] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  // Check if the URL looks like a placeholder/fake image
  const isFakeUrl = useCallback((url) => {
    if (!url) return true;
    const fakePatterns = [
      /via\.placeholder\.com/i,
      /placeholder\./i,
      /example\.com/i,
      /\?text=/i,
      /placehold\.it/i,
      /placekitten/i,
      /dummyimage/i,
    ];
    return fakePatterns.some(pattern => pattern.test(url));
  }, []);

  useEffect(() => {
    if (isFakeUrl(src)) {
      setImageStatus('error');
      return;
    }

    // Test if the image can actually load
    const img = new Image();
    img.onload = () => setImageStatus('loaded');
    img.onerror = () => setImageStatus('error');
    img.src = src;
  }, [src, isFakeUrl]);

  const handleMouseEnter = (e) => {
    if (imageStatus === 'loaded') {
      const rect = e.currentTarget.getBoundingClientRect();
      setPreviewPosition({
        x: rect.left,
        y: rect.bottom + 8
      });
      setShowPreview(true);
    }
  };

  const handleMouseLeave = () => {
    setShowPreview(false);
  };

  // If image failed to load or is fake, show alt text as styled text
  if (imageStatus === 'error') {
    return (
      <span className="image-alt-text" title={`Image: ${alt || 'No description'}`}>
        {alt || 'Image'}
      </span>
    );
  }

  // If image is still loading, show placeholder
  if (imageStatus === 'loading') {
    return (
      <span className="image-loading">
        {alt || 'Loading image...'}
      </span>
    );
  }

  // Image loaded successfully - show inline with hover preview
  return (
    <span 
      ref={containerRef}
      className="image-hover-container"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <span className="image-link-text">
        📷 {alt || 'Image'}
      </span>
      {showPreview && (
        <div 
          className="image-preview-tooltip"
          style={{
            position: 'fixed',
            left: `${previewPosition.x}px`,
            top: `${previewPosition.y}px`,
          }}
        >
          <img src={src} alt={alt} {...props} />
        </div>
      )}
    </span>
  );
}

// Mermaid diagram component with lazy loading
function MermaidDiagram({ code }) {
  const containerRef = useRef(null);
  const [svg, setSvg] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    
    const renderMermaid = async () => {
      try {
        // Dynamically import mermaid only when needed
        const mermaid = (await import('mermaid')).default;
        
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          fontFamily: 'inherit',
        });
        
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code);
        
        if (isMounted) {
          setSvg(svg);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      }
    };
    
    renderMermaid();
    
    return () => {
      isMounted = false;
    };
  }, [code]);

  if (loading) {
    return <div className="mermaid-loading">Loading diagram...</div>;
  }

  if (error) {
    return (
      <div className="mermaid-error">
        <span>⚠️ Diagram error: {error}</span>
        <pre>{code}</pre>
      </div>
    );
  }

  return (
    <div 
      ref={containerRef}
      className="mermaid-container"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

// Custom code block component with syntax highlighting and mermaid support
function CodeBlock({ node, inline, className, children, ...props }) {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const code = String(children).replace(/\n$/, '');

  // Handle mermaid diagrams
  if (language === 'mermaid') {
    return <MermaidDiagram code={code} />;
  }

  // Inline code
  if (inline) {
    return (
      <code className="inline-code" {...props}>
        {children}
      </code>
    );
  }

  // Code block with syntax highlighting
  return (
    <div className="code-block-wrapper">
      {language && <span className="code-language">{language}</span>}
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={language || 'text'}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: '0 0 6px 6px',
          fontSize: '13px',
        }}
        {...props}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

/**
 * Enhanced markdown renderer with support for:
 * - GitHub Flavored Markdown (tables, strikethrough, task lists, etc.)
 * - Syntax highlighted code blocks
 * - Mermaid diagrams
 * - Raw HTML (for advanced formatting)
 */
export default function MarkdownRenderer({ children, className = '' }) {
  return (
    <div className={`markdown-renderer ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          code: CodeBlock,
          // Smart image handling with hover preview
          img: SmartImage,
          // Enhance table styling
          table: ({ node, ...props }) => (
            <div className="table-wrapper">
              <table {...props} />
            </div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
